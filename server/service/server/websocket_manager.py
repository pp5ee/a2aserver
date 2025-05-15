import asyncio
import json
import logging
from typing import Dict, Set, Optional, List
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    管理WebSocket连接和消息推送
    """
    # 单例模式
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = WebSocketManager()
        return cls._instance
    
    def __init__(self):
        # 使用字典存储每个用户的WebSocket连接
        # {wallet_address: list(websocket_connections)}
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # 锁，用于保护共享资源
        self.lock = asyncio.Lock()
        # 待发送的消息队列，用于连接暂时不可用时
        self.pending_messages: Dict[str, List[dict]] = {}
        # 重试配置
        self.max_retries = 3
        self.retry_delay = 1.0  # 秒
        # 地址映射，用于解决大小写敏感问题
        self.address_mapping: Dict[str, str] = {}
        logger.info("WebSocket管理器初始化完成")
    
    async def connect(self, websocket: WebSocket, wallet_address: str):
        """建立WebSocket连接"""
        if not wallet_address:
            logger.warning("尝试建立WebSocket连接但钱包地址为空")
            await websocket.close(code=1008, reason="Missing wallet address")
            return
            
        # 标准化钱包地址
        normalized_address = wallet_address.strip()
        
        # 初始化连接
        await websocket.accept()
        
        # 添加到连接池
        if normalized_address not in self.active_connections:
            self.active_connections[normalized_address] = []
        
        self.active_connections[normalized_address].append(websocket)
        
        # 记录详细的连接信息
        connection_info = {
            "total_connections": sum(len(conns) for conns in self.active_connections.values()),
            "active_wallet_count": len(self.active_connections),
            "connection_count_for_wallet": len(self.active_connections[normalized_address])
        }
        
        logger.info(f"WebSocket连接已建立: wallet={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}..., 连接详情: {json.dumps(connection_info)}")
        
        # 尝试发送之前暂存的消息
        if normalized_address in self.pending_messages and self.pending_messages[normalized_address]:
            asyncio.create_task(self._send_pending_messages(normalized_address))
            
    async def disconnect(self, websocket: WebSocket, wallet_address: str):
        """断开WebSocket连接"""
        if not wallet_address:
            logger.warning("尝试断开WebSocket连接但钱包地址为空")
            return
            
        # 标准化钱包地址
        normalized_address = wallet_address.strip()
        
        # 从连接池移除
        if normalized_address in self.active_connections:
            # 查找并移除指定的连接
            if websocket in self.active_connections[normalized_address]:
                self.active_connections[normalized_address].remove(websocket)
                logger.info(f"WebSocket连接已断开: wallet={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}..., 剩余连接数: {len(self.active_connections[normalized_address])}")
            
            # 如果没有更多连接，移除钱包地址项
            if not self.active_connections[normalized_address]:
                del self.active_connections[normalized_address]
                logger.info(f"钱包地址 {normalized_address[:10] if len(normalized_address) > 10 else normalized_address}... 的所有WebSocket连接已断开")
    
    async def send_message(self, wallet_address: str, message: dict):
        """向指定钱包地址的所有连接发送消息"""
        if not wallet_address:
            logger.warning(f"websocket send_message: 钱包地址为空")
            return
        
        # 标准化钱包地址，避免大小写问题
        normalized_address = wallet_address.strip()
        
        # 检查是否有活跃连接
        if normalized_address not in self.active_connections or not self.active_connections[normalized_address]:
            # 如果没有连接，记录更详细的日志并存储待发送消息
            connection_info = {
                "total_connections": sum(len(conns) for conns in self.active_connections.values()),
                "active_wallet_count": len(self.active_connections),
                "active_wallets": [addr[:10] + "..." for addr in self.active_connections.keys()]
            }
            logger.warning(f"websocket send_message: 钱包地址 {normalized_address[:10] if len(normalized_address) > 10 else normalized_address}... 无活跃连接。当前连接状态: {json.dumps(connection_info)}")
            
            # 存储待发送消息
            self._store_pending_message(normalized_address, message)
            return
            
        # 获取钱包地址的所有活跃连接
        connections = self.active_connections[normalized_address]
        
        # 将消息转换为JSON字符串
        message_json = json.dumps(message)
        
        # 记录发送信息日志
        message_type = message.get('type', 'unknown')
        logger.info(f"准备向 {normalized_address[:10] if len(normalized_address) > 10 else normalized_address}... 发送WebSocket消息: type={message_type}, 连接数: {len(connections)}")
        
        # 发送消息到所有连接
        disconnected = []
        success_count = 0
        
        for connection in connections:
            try:
                await connection.send_text(message_json)
                success_count += 1
            except Exception as e:
                logger.error(f"发送WebSocket消息失败: {e}")
                # 将断开的连接添加到列表
                disconnected.append(connection)
        
        # 记录发送结果
        if success_count > 0:
            logger.info(f"成功向 {normalized_address[:10] if len(normalized_address) > 10 else normalized_address}... 的 {success_count}/{len(connections)} 个连接发送消息")
                
        # 清理断开的连接
        for connection in disconnected:
            if connection in self.active_connections[normalized_address]:
                self.active_connections[normalized_address].remove(connection)
                logger.info(f"已移除断开的WebSocket连接, 剩余连接数: {len(self.active_connections[normalized_address])}")
        
        # 如果所有连接都断开，移除钱包地址项
        if not self.active_connections[normalized_address]:
            del self.active_connections[normalized_address]
            logger.info(f"钱包地址 {normalized_address[:10] if len(normalized_address) > 10 else normalized_address}... 的所有WebSocket连接已断开")
    
    def _store_pending_message(self, wallet_address: str, message: dict):
        """存储待发送的消息，以便稍后连接建立时发送"""
        if not wallet_address:
            logger.warning("尝试存储待发送消息但钱包地址为空")
            return
            
        # 标准化钱包地址
        normalized_address = wallet_address.strip()
        
        message_type = message.get('type', 'unknown')
        conversation_id = message.get('conversation_id', 'unknown')
        
        if normalized_address not in self.pending_messages:
            self.pending_messages[normalized_address] = []
        
        # 最多存储100条消息
        if len(self.pending_messages[normalized_address]) < 100:
            self.pending_messages[normalized_address].append(message)
            logger.info(f"暂存待发送消息: 地址={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}..., 类型={message_type}, 会话ID={conversation_id}")
        else:
            logger.warning(f"暂存消息队列已满，丢弃消息: 地址={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}..., 类型={message_type}")
    
    async def _send_pending_messages(self, wallet_address: str):
        """发送暂存的待发送消息"""
        if not wallet_address:
            logger.warning("尝试发送暂存消息但钱包地址为空")
            return
            
        # 标准化钱包地址
        normalized_address = wallet_address.strip()
        
        if normalized_address not in self.pending_messages or not self.pending_messages[normalized_address]:
            return
        
        logger.info(f"尝试发送暂存消息，地址={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}..., 消息数={len(self.pending_messages[normalized_address])}")
        
        messages = self.pending_messages[normalized_address]
        self.pending_messages[normalized_address] = []
        
        for message in messages:
            await self.send_message(normalized_address, message)
    
    async def _retry_send_message(self, wallet_address: str, message: dict, retry_count: int = 0):
        """重试发送消息"""
        if not wallet_address:
            logger.warning("尝试重试发送消息但钱包地址为空")
            return
            
        # 标准化钱包地址
        normalized_address = wallet_address.strip()
        
        if retry_count >= self.max_retries:
            logger.warning(f"发送消息重试次数已达上限，放弃发送: 地址={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}..., 类型={message.get('type', 'unknown')}")
            return
        
        # 递增延迟
        await asyncio.sleep(self.retry_delay * (retry_count + 1))
        
        logger.info(f"重试发送消息，尝试 #{retry_count+1}, 地址={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}..., 类型={message.get('type', 'unknown')}")
        
        # 检查连接是否已恢复
        if normalized_address not in self.active_connections or not self.active_connections[normalized_address]:
            self._store_pending_message(normalized_address, message)
            return
        
        try:
            # 序列化消息
            message_str = json.dumps(message)
            
            # 获取连接
            connections = self.active_connections.get(normalized_address, [])
            if not connections:
                self._store_pending_message(normalized_address, message)
                return
            
            # 重新尝试发送
            success = False
            for websocket in connections:
                try:
                    await websocket.send_text(message_str)
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"重试发送消息失败, 尝试 #{retry_count+1}, 错误: {str(e)}")
            
            if success:
                logger.info(f"重试发送消息成功, 尝试 #{retry_count+1}, 地址={normalized_address[:10] if len(normalized_address) > 10 else normalized_address}...")
            else:
                # 递归重试
                asyncio.create_task(self._retry_send_message(normalized_address, message, retry_count + 1))
        except Exception as e:
            logger.error(f"重试发送消息异常: {str(e)}")
            # 继续递归重试
            asyncio.create_task(self._retry_send_message(normalized_address, message, retry_count + 1))
    
    async def broadcast(self, message: dict):
        """向所有连接的用户广播消息"""
        # 获取所有用户
        all_users = list(self.active_connections.keys())
        
        logger.info(f"广播消息给 {len(all_users)} 个用户")
        
        # 为每个用户发送消息
        for wallet_address in all_users:
            await self.send_message(wallet_address, message)
    
    def get_active_connections_count(self, wallet_address: Optional[str] = None) -> int:
        """获取活跃连接数"""
        if wallet_address:
            # 标准化钱包地址
            normalized_address = wallet_address.strip()
            return len(self.active_connections.get(normalized_address, []))
        else:
            return sum(len(connections) for connections in self.active_connections.values()) 
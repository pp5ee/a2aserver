import asyncio
import json
import logging
from typing import Dict, Set, Optional
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
        # {wallet_address: set(websocket_connections)}
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # 锁，用于保护共享资源
        self.lock = asyncio.Lock()
        # 待发送的消息队列，用于连接暂时不可用时
        self.pending_messages: Dict[str, list] = {}
        # 重试配置
        self.max_retries = 3
        self.retry_delay = 1.0  # 秒
    
    async def connect(self, websocket: WebSocket, wallet_address: str):
        """建立WebSocket连接"""
        if not wallet_address:
            logger.warning("尝试建立WebSocket连接时未提供钱包地址")
            return
            
        await websocket.accept()
        
        async with self.lock:
            # 使用原始地址作为key
            if wallet_address not in self.active_connections:
                self.active_connections[wallet_address] = set()
            self.active_connections[wallet_address].add(websocket)
            
        logger.info(f"WebSocket连接建立: {wallet_address}, 当前连接数: {len(self.active_connections[wallet_address])}")
        
        # 检查是否有待发送的消息
        await self._send_pending_messages(wallet_address)
    
    async def disconnect(self, websocket: WebSocket, wallet_address: str):
        """断开WebSocket连接"""
        if not wallet_address:
            return
        
        async with self.lock:
            if wallet_address in self.active_connections:
                self.active_connections[wallet_address].discard(websocket)
                # 如果用户没有活跃连接，则删除该用户的记录
                if not self.active_connections[wallet_address]:
                    del self.active_connections[wallet_address]
                logger.info(f"WebSocket连接断开: {wallet_address}")
    
    async def send_message(self, wallet_address: str, message: dict):
        """向指定用户发送消息"""
        if not wallet_address:
            logger.warning(f"无法发送WebSocket消息: 钱包地址为空")
            return
        
        if wallet_address not in self.active_connections:
            logger.warning(f"无法发送WebSocket消息: 找不到钱包地址 {wallet_address} 的活跃连接")
            
            # 额外记录当前所有活跃连接的地址，帮助调试
            all_addresses = list(self.active_connections.keys())
            if all_addresses:
                logger.info(f"当前活跃连接的钱包地址: {all_addresses}")
            
            # 存储待发送消息，以便稍后连接建立时发送
            self._store_pending_message(wallet_address, message)
            return
        
        # 序列化消息
        message_str = json.dumps(message)
        
        # 获取用户的所有连接
        connections = self.active_connections.get(wallet_address, set())
        if not connections:
            logger.warning(f"钱包地址 {wallet_address} 没有活跃的WebSocket连接")
            
            # 存储待发送消息，以便稍后连接建立时发送
            self._store_pending_message(wallet_address, message)
            return
        
        logger.info(f"准备向用户 {wallet_address} 发送消息: 消息类型={message.get('type', 'unknown')}, 会话ID={message.get('conversation_id', 'unknown')}")
        
        # 发送消息到所有连接，处理可能的断开连接
        disconnected = set()
        success_count = 0
        
        for websocket in connections:
            try:
                await websocket.send_text(message_str)
                success_count += 1
            except Exception as e:
                logger.error(f"向用户 {wallet_address} 发送消息失败: {str(e)}")
                disconnected.add(websocket)
        
        logger.info(f"已向用户 {wallet_address} 的 {success_count}/{len(connections)} 个连接发送消息")
        
        # 移除断开的连接
        if disconnected:
            async with self.lock:
                if wallet_address in self.active_connections:
                    self.active_connections[wallet_address] = connections.difference(disconnected)
                    if not self.active_connections[wallet_address]:
                        del self.active_connections[wallet_address]
                        logger.info(f"用户 {wallet_address} 的所有WebSocket连接均已断开")
        
        # 如果部分发送失败，安排重试
        if success_count == 0 and wallet_address not in self.pending_messages:
            await self._retry_send_message(wallet_address, message)
    
    def _store_pending_message(self, wallet_address: str, message: dict):
        """存储待发送的消息，以便稍后连接建立时发送"""
        message_type = message.get('type', 'unknown')
        conversation_id = message.get('conversation_id', 'unknown')
        
        if wallet_address not in self.pending_messages:
            self.pending_messages[wallet_address] = []
        
        # 最多存储100条消息
        if len(self.pending_messages[wallet_address]) < 100:
            self.pending_messages[wallet_address].append(message)
            logger.info(f"暂存待发送消息: 地址={wallet_address}, 类型={message_type}, 会话ID={conversation_id}")
        else:
            logger.warning(f"暂存消息队列已满，丢弃消息: 地址={wallet_address}, 类型={message_type}")
    
    async def _send_pending_messages(self, wallet_address: str):
        """发送暂存的待发送消息"""
        if wallet_address not in self.pending_messages or not self.pending_messages[wallet_address]:
            return
        
        logger.info(f"尝试发送暂存消息，地址={wallet_address}, 消息数={len(self.pending_messages[wallet_address])}")
        
        messages = self.pending_messages[wallet_address]
        self.pending_messages[wallet_address] = []
        
        for message in messages:
            await self.send_message(wallet_address, message)
    
    async def _retry_send_message(self, wallet_address: str, message: dict, retry_count: int = 0):
        """重试发送消息"""
        if retry_count >= self.max_retries:
            logger.warning(f"发送消息重试次数已达上限，放弃发送: 地址={wallet_address}, 类型={message.get('type', 'unknown')}")
            return
        
        # 递增延迟
        await asyncio.sleep(self.retry_delay * (retry_count + 1))
        
        logger.info(f"重试发送消息，尝试 #{retry_count+1}, 地址={wallet_address}, 类型={message.get('type', 'unknown')}")
        
        # 检查连接是否已恢复
        if wallet_address not in self.active_connections or not self.active_connections[wallet_address]:
            self._store_pending_message(wallet_address, message)
            return
        
        try:
            # 序列化消息
            message_str = json.dumps(message)
            
            # 获取连接
            connections = self.active_connections.get(wallet_address, set())
            if not connections:
                self._store_pending_message(wallet_address, message)
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
                logger.info(f"重试发送消息成功, 尝试 #{retry_count+1}, 地址={wallet_address}")
            else:
                # 递归重试
                asyncio.create_task(self._retry_send_message(wallet_address, message, retry_count + 1))
        except Exception as e:
            logger.error(f"重试发送消息异常: {str(e)}")
            # 继续递归重试
            asyncio.create_task(self._retry_send_message(wallet_address, message, retry_count + 1))
    
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
            return len(self.active_connections.get(wallet_address, set()))
        else:
            return sum(len(connections) for connections in self.active_connections.values()) 
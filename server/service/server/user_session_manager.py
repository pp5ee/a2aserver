import datetime
from datetime import timedelta
import logging
from typing import Dict, Optional
import os

# 尝试导入MySQL连接器，如果不可用则使用内存模式
try:
    import pymysql
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False
    logging.warning("PyMySQL数据库模块不可用，将使用内存模式")

from .adk_host_manager import ADKHostManager
from common.types import AgentCard, Message, Task, TaskStatus, TaskState, Artifact

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserSessionManager:
    """用户会话管理器，为每个用户维护独立的ADKHostManager实例"""
    
    _instance = None
    _host_managers: Dict[str, ADKHostManager] = {}  # 钱包地址 -> ADKHostManager 实例
    _db_connection = None
    _memory_mode = not HAS_MYSQL  # 是否使用内存模式
    _memory_user_agents = {}  # 用于内存模式存储用户代理 {wallet_address: [agent_url]}
    _memory_users = {}  # 用于内存模式存储用户信息 {wallet_address: last_active_time}
    
    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = UserSessionManager()
        return cls._instance
    
    def __init__(self):
        """初始化数据库连接并创建表结构"""
        if not self._memory_mode:
            self._initialize_database()
        logger.info(f"用户会话管理器初始化完成，使用{'内存' if self._memory_mode else '数据库'}模式")
        
    def _initialize_database(self):
        """初始化MySQL数据库连接"""
        if self._memory_mode:
            return
            
        try:
            # 首先尝试连接MySQL服务器（不指定数据库）
            try:
                conn = pymysql.connect(
                    host="localhost",
                    port=3306,
                    user="root",
                    password="orangepi123"
                )
                cursor = conn.cursor()
                
                # 检查a2a数据库是否存在
                cursor.execute("SHOW DATABASES LIKE 'a2a'")
                exists = cursor.fetchone()
                
                if not exists:
                    # 创建数据库
                    logger.info("创建a2a数据库...")
                    cursor.execute("CREATE DATABASE IF NOT EXISTS a2a")
                    conn.commit()
                    logger.info("a2a数据库创建成功")
                
                # 关闭无数据库连接
                cursor.close()
                conn.close()
            except pymysql.Error as err:
                logger.error(f"无法连接MySQL服务器: {err}")
                self._memory_mode = True
                logger.warning("切换到内存模式运行，数据将不会持久化")
                return
            
            # 现在连接a2a数据库
            self._db_connection = pymysql.connect(
                host="localhost",
                port=3306,
                user="root",
                password="orangepi123",
                database="a2a"
            )
            logger.info("数据库连接成功")
            
            # 创建表结构
            self._create_tables()
        except pymysql.Error as err:
            logger.error(f"数据库初始化失败: {err}")
            # 切换到内存模式
            self._memory_mode = True
            logger.warning("切换到内存模式运行，数据将不会持久化")
        
    def _create_tables(self):
        """创建必要的数据库表"""
        if self._memory_mode:
            return
            
        try:
            cursor = self._db_connection.cursor()
            
            # 用户表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                wallet_address VARCHAR(255) PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            ''')
            
            # 用户代理关系表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_agents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                wallet_address VARCHAR(255),
                agent_url VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (wallet_address) REFERENCES users(wallet_address) ON DELETE CASCADE,
                UNIQUE(wallet_address, agent_url)
            )
            ''')
            
            # 会话记录表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id VARCHAR(255) PRIMARY KEY,
                wallet_address VARCHAR(255),
                name VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (wallet_address) REFERENCES users(wallet_address) ON DELETE CASCADE
            )
            ''')
            
            # 消息记录表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                message_id VARCHAR(255) PRIMARY KEY,
                conversation_id VARCHAR(255),
                wallet_address VARCHAR(255),
                role VARCHAR(50),
                content LONGTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                FOREIGN KEY (wallet_address) REFERENCES users(wallet_address) ON DELETE CASCADE
            )
            ''')
            
            # 任务记录表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id VARCHAR(255) PRIMARY KEY,
                session_id VARCHAR(255),
                conversation_id VARCHAR(255),
                wallet_address VARCHAR(255),
                state VARCHAR(50),
                status_message_id VARCHAR(255),
                data LONGTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                FOREIGN KEY (wallet_address) REFERENCES users(wallet_address) ON DELETE CASCADE
            )
            ''')
            
            # 任务制品表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_artifacts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                task_id VARCHAR(255),
                name VARCHAR(255),
                description TEXT,
                data LONGTEXT,
                index_num INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            )
            ''')
            
            self._db_connection.commit()
            cursor.close()
            logger.info("数据库表创建/检查完成")
        except Exception as err:
            logger.error(f"创建表失败: {err}")
            # 切换到内存模式
            self._memory_mode = True
            logger.warning("切换到内存模式运行，数据将不会持久化")
    
    def get_host_manager(self, wallet_address: str) -> ADKHostManager:
        """获取指定用户的Host Manager实例，如果不存在则创建新实例"""
        if not wallet_address:
            logger.warning("尝试获取无效钱包地址的Host Manager")
            # 返回一个临时Host Manager用于匿名访问
            return ADKHostManager()
        
        # 确保用户存在
        self._ensure_user_exists(wallet_address)
        
        # 如果该用户没有Host Manager实例，创建一个
        if wallet_address not in self._host_managers:
            logger.info(f"为用户 {wallet_address} 创建新的Host Manager实例")
            
            # 获取环境变量中的API密钥
            api_key = os.environ.get("GOOGLE_API_KEY", "")
            if not api_key:
                # 确保至少有一个默认值
                api_key = "default_key_placeholder"
            
            uses_vertex_ai = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
            
            # 创建新的ADKHostManager实例，使用环境变量中的API key
            host_manager = ADKHostManager(api_key=api_key, uses_vertex_ai=uses_vertex_ai)
            
            # 恢复用户之前注册的代理
            self._restore_user_agents(wallet_address, host_manager)
            
            # 将host_manager添加到字典中
            self._host_managers[wallet_address] = host_manager
            
            # 尝试从数据库恢复用户的历史会话
            if not self._memory_mode and self._db_connection:
                try:
                    # 从数据库加载用户的历史会话列表
                    self._db_connection.ping(reconnect=True)
                    cursor = self._db_connection.cursor()
                    
                    # 查询用户的所有会话
                    cursor.execute("""
                    SELECT conversation_id 
                    FROM conversations 
                    WHERE wallet_address = %s
                    ORDER BY updated_at DESC
                    LIMIT 5  # 限制只恢复最近的5个会话
                    """, (wallet_address,))
                    
                    for (conversation_id,) in cursor.fetchall():
                        try:
                            # 尝试恢复会话
                            self.rebuild_conversation_from_history(wallet_address, conversation_id)
                            logger.info(f"已恢复用户 {wallet_address} 的历史会话 {conversation_id}")
                        except Exception as e:
                            logger.error(f"恢复会话 {conversation_id} 时出错: {e}")
                    
                    cursor.close()
                except Exception as err:
                    logger.error(f"恢复用户历史会话时出错: {err}")
            
        return self._host_managers[wallet_address]
    
    def _ensure_user_exists(self, wallet_address: str):
        """确保用户在数据库中存在，如果不存在则创建新用户"""
        if self._memory_mode:
            # 内存模式下直接更新用户状态
            self._memory_users[wallet_address] = datetime.datetime.now()
            if wallet_address not in self._memory_user_agents:
                self._memory_user_agents[wallet_address] = []
            return
            
        if not self._db_connection:
            logger.warning("数据库未连接，无法确保用户存在")
            return
            
        try:
            self._db_connection.ping(reconnect=True)
            
            cursor = self._db_connection.cursor()
            cursor.execute("SELECT wallet_address FROM users WHERE wallet_address = %s", (wallet_address,))
            result = cursor.fetchone()
            
            if not result:
                # 新用户，添加到数据库
                logger.info(f"创建新用户: {wallet_address}")
                cursor.execute("INSERT INTO users (wallet_address) VALUES (%s)", (wallet_address,))
                self._db_connection.commit()
            else:
                # 更新最后活跃时间
                cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE wallet_address = %s", (wallet_address,))
                self._db_connection.commit()
                
            cursor.close()
        except Exception as err:
            logger.error(f"确保用户存在时出错: {err}")
            # 切换到内存模式
            if not self._memory_mode:
                self._memory_mode = True
                logger.warning("切换到内存模式运行，数据将不会持久化")
                # 确保在内存中存在
                self._memory_users[wallet_address] = datetime.datetime.now()
                if wallet_address not in self._memory_user_agents:
                    self._memory_user_agents[wallet_address] = []
    
    def _restore_user_agents(self, wallet_address: str, host_manager: ADKHostManager):
        """从数据库恢复用户之前注册的代理"""
        if self._memory_mode:
            # 内存模式下恢复代理
            if wallet_address in self._memory_user_agents:
                for agent_url in self._memory_user_agents[wallet_address]:
                    try:
                        logger.info(f"为用户 {wallet_address} 恢复代理: {agent_url}")
                        host_manager.register_agent(agent_url)
                    except Exception as e:
                        logger.error(f"恢复代理 {agent_url} 失败: {e}")
            return
            
        if not self._db_connection:
            logger.warning("数据库未连接，无法恢复用户代理")
            return
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            cursor.execute("SELECT agent_url FROM user_agents WHERE wallet_address = %s", (wallet_address,))
            
            for (agent_url,) in cursor.fetchall():
                try:
                    logger.info(f"为用户 {wallet_address} 恢复代理: {agent_url}")
                    host_manager.register_agent(agent_url)
                except Exception as e:
                    logger.error(f"恢复代理 {agent_url} 失败: {e}")
                    
            cursor.close()
        except Exception as err:
            logger.error(f"恢复用户代理时出错: {err}")
            # 切换到内存模式
            if not self._memory_mode:
                self._memory_mode = True
                logger.warning("切换到内存模式运行，数据将不会持久化")
    
    def register_agent(self, wallet_address: str, agent_url: str) -> Optional[AgentCard]:
        """为指定用户注册代理"""
        logger.info(f"为用户 {wallet_address} 注册代理: {agent_url}")
        
        # 获取用户的Host Manager
        host_manager = self.get_host_manager(wallet_address)
        
        # 注册代理
        result = host_manager.register_agent(agent_url)
        
        # 保存代理信息
        if self._memory_mode:
            # 内存模式下保存
            if wallet_address not in self._memory_user_agents:
                self._memory_user_agents[wallet_address] = []
            if agent_url not in self._memory_user_agents[wallet_address]:
                self._memory_user_agents[wallet_address].append(agent_url)
        elif self._db_connection:
            # 数据库模式下保存
            try:
                self._db_connection.ping(reconnect=True)
                cursor = self._db_connection.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO user_agents (wallet_address, agent_url) VALUES (%s, %s)", 
                        (wallet_address, agent_url)
                    )
                    self._db_connection.commit()
                except pymysql.IntegrityError:
                    # 代理已存在，忽略
                    logger.info(f"代理 {agent_url} 已存在于用户 {wallet_address} 的记录中")
                    
                cursor.close()
            except Exception as err:
                logger.error(f"保存代理信息时出错: {err}")
                # 切换到内存模式
                if not self._memory_mode:
                    self._memory_mode = True
                    logger.warning("切换到内存模式运行，数据将不会持久化")
                    # 确保在内存中保存
                    if wallet_address not in self._memory_user_agents:
                        self._memory_user_agents[wallet_address] = []
                    if agent_url not in self._memory_user_agents[wallet_address]:
                        self._memory_user_agents[wallet_address].append(agent_url)
            
        return result
    
    def cleanup_inactive_sessions(self, timeout_minutes: int = 30):
        """清理超过指定时间未活跃的用户会话"""
        logger.info(f"清理超过 {timeout_minutes} 分钟未活跃的用户会话")
        
        if self._memory_mode:
            # 内存模式下清理
            current_time = datetime.datetime.now()
            inactive_timeout = current_time - timedelta(minutes=timeout_minutes)
            
            # 查找过期用户
            inactive_users = []
            for wallet_address, last_active in self._memory_users.items():
                if last_active < inactive_timeout:
                    inactive_users.append(wallet_address)
            
            # 清理过期用户的会话
            for wallet_address in inactive_users:
                if wallet_address in self._host_managers:
                    logger.info(f"清理用户 {wallet_address} 的会话")
                    del self._host_managers[wallet_address]
            return
                
        if not self._db_connection:
            logger.warning("数据库未连接，无法清理会话")
            return
        
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询超时的用户
            cursor.execute(
                "SELECT wallet_address FROM users WHERE last_active < %s", 
                (datetime.datetime.now() - timedelta(minutes=timeout_minutes),)
            )
            
            for (wallet_address,) in cursor.fetchall():
                # 如果用户有活跃的Host Manager实例，清除它
                if wallet_address in self._host_managers:
                    logger.info(f"清理用户 {wallet_address} 的会话")
                    del self._host_managers[wallet_address]
                    
            cursor.close()
        except Exception as err:
            logger.error(f"清理会话时出错: {err}")
            # 切换到内存模式
            if not self._memory_mode:
                self._memory_mode = True
                logger.warning("切换到内存模式运行，数据将不会持久化") 
    
    def refresh_user_agents(self, wallet_address: str):
        """在每次请求时重新加载用户的agent列表"""
        if not wallet_address or wallet_address not in self._host_managers:
            return
            
        # 获取用户的HostManager实例
        host_manager = self._host_managers[wallet_address]
        
        # 直接修改内部的_agents列表而不是通过property
        if hasattr(host_manager, '_agents'):
            # 清除现有代理
            host_manager._agents = []
            # 清除host_agent中的代理
            if hasattr(host_manager, '_host_agent') and hasattr(host_manager._host_agent, 'agents'):
                host_manager._host_agent.agents = []
                
            # 重新初始化host
            host_manager._initialize_host()
            
        # 重新加载并注册代理
        self._restore_user_agents(wallet_address, host_manager)

    def save_conversation(self, wallet_address: str, conversation_id: str, name: str = "", is_active: bool = True):
        """将会话记录保存到数据库"""
        if self._memory_mode or not self._db_connection or not wallet_address:
            return
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 尝试插入新记录，如果已存在则更新
            try:
                cursor.execute("""
                INSERT INTO conversations (conversation_id, wallet_address, name, is_active) 
                VALUES (%s, %s, %s, %s)
                """, (conversation_id, wallet_address, name, is_active))
            except pymysql.IntegrityError:
                # 会话已存在，更新记录
                cursor.execute("""
                UPDATE conversations SET 
                name = %s, is_active = %s, updated_at = CURRENT_TIMESTAMP
                WHERE conversation_id = %s AND wallet_address = %s
                """, (name, is_active, conversation_id, wallet_address))
                
            self._db_connection.commit()
            cursor.close()
        except Exception as err:
            logger.error(f"保存会话记录时出错: {err}")
            
    def save_message(self, wallet_address: str, message_id: str, conversation_id: str, role: str, content: str):
        """将消息记录保存到数据库"""
        if self._memory_mode or not self._db_connection or not wallet_address:
            return
            
        try:
            # 首先确保会话已记录
            self.save_conversation(wallet_address, conversation_id)
            
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 尝试插入新消息，如果已存在则忽略（消息内容不会变化）
            try:
                cursor.execute("""
                INSERT INTO messages (message_id, conversation_id, wallet_address, role, content)
                VALUES (%s, %s, %s, %s, %s)
                """, (message_id, conversation_id, wallet_address, role, content))
                self._db_connection.commit()
            except pymysql.IntegrityError:
                # 消息已存在，忽略
                pass
                
            cursor.close()
        except Exception as err:
            logger.error(f"保存消息记录时出错: {err}")
            
    def save_message_from_object(self, wallet_address: str, message: Message):
        """从消息对象保存消息记录"""
        if not message or not message.metadata:
            return
            
        try:
            # 获取必要的元数据
            message_id = message.metadata.get('message_id')
            conversation_id = message.metadata.get('conversation_id')
            
            if not message_id or not conversation_id:
                return
                
            # 标准化角色名称
            role = message.role
            if role in ['model', 'assistant']:
                role = 'agent'  # 确保统一角色名称
                
            # 序列化消息内容
            import json
            content = json.dumps({
                'parts': [self._serialize_message_part(part) for part in message.parts],
                'role': role,
                'metadata': message.metadata
            })
            
            # 保存消息
            self.save_message(
                wallet_address=wallet_address,
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                content=content
            )
            logger.info(f"已保存用户 {wallet_address} 的{role}消息 {message_id[:8]} 到数据库")
        except Exception as err:
            logger.error(f"从消息对象保存记录时出错: {err}")
            
    def _serialize_message_part(self, part):
        """序列化消息部分为可存储的格式"""
        try:
            # 直接使用part的原始属性
            if hasattr(part, 'type'):
                # 处理文本部分
                if part.type == 'text' and hasattr(part, 'text'):
                    return {
                        'type': 'text',
                        'text': part.text
                    }
                # 处理数据部分
                elif part.type == 'data' and hasattr(part, 'data'):
                    return {
                        'type': 'data',
                        'data': part.data
                    }
                # 处理文件部分
                elif part.type == 'file' and hasattr(part, 'file'):
                    file_data = {}
                    if hasattr(part.file, 'mimeType'):
                        file_data['mimeType'] = part.file.mimeType
                    if hasattr(part.file, 'uri'):
                        file_data['uri'] = part.file.uri
                    if hasattr(part.file, 'bytes'):
                        file_data['bytes'] = part.file.bytes
                    return {
                        'type': 'file',
                        'file': file_data
                    }
            
            # 对于其他类型，尝试转换为字典
            if hasattr(part, 'model_dump'):
                return part.model_dump()
            elif hasattr(part, '__dict__'):
                return part.__dict__
            else:
                # 简单类型直接返回
                return {'type': 'text', 'text': str(part)}
        except Exception as e:
            logger.error(f"序列化消息部分时出错: {e}")
            return {'type': 'text', 'text': str(part)}

    def get_conversation_wallet_address(self, conversation_id: str) -> str:
        """获取会话对应的钱包地址"""
        if not conversation_id:
            return None
            
        if self._memory_mode:
            # 遍历所有用户，查找会话所属
            for wallet_address, host_manager in self._host_managers.items():
                if hasattr(host_manager, 'conversations'):
                    for conv in host_manager.conversations:
                        if conv.conversation_id == conversation_id:
                            return wallet_address
            return None
            
        if not self._db_connection:
            return None
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 从数据库查询会话对应的钱包地址
            cursor.execute("""
            SELECT wallet_address FROM conversations 
            WHERE conversation_id = %s
            """, (conversation_id,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return result[0]
            else:
                return None
        except Exception as err:
            logger.error(f"获取会话钱包地址时出错: {err}")
            return None

    def get_user_conversations(self, wallet_address: str):
        """获取用户的所有会话记录"""
        if not wallet_address:
            return []
            
        if self._memory_mode:
            # 内存模式下从host_manager获取
            if wallet_address in self._host_managers:
                return self._host_managers[wallet_address].conversations
            return []
            
        if not self._db_connection:
            return []
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询用户的所有会话
            cursor.execute("""
            SELECT conversation_id, name, is_active, created_at, updated_at
            FROM conversations 
            WHERE wallet_address = %s
            ORDER BY updated_at DESC
            """, (wallet_address,))
            
            conversations = []
            for (conversation_id, name, is_active, created_at, updated_at) in cursor.fetchall():
                conversations.append({
                    'conversation_id': conversation_id,
                    'name': name,
                    'is_active': bool(is_active),
                    'created_at': created_at.isoformat() if created_at else None,
                    'updated_at': updated_at.isoformat() if updated_at else None
                })
                
            cursor.close()
            return conversations
        except Exception as err:
            logger.error(f"获取用户会话时出错: {err}")
            return []
            
    def get_conversation_messages(self, conversation_id: str, limit: int = 100):
        """获取会话的所有消息记录"""
        if not conversation_id:
            return []
            
        if self._memory_mode:
            # 内存模式下遍历所有用户，查找会话所属
            for wallet_address, host_manager in self._host_managers.items():
                conversation = host_manager.get_conversation(conversation_id)
                if conversation:
                    return conversation.messages
            return []
            
        if not self._db_connection:
            return []
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询会话的所有消息
            cursor.execute("""
            SELECT message_id, role, content, created_at
            FROM messages 
            WHERE conversation_id = %s
            ORDER BY created_at ASC
            LIMIT %s
            """, (conversation_id, limit))
            
            messages = []
            for (message_id, role, content, created_at) in cursor.fetchall():
                import json
                message_data = {
                    'message_id': message_id,
                    'role': role,
                    'content': json.loads(content) if content else {},
                    'created_at': created_at.isoformat() if created_at else None
                }
                messages.append(message_data)
                
            cursor.close()
            return messages
        except Exception as err:
            logger.error(f"获取会话消息时出错: {err}")
            return []
            
    def rebuild_conversation_from_history(self, wallet_address: str, conversation_id: str):
        """从历史记录重建会话"""
        if not wallet_address or not conversation_id:
            return None
            
        # 检查会话是否存在
        if wallet_address in self._host_managers:
            host_manager = self._host_managers[wallet_address]
            conversation = host_manager.get_conversation(conversation_id)
            if conversation:
                # 会话已存在，无需重建
                return conversation
                
        # 从数据库获取会话信息
        if self._memory_mode:
            return None
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询会话信息
            cursor.execute("""
            SELECT name, is_active
            FROM conversations 
            WHERE conversation_id = %s AND wallet_address = %s
            """, (conversation_id, wallet_address))
            
            conversation_data = cursor.fetchone()
            if not conversation_data:
                cursor.close()
                return None
                
            name, is_active = conversation_data
            
            # 获取用户的host_manager
            host_manager = self.get_host_manager(wallet_address)
            
            # 创建会话
            from service.types import Conversation
            conversation = Conversation(
                conversation_id=conversation_id,
                name=name,
                is_active=bool(is_active)
            )
            
            # 将会话添加到host_manager
            host_manager._conversations.append(conversation)
            
            # 查询会话的消息
            cursor.execute("""
            SELECT message_id, role, content, created_at
            FROM messages 
            WHERE conversation_id = %s
            ORDER BY created_at ASC
            """, (conversation_id,))
            
            messages = []
            from common.types import Message, TextPart, DataPart, FilePart, FileContent
            
            for (message_id, role, content, created_at) in cursor.fetchall():
                import json
                try:
                    content_data = json.loads(content) if content else {}
                    
                    # 从内容构建消息对象
                    parts = []
                    metadata = {
                        'message_id': message_id,
                        'conversation_id': conversation_id,
                        'wallet_address': wallet_address
                    }
                    
                    # 从完整内容中提取数据
                    if 'metadata' in content_data and isinstance(content_data['metadata'], dict):
                        # 合并额外的元数据
                        for key, value in content_data['metadata'].items():
                            if key not in metadata:  # 避免覆盖重要字段
                                metadata[key] = value
                    
                    # 确定消息角色 - 可能是user或agent/model
                    msg_role = content_data.get('role', role)
                    # 标准化角色名称
                    if msg_role in ['model', 'assistant']:
                        msg_role = 'agent'  # 确保前端统一识别为agent
                    
                    # 处理消息部分
                    if 'parts' in content_data:
                        for part_data in content_data['parts']:
                            # 根据不同类型创建不同的Part对象
                            if isinstance(part_data, dict):
                                part_type = part_data.get('type')
                                
                                if part_type == 'text' and 'text' in part_data:
                                    parts.append(TextPart(text=part_data['text']))
                                
                                elif part_type == 'data' and 'data' in part_data:
                                    parts.append(DataPart(data=part_data['data']))
                                
                                elif part_type == 'file' and 'file' in part_data:
                                    file_content = FileContent(**part_data['file'])
                                    parts.append(FilePart(file=file_content))
                                
                                else:
                                    # 对于未知类型，尝试作为文本处理
                                    text_content = part_data.get('text', str(part_data))
                                    parts.append(TextPart(text=text_content))
                            
                            elif isinstance(part_data, str):
                                parts.append(TextPart(text=part_data))
                    
                    # 如果没有成功解析出任何部分，添加默认文本
                    if not parts:
                        # 尝试从原始内容中提取文本
                        text = content_data.get('text', '无法显示内容')
                        parts.append(TextPart(text=text))
                    
                    # 创建消息对象
                    message = Message(
                        role=msg_role,
                        parts=parts,
                        metadata=metadata
                    )
                    
                    # 调试输出 - 帮助确认消息格式是否正确
                    print(f"重建消息: {message_id}, 角色: {msg_role}, 内容类型: {len(parts)}")
                    
                    messages.append(message)
                except Exception as e:
                    logger.error(f"解析消息时出错: {e}")
            
            # 将消息添加到会话
            conversation.messages = messages
            
            logger.info(f"成功从数据库重建会话 {conversation_id}，共恢复 {len(messages)} 条消息")
            cursor.close()
            return conversation
        except Exception as err:
            logger.error(f"重建会话时出错: {err}")
            return None

    def get_user_conversation_count(self, wallet_address: str) -> int:
        """获取用户的会话数量"""
        if not wallet_address:
            return 0
            
        if self._memory_mode:
            # 内存模式下从host_manager获取
            if wallet_address in self._host_managers:
                return len(self._host_managers[wallet_address].conversations)
            return 0
            
        if not self._db_connection:
            return 0
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询用户的会话数量
            cursor.execute("""
            SELECT COUNT(*) 
            FROM conversations 
            WHERE wallet_address = %s
            """, (wallet_address,))
            
            count = cursor.fetchone()[0]
            cursor.close()
            return count
        except Exception as err:
            logger.error(f"获取用户会话数量时出错: {err}")
            return 0
            
    def delete_conversation(self, wallet_address: str, conversation_id: str) -> bool:
        """删除用户的会话"""
        if not wallet_address or not conversation_id:
            return False
            
        # 获取对应的host_manager
        host_manager = None
        if wallet_address in self._host_managers:
            host_manager = self._host_managers[wallet_address]
            
        # 内存模式下直接从host_manager中删除会话
        if self._memory_mode:
            if not host_manager:
                return False
                
            # 查找并删除会话
            conversations = host_manager._conversations
            for i, conv in enumerate(conversations):
                if conv.conversation_id == conversation_id:
                    del conversations[i]
                    logger.info(f"已删除用户 {wallet_address} 的会话 {conversation_id}")
                    return True
            return False
            
        # 数据库模式
        if not self._db_connection:
            return False
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 首先验证会话是否属于该用户
            cursor.execute("""
            SELECT COUNT(*) 
            FROM conversations 
            WHERE conversation_id = %s AND wallet_address = %s
            """, (conversation_id, wallet_address))
            
            if cursor.fetchone()[0] == 0:
                cursor.close()
                logger.warning(f"用户 {wallet_address} 尝试删除不属于他的会话 {conversation_id}")
                return False
                
            # 删除会话 (数据库级联删除会自动删除关联的消息)
            cursor.execute("""
            DELETE FROM conversations 
            WHERE conversation_id = %s AND wallet_address = %s
            """, (conversation_id, wallet_address))
            
            self._db_connection.commit()
            cursor.close()
            
            # 如果有对应的host_manager，也从内存中删除
            if host_manager:
                conversations = host_manager._conversations
                for i, conv in enumerate(conversations):
                    if conv.conversation_id == conversation_id:
                        del conversations[i]
                        break
                        
            logger.info(f"已删除用户 {wallet_address} 的会话 {conversation_id}")
            return True
        except Exception as err:
            logger.error(f"删除会话时出错: {err}")
            return False

    def limit_conversation_messages(self, wallet_address: str, conversation_id: str, max_messages: int = 10):
        """限制会话消息数量，只保留最新的几条消息"""
        if not wallet_address or not conversation_id:
            return
            
        if self._memory_mode:
            # 内存模式下直接修改host_manager中的会话消息
            if wallet_address in self._host_managers:
                host_manager = self._host_managers[wallet_address]
                conversation = host_manager.get_conversation(conversation_id)
                if conversation and hasattr(conversation, 'messages') and len(conversation.messages) > max_messages:
                    # 只保留最新的max_messages条消息
                    conversation.messages = conversation.messages[-max_messages:]
                    logger.info(f"已限制会话 {conversation_id} 的消息数量为 {max_messages}")
            return
            
        if not self._db_connection:
            return
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询会话的消息数量
            cursor.execute("""
            SELECT COUNT(*) 
            FROM messages 
            WHERE conversation_id = %s
            """, (conversation_id,))
            
            count = cursor.fetchone()[0]
            if count <= max_messages:
                cursor.close()
                return
                
            # 查询需要删除的消息ID
            cursor.execute("""
            SELECT message_id 
            FROM messages 
            WHERE conversation_id = %s 
            ORDER BY created_at ASC 
            LIMIT %s
            """, (conversation_id, count - max_messages))
            
            message_ids = [row[0] for row in cursor.fetchall()]
            
            # 删除多余的消息
            if message_ids:
                placeholders = ', '.join(['%s'] * len(message_ids))
                cursor.execute(f"""
                DELETE FROM messages 
                WHERE message_id IN ({placeholders})
                """, message_ids)
                
                self._db_connection.commit()
                logger.info(f"已删除会话 {conversation_id} 的 {len(message_ids)} 条旧消息，保留最新的 {max_messages} 条")
                
            cursor.close()
            
            # 如果有对应的host_manager，也限制内存中的消息
            if wallet_address in self._host_managers:
                host_manager = self._host_managers[wallet_address]
                conversation = host_manager.get_conversation(conversation_id)
                if conversation and hasattr(conversation, 'messages') and len(conversation.messages) > max_messages:
                    conversation.messages = conversation.messages[-max_messages:]
        except Exception as err:
            logger.error(f"限制会话消息数量时出错: {err}")
    
    def save_task(self, wallet_address: str, task: Task):
        """将任务保存到数据库"""
        if self._memory_mode or not self._db_connection or not wallet_address:
            return
        
        # 确保用户存在
        self._ensure_user_exists(wallet_address)
        
        try:
            # 从任务中提取必要信息
            task_id = task.id
            session_id = task.sessionId
            
            # 尝试从任务元数据或历史消息中获取会话ID
            conversation_id = None
            status_message_id = None
            
            if task.metadata and 'conversation_id' in task.metadata:
                conversation_id = task.metadata['conversation_id']
            
            # 检查状态消息
            if task.status and task.status.message and task.status.message.metadata:
                if 'conversation_id' in task.status.message.metadata and not conversation_id:
                    conversation_id = task.status.message.metadata['conversation_id']
                
                if 'message_id' in task.status.message.metadata:
                    status_message_id = task.status.message.metadata['message_id']
            
            # 如果没有会话ID，尝试从历史消息中获取
            if not conversation_id and task.history:
                for message in task.history:
                    if message.metadata and 'conversation_id' in message.metadata:
                        conversation_id = message.metadata['conversation_id']
                        break
            
            # 如果仍然没有conversation_id，无法保存任务
            if not conversation_id:
                logger.warning(f"无法保存任务 {task_id}，未找到关联的会话ID")
                return
            
            # 检查会话是否存在
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询会话是否存在
            cursor.execute("""
            SELECT conversation_id 
            FROM conversations 
            WHERE conversation_id = %s
            """, (conversation_id,))
            
            if not cursor.fetchone():
                # 会话不存在，可能需要创建
                self.save_conversation(wallet_address, conversation_id)
            
            # 序列化整个任务对象以便存储
            import json
            task_data = json.dumps({
                'id': task.id,
                'sessionId': task.sessionId,
                'status': {
                    'state': task.status.state if task.status else None,
                    'timestamp': task.status.timestamp.isoformat() if task.status and hasattr(task.status, 'timestamp') else None,
                },
                'artifacts': [
                    {
                        'name': artifact.name,
                        'description': artifact.description,
                        'index': artifact.index,
                        'parts': [self._serialize_message_part(part) for part in artifact.parts]
                    } for artifact in (task.artifacts or [])
                ],
                'history': [
                    {
                        'role': message.role,
                        'parts': [self._serialize_message_part(part) for part in message.parts],
                        'metadata': message.metadata
                    } for message in (task.history or [])
                ]
            })
            
            # 尝试插入或更新任务
            cursor.execute("""
            INSERT INTO tasks 
            (task_id, session_id, conversation_id, wallet_address, state, status_message_id, data) 
            VALUES (%s, %s, %s, %s, %s, %s, %s) 
            ON DUPLICATE KEY UPDATE 
            state = VALUES(state), 
            status_message_id = VALUES(status_message_id), 
            data = VALUES(data),
            updated_at = CURRENT_TIMESTAMP
            """, (
                task_id, 
                session_id, 
                conversation_id, 
                wallet_address, 
                task.status.state if task.status else None,
                status_message_id,
                task_data
            ))
            
            # 保存任务制品
            if task.artifacts:
                # 先删除旧的制品记录
                cursor.execute("""
                DELETE FROM task_artifacts WHERE task_id = %s
                """, (task_id,))
                
                # 插入新的制品记录
                for artifact in task.artifacts:
                    # 序列化制品
                    artifact_data = json.dumps({
                        'name': artifact.name,
                        'description': artifact.description,
                        'parts': [self._serialize_message_part(part) for part in artifact.parts]
                    })
                    
                    cursor.execute("""
                    INSERT INTO task_artifacts 
                    (task_id, name, description, data, index_num) 
                    VALUES (%s, %s, %s, %s, %s)
                    """, (
                        task_id,
                        artifact.name,
                        artifact.description,
                        artifact_data,
                        artifact.index
                    ))
            
            self._db_connection.commit()
            cursor.close()
            logger.info(f"已保存任务 {task_id} 到会话 {conversation_id}")
        except Exception as err:
            logger.error(f"保存任务记录时出错: {err}")
    
    def get_conversation_tasks(self, conversation_id: str) -> list:
        """获取会话的任务列表"""
        if not conversation_id:
            return []
            
        if self._memory_mode:
            # 内存模式下无法跨会话获取任务
            return []
            
        if not self._db_connection:
            return []
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询会话的任务
            cursor.execute("""
            SELECT task_id, session_id, state, data, created_at, updated_at 
            FROM tasks 
            WHERE conversation_id = %s 
            ORDER BY updated_at DESC
            """, (conversation_id,))
            
            tasks = []
            for row in cursor.fetchall():
                task_id, session_id, state, data, created_at, updated_at = row
                
                # 反序列化任务数据
                import json
                task_data = json.loads(data) if data else {}
                
                tasks.append({
                    'id': task_id,
                    'sessionId': session_id,
                    'state': state,
                    'created_at': created_at.isoformat() if created_at else None,
                    'updated_at': updated_at.isoformat() if updated_at else None,
                    'data': task_data
                })
            
            cursor.close()
            return tasks
        except Exception as err:
            logger.error(f"获取会话任务时出错: {err}")
            return []
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务记录"""
        if not task_id:
            return False
            
        if self._memory_mode:
            # 内存模式下无法删除任务
            return False
            
        if not self._db_connection:
            return False
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 删除任务记录
            cursor.execute("""
            DELETE FROM tasks WHERE task_id = %s
            """, (task_id,))
            
            affected = cursor.rowcount
            self._db_connection.commit()
            cursor.close()
            
            if affected > 0:
                logger.info(f"已删除任务 {task_id}")
                return True
            else:
                logger.warning(f"任务 {task_id} 不存在")
                return False
        except Exception as err:
            logger.error(f"删除任务时出错: {err}")
            return False 
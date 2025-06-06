import datetime
from datetime import timedelta
import logging
from typing import Dict, Optional, List, Any, Union, Tuple
import os
import threading
import time
import json
import uuid
import sys
import concurrent.futures
import asyncio

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
        """初始化"""
        # 初始化数据库连接
        self._initialize_database()
        # 创建订阅检查器
        self.subscription_checker = UserSubscriptionChecker(self)
        # 创建过期代理清理器
        self.expired_agent_cleaner = ExpiredAgentCleaner(self)
        # 创建代理状态检查器
        self.agent_status_checker = AgentStatusChecker(self)
        # 启动集中式订阅检查器
        self.subscription_checker.start_checker()
        # 启动过期代理清理任务
        self.expired_agent_cleaner.start_cleaner()
        # 启动代理状态检查任务
        self.agent_status_checker.start_checker()
        logger.info(f"用户会话管理器初始化完成，使用{'内存' if self._memory_mode else '数据库'}模式")
        
    def _initialize_database(self):
        """初始化MySQL数据库连接"""
        # 禁用内存模式，强制使用数据库
        self._memory_mode = False
            
        try:
            # 首先尝试连接MySQL服务器（不指定数据库）
            try:
                conn = pymysql.connect(
                    host="localhost",
                    port=3306,
                    user="root",
                    password="orangepi123",
                    connect_timeout=10,  # 增加连接超时设置
                    read_timeout=30,     # 增加读取超时设置
                    write_timeout=30     # 增加写入超时设置
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
                # 不再切换到内存模式，而是抛出异常
                raise Exception(f"数据库连接失败: {err}")
            
            # 现在连接a2a数据库
            self._db_connection = pymysql.connect(
                host="localhost",
                port=3306,
                user="root",
                password="orangepi123",
                database="a2a",
                connect_timeout=10,  # 增加连接超时设置
                read_timeout=30,     # 增加读取超时设置
                write_timeout=30,    # 增加写入超时设置
                autocommit=False     # 显式控制事务
            )
            logger.info("数据库连接成功")
            
            # 创建表结构
            self._create_tables()
        except Exception as err:
            logger.error(f"数据库初始化失败: {err}")
            # 不再切换到内存模式，而是将数据库连接设为None并抛出异常
            self._db_connection = None
            raise Exception(f"数据库初始化失败: {err}")
            
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
                nft_mint_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expire_at TIMESTAMP NULL,
                is_online VARCHAR(10) DEFAULT 'unknown',
                agent_card LONGTEXT NULL,
                FOREIGN KEY (wallet_address) REFERENCES users(wallet_address) ON DELETE CASCADE,
                UNIQUE(wallet_address, nft_mint_id)
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
            
            # 任务历史消息表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                task_id VARCHAR(255),
                role VARCHAR(50),
                content LONGTEXT,
                message_id VARCHAR(255),
                conversation_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
            )
            ''')
            
            self._db_connection.commit()
            cursor.close()
            logger.info("数据库表创建/检查完成")
        except Exception as err:
            logger.error(f"创建表失败: {err}")
            
    
    def get_host_manager(self, wallet_address: str, headers: dict = None) -> ADKHostManager:
        """获取指定用户的Host Manager实例，如果不存在则创建新实例"""
        if not wallet_address:
            logger.warning("尝试获取无效钱包地址的Host Manager")
            # 返回一个临时Host Manager用于匿名访问
            return ADKHostManager(headers=headers)
        
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
            host_manager = ADKHostManager(api_key=api_key, uses_vertex_ai=uses_vertex_ai, headers=headers)
            
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
    
    def _ensure_db_connection(self):
        """确保数据库连接有效"""
        if self._memory_mode:
            return
            
        try:
            # 尝试ping数据库，如果失败则重新连接
            if not self._db_connection:
                logger.warning("数据库连接不存在，尝试重新连接")
                self._initialize_database()
                return
                
            try:
                self._db_connection.ping(reconnect=True)
            except Exception as e:
                logger.warning(f"数据库ping失败: {e}，尝试重新连接")
                self._initialize_database()
        except Exception as e:
            logger.error(f"确保数据库连接时出错: {e}")
            
    
    def _ensure_user_exists(self, wallet_address: str):
        """确保用户在数据库中存在，如果不存在则创建新用户"""
        # 强制使用数据库模式
        self._memory_mode = False
        
        # 确保数据库连接有效
        self._ensure_db_connection()
            
        try:
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
                cursor.execute("UPDATE users SET last_active = UTC_TIMESTAMP() WHERE wallet_address = %s", (wallet_address,))
                self._db_connection.commit()
                
            cursor.close()
        except Exception as err:
            logger.error(f"确保用户存在时出错: {err}")
            # 尝试重新连接数据库
            try:
                self._ensure_db_connection()
                # 重试一次
                cursor = self._db_connection.cursor()
                cursor.execute("SELECT wallet_address FROM users WHERE wallet_address = %s", (wallet_address,))
                result = cursor.fetchone()
                
                if not result:
                    cursor.execute("INSERT INTO users (wallet_address) VALUES (%s)", (wallet_address,))
                    self._db_connection.commit()
                else:
                    cursor.execute("UPDATE users SET last_active = UTC_TIMESTAMP() WHERE wallet_address = %s", (wallet_address,))
                    self._db_connection.commit()
                    
                cursor.close()
            except Exception as retry_err:
                logger.error(f"重试确保用户存在时出错: {retry_err}")
                raise Exception(f"无法确保用户存在: {retry_err}")
                
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
            cursor.execute("SELECT agent_url FROM user_agents WHERE wallet_address = %s and is_online = 'yes'", (wallet_address,))
            
            for (agent_url,) in cursor.fetchall():
                try:
                    logger.info(f"为用户 {wallet_address} 恢复代理: {agent_url}")
                    host_manager.register_agent(agent_url)
                except Exception as e:
                    logger.error(f"恢复代理 {agent_url} 失败: {e}")
                    
            cursor.close()
        except Exception as err:
            logger.error(f"恢复用户代理时出错: {err}")
        
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
            current_time = datetime.datetime.utcnow()
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
            
            # 查询超时的用户 - 使用UTC时间
            utc_inactive_time = datetime.datetime.utcnow() - timedelta(minutes=timeout_minutes)
            logger.info(f"清理活跃时间早于UTC: {utc_inactive_time}的用户")
            
            cursor.execute(
                "SELECT wallet_address FROM users WHERE last_active < %s", 
                (utc_inactive_time,)
            )
            
            for (wallet_address,) in cursor.fetchall():
                # 如果用户有活跃的Host Manager实例，清除它
                if wallet_address in self._host_managers:
                    logger.info(f"清理用户 {wallet_address} 的会话")
                    del self._host_managers[wallet_address]
                    
            cursor.close()
        except Exception as err:
            logger.error(f"清理会话时出错: {err}")
            #
    
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
            
    def get_conversation_messages(self, conversation_id: str, wallet_address: str = None, limit: int = 100):
        """获取会话的所有消息记录
        
        Args:
            conversation_id: 会话ID
            wallet_address: 钱包地址，如果提供则确保消息属于该用户
            limit: 返回消息的最大数量
            
        Returns:
            list: 消息列表
        """
        if not conversation_id:
            return []
            
        if self._memory_mode:
            # 内存模式下遍历所有用户，查找会话所属
            for user_wallet, host_manager in self._host_managers.items():
                # 如果指定了钱包地址，只查找该用户的会话
                if wallet_address and user_wallet != wallet_address:
                    continue
                    
                conversation = host_manager.get_conversation(conversation_id)
                if conversation:
                    # 如果指定了限制，只返回最新的limit条消息
                    if limit and len(conversation.messages) > limit:
                        return conversation.messages[-limit:]
                    return conversation.messages
            return []
            
        if not self._db_connection:
            return []
            
        try:
            self._db_connection.ping(reconnect=True)
            cursor = self._db_connection.cursor()
            
            # 查询会话的所有消息，根据是否提供wallet_address构建不同的查询
            if wallet_address:
                # 同时使用wallet_address和conversation_id查询
                cursor.execute("""
                SELECT message_id, role, content, created_at
                FROM messages 
                WHERE conversation_id = %s AND wallet_address = %s
                ORDER BY created_at ASC
                LIMIT %s
                """, (conversation_id, wallet_address, limit))
            else:
                # 只按conversation_id查询
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
            
            # 保存任务历史消息
            if task.history:
                # # 先删除旧的历史记录
                # cursor.execute("""
                # DELETE FROM task_history WHERE task_id = %s
                # """, (task_id,))
                
                # 使用集合去重，防止保存重复的历史消息
                message_ids_seen = set()
                
                # 插入新的历史记录
                for history_message in task.history:
                    # 跳过没有message_id的消息
                    if not history_message.metadata or 'message_id' not in history_message.metadata:
                        continue
                        
                    # 获取消息ID并检查是否已处理过
                    message_id = history_message.metadata.get('message_id')
                    if message_id in message_ids_seen:
                        logger.info(f"跳过重复的消息ID {message_id} 的保存")
                        continue
                    
                    # 记录已处理的消息ID
                    message_ids_seen.add(message_id)
                    
                    # 序列化消息内容
                    message_content = json.dumps({
                        'role': history_message.role,
                        'parts': [self._serialize_message_part(part) for part in history_message.parts]
                    })
                    
                    # 获取消息元数据
                    message_id = None
                    conversation_id = None
                    if history_message.metadata:
                        message_id = history_message.metadata.get('message_id')
                        conversation_id = history_message.metadata.get('conversation_id')
                    
                    cursor.execute("""
                    INSERT INTO task_history 
                    (task_id, role, content, message_id, conversation_id) 
                    VALUES (%s, %s, %s, %s, %s)
                    """, (
                        task_id,
                        history_message.role,
                        message_content,
                        message_id,
                        conversation_id
                    ))
            
            self._db_connection.commit()
            cursor.close()
            logger.info(f"已保存任务 {task_id} 到会话 {conversation_id}")
        except Exception as err:
            logger.error(f"保存任务记录时出错: {err}")
    
    def get_conversation_tasks(self, conversation_id: str, wallet_address: str = None) -> list:
        """获取会话的任务列表
        
        Args:
            conversation_id: 会话ID
            wallet_address: 钱包地址，如果提供则确保任务属于该用户
            
        Returns:
            list: 任务列表
        """
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
            
            # 构建查询条件
            query = """
            SELECT t.task_id, t.session_id, t.state, t.data, t.created_at, t.updated_at, t.status_message_id
            FROM tasks t
            """
            
            params = []
            
            # 如果有wallet_address，通过会话表关联确保任务属于该用户
            if wallet_address:
                query += """
                JOIN conversations c ON t.conversation_id = c.conversation_id 
                WHERE t.conversation_id = %s AND c.wallet_address = %s
                """
                params = [conversation_id, wallet_address]
            else:
                # 如果没有wallet_address，只按conversation_id过滤
                query += "WHERE t.conversation_id = %s"
                params = [conversation_id]
                
            query += " ORDER BY t.updated_at DESC"
            
            # 执行查询
            cursor.execute(query, params)
            
            tasks = []
            for row in cursor.fetchall():
                task_id, session_id, state, data, created_at, updated_at, status_message_id = row
                
                # 反序列化任务数据
                import json
                task_data = json.loads(data) if data else {}
                
                # 获取任务的历史消息
                cursor.execute("""
                SELECT role, content, message_id, conversation_id 
                FROM task_history 
                WHERE task_id = %s 
                ORDER BY created_at ASC
                """, (task_id,))
                
                history = []
                # 使用集合记录已处理的message_id，防止重复
                processed_message_ids = set()
                
                for history_row in cursor.fetchall():
                    role, content_json, message_id, history_conversation_id = history_row
                    
                    # 跳过已处理的message_id，防止重复
                    if message_id and message_id in processed_message_ids:
                        #logger.info(f"跳过重复的消息ID: {message_id}")
                        continue
                    
                    try:
                        content_data = json.loads(content_json) if content_json else {}
                        history_item = {
                            'role': role,
                            'parts': content_data.get('parts', []),
                            'metadata': {
                                'message_id': message_id,
                                'conversation_id': history_conversation_id
                            } if message_id and history_conversation_id else None
                        }
                        history.append(history_item)
                        
                        # 记录已处理的message_id
                        if message_id:
                            processed_message_ids.add(message_id)
                            
                    except Exception as e:
                        logger.error(f"解析任务历史消息时出错: {e}")
                
                # 添加历史消息到任务数据
                task_data['history'] = history
                
                tasks.append({
                    'id': task_id,
                    'sessionId': session_id,
                    'state': state,
                    'message_id': status_message_id,  # 添加 message_id 字段
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

    def update_user_activity(self, wallet_address: str):
        """更新用户活跃状态并启动订阅检查"""
        # 确保用户存在
        self._ensure_user_exists(wallet_address)
        
        # 更新用户活跃时间
        if self._memory_mode:
            self._memory_users[wallet_address] = datetime.datetime.utcnow()
            logger.debug(f"内存模式下更新用户活跃时间(UTC): {wallet_address[:8] if len(wallet_address) > 8 else wallet_address}")
        elif self._db_connection:
            try:
                self._db_connection.ping(reconnect=True)
                cursor = self._db_connection.cursor()
                cursor.execute(
                    "UPDATE users SET last_active = UTC_TIMESTAMP() WHERE wallet_address = %s",
                    (wallet_address,)
                )
                self._db_connection.commit()
                cursor.close()
                logger.debug(f"数据库模式下更新用户活跃时间(UTC): {wallet_address[:8] if len(wallet_address) > 8 else wallet_address}")
            except Exception as err:
                logger.error(f"更新用户活跃状态时出错: {err}")
        
        # 更新订阅检查器中的用户活跃状态
        self.subscription_checker.update_user_activity(wallet_address)

    async def update_user_subscriptions(self, wallet_address: str):
        """检查并更新用户的NFT订阅状态"""
        if not wallet_address:
            return
            
        logger.info(f"检查用户 {wallet_address} 的NFT订阅状态")
        
        try:
            # 从Solana获取用户的NFT订阅状态
            valid_subscriptions = await self._get_user_valid_subscriptions(wallet_address)
            
            if not valid_subscriptions:
                logger.info(f"用户 {wallet_address} 没有有效的NFT订阅")
                # 清理所有过期的代理
                self._remove_expired_agents(wallet_address)
                return
                
            # 更新数据库中的订阅信息
            self._update_user_agent_subscriptions(wallet_address, valid_subscriptions)
            
            # 清理过期的代理
            self._remove_expired_agents(wallet_address)
            
        except Exception as e:
            logger.error(f"更新用户 {wallet_address} 的NFT订阅时出错: {e}")
            # 如果出错，尝试重新连接数据库
            try:
                self._ensure_db_connection()
            except Exception:
                logger.error("更新用户订阅时出错，无法重新连接数据库")
    
    async def _get_user_valid_subscriptions(self, wallet_address: str):
        """从Solana获取用户有效的NFT订阅
        
        返回格式: [
            {
                'nft_mint_id': 'mint_address',
                'agent_url': 'agent_url',
                'expire_at': datetime对象
            }
        ]
        """
        # 这里需要调用Solana API获取用户的NFT订阅信息
        
        try:
            from utils.solana_verifier import get_user_subscriptions
            # 调用异步函数获取用户的有效订阅列表
            return await get_user_subscriptions(wallet_address)
        except ImportError:
            logger.warning("未找到solana_verifier模块，使用模拟数据")
            return []
    
    def _update_user_agent_subscriptions(self, wallet_address: str, subscriptions: list):
        """更新用户代理的订阅信息"""
        if self._memory_mode:
            # 内存模式下不需要更新数据库
            return
            
        if not self._db_connection:
            logger.warning("数据库未连接，无法更新用户订阅")
            return
            
        try:
            # 确保数据库连接有效
            self._ensure_db_connection()
            
            cursor = self._db_connection.cursor()
            
            # 收集需要检查状态的代理URL
            agents_to_check = []
            
            for sub in subscriptions:
                try:
                    nft_mint_id = sub.get('nft_mint_id')
                    agent_url = sub.get('agent_url')
                    expire_at = sub.get('expire_at')
                    
                    if not all([nft_mint_id, agent_url, expire_at]):
                        continue
                    
                    # 确保expire_at是datetime对象
                    if not isinstance(expire_at, datetime.datetime):
                        # 尝试转换
                        try:
                            if isinstance(expire_at, (int, float)):
                                expire_at = datetime.datetime.fromtimestamp(expire_at)
                            elif isinstance(expire_at, str):
                                expire_at = datetime.datetime.fromisoformat(expire_at)
                            logger.info(f"转换后的过期时间: {expire_at}")
                        except Exception as convert_err:
                            logger.error(f"转换过期时间失败: {convert_err}")
                            continue
                        
                    # 检查该代理是否已存在
                    cursor.execute(
                        "SELECT id FROM user_agents WHERE wallet_address = %s AND nft_mint_id = %s",
                        (wallet_address, nft_mint_id)
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        # 更新现有记录，默认设置为离线，后续检查在线状态
                        try:
                            cursor.execute(
                                """
                                UPDATE user_agents 
                                SET agent_url = %s, expire_at = %s, is_online = 'no'
                                WHERE wallet_address = %s AND nft_mint_id = %s
                                """,
                                (agent_url, expire_at, wallet_address, nft_mint_id)
                            )
                            # 添加到需要检查的代理列表
                            agents_to_check.append((existing[0], agent_url))
                        except Exception as update_err:
                            logger.error(f"更新NFT订阅记录失败: {update_err}")
                            # 尝试使用字符串格式
                            try:
                                expire_at_str = expire_at.strftime('%Y-%m-%d %H:%M:%S')
                                cursor.execute(
                                    """
                                    UPDATE user_agents 
                                    SET agent_url = %s, expire_at = %s, is_online = 'no'
                                    WHERE wallet_address = %s AND nft_mint_id = %s
                                    """,
                                    (agent_url, expire_at_str, wallet_address, nft_mint_id)
                                )
                                
                                # 添加到需要检查的代理列表
                                agents_to_check.append((existing[0], agent_url))
                            except Exception as retry_err:
                                logger.error(f"使用字符串格式更新也失败: {retry_err}")
                                continue
                    else:
                        # 插入新记录，默认设置为离线，后续检查在线状态
                        logger.info(f"插入新NFT订阅: mint={nft_mint_id}, url={agent_url}")
                        try:
                            cursor.execute(
                                """
                                INSERT INTO user_agents 
                                (wallet_address, agent_url, nft_mint_id, expire_at, is_online) 
                                VALUES (%s, %s, %s, %s, 'no')
                                """,
                                (wallet_address, agent_url, nft_mint_id, expire_at)
                            )
                            # 获取插入的记录ID
                            cursor.execute(
                                "SELECT LAST_INSERT_ID()"
                            )
                            new_id = cursor.fetchone()[0]
                            # 添加到需要检查的代理列表
                            agents_to_check.append((new_id, agent_url))
                        except Exception as insert_err:
                            logger.error(f"插入NFT订阅记录失败: {insert_err}")
                            # 尝试使用字符串格式
                            try:
                                expire_at_str = expire_at.strftime('%Y-%m-%d %H:%M:%S')
                                cursor.execute(
                                    """
                                    INSERT INTO user_agents 
                                    (wallet_address, agent_url, nft_mint_id, expire_at, is_online) 
                                    VALUES (%s, %s, %s, %s, 'no')
                                    """,
                                    (wallet_address, agent_url, nft_mint_id, expire_at_str)
                                )
                                logger.info(f"使用字符串格式插入成功: {expire_at_str}")
                                # 获取插入的记录ID
                                cursor.execute(
                                    "SELECT LAST_INSERT_ID()"
                                )
                                new_id = cursor.fetchone()[0]
                                # 添加到需要检查的代理列表
                                agents_to_check.append((new_id, agent_url))
                            except Exception as retry_err:
                                logger.error(f"使用字符串格式插入也失败: {retry_err}")
                                continue
                except Exception as sub_err:
                    logger.error(f"处理单个订阅时出错: {sub_err}")
                    continue
            
            # 提交事务，确保所有代理记录已存储
            try:
                self._db_connection.commit()
                logger.info(f"成功更新用户 {wallet_address} 的订阅信息")
            except Exception as commit_err:
                logger.error(f"提交事务失败: {commit_err}")
                try:
                    self._db_connection.rollback()
                except Exception:
                    pass
                # 如果提交失败，清空需要检查的代理列表
                agents_to_check = []
            
            # 立即检查代理状态，不需要等待定时任务
            if agents_to_check:
                logger.info(f"立即检查 {len(agents_to_check)} 个新添加/更新的代理状态")
                status_updates = []
                
                # 实例化AgentStatusChecker以便使用其检查方法
                status_checker = self.agent_status_checker
                
                # 检查每个代理的状态
                for agent_id, agent_url in agents_to_check:
                    try:
                        # 直接调用状态检查器的方法检查代理状态
                        is_online, agent_card = status_checker._try_check_agent(agent_url)
                        logger.info(f"代理 {agent_url} 在线状态检查结果: {is_online}")
                        
                        # 收集更新信息
                        if agent_card:
                            agent_card_json = json.dumps(agent_card)
                            status_updates.append((is_online, agent_card_json, agent_id))
                            logger.info(f"代理 {agent_url} 成功获取agent card并保存")
                        else:
                            status_updates.append((is_online, None, agent_id))
                            if is_online == 'no':
                                logger.info(f"代理 {agent_url} 不在线，标记为离线状态")
                            else:
                                logger.info(f"代理 {agent_url} 在线但未获取到有效agent card")
                    except Exception as e:
                        logger.error(f"初始检查代理 {agent_url} 状态时出错: {e}")
                        # 出错时标记为离线
                        status_updates.append(('no', None, agent_id))
                        logger.info(f"代理 {agent_url} 检查出错，标记为离线状态")
                        continue
                
                # 批量更新代理状态
                if status_updates:
                    try:
                        # 区分有卡片和无卡片的更新
                        with_cards = [(status, card, id) for status, card, id in status_updates if card is not None]
                        without_cards = [(status, id) for status, card, id in status_updates if card is None]
                        
                        # 更新带卡片数据的代理
                        if with_cards:
                            cursor.executemany(
                                "UPDATE user_agents SET is_online = %s, agent_card = %s WHERE id = %s",
                                with_cards
                            )
                            logger.info(f"更新了 {len(with_cards)} 个带agent card的代理状态")
                        
                        # 更新不带卡片数据的代理
                        if without_cards:
                            cursor.executemany(
                                "UPDATE user_agents SET is_online = %s WHERE id = %s",
                                without_cards
                            )
                            logger.info(f"更新了 {len(without_cards)} 个不带agent card的代理状态")
                        
                        # 提交更新
                        self._db_connection.commit()
                        logger.info(f"成功更新 {len(status_updates)} 个代理的初始状态")
                    except Exception as update_err:
                        logger.error(f"更新代理初始状态时出错: {update_err}")
                        try:
                            self._db_connection.rollback()
                        except Exception:
                            pass
            
            cursor.close()
        except Exception as e:
            logger.error(f"更新用户代理订阅信息时出错: {e}")
            if cursor:
                cursor.close()

    def _remove_expired_agents(self, wallet_address: str):
        """移除过期的代理"""
        logger.info("开始清理过期代理")
        
        # 确保数据库连接有效
        try:
            # 强制使用数据库模式
            self._memory_mode = False
            
            # 确保数据库连接
            self._ensure_db_connection()
            
            if not self._db_connection:
                logger.error("无法连接到数据库，跳过本次清理")
                return
                    
            # 创建游标
            cursor = None
            try:
                cursor = self._db_connection.cursor()
                
                # 查询所有过期的代理
                cursor.execute(
                    """
                    SELECT wallet_address, agent_url, nft_mint_id 
                    FROM user_agents 
                    WHERE expire_at IS NOT NULL AND expire_at < CURRENT_TIMESTAMP
                    """
                )
                
                expired_agents = cursor.fetchall()
                if not expired_agents:
                    logger.info("未发现过期代理")
                    return
                    
                logger.info(f"发现 {len(expired_agents)} 个过期代理，准备清理")
                
                # 删除过期的代理
                cursor.execute(
                    """
                    DELETE FROM user_agents 
                    WHERE expire_at IS NOT NULL AND expire_at < CURRENT_TIMESTAMP
                    """
                )
                
                deleted_count = cursor.rowcount
                self._db_connection.commit()
                
                logger.info(f"已清理 {deleted_count} 个过期代理")
                
                # 重新加载受影响用户的代理列表
                affected_wallets = set()
                for wallet_address, _, _ in expired_agents:
                    affected_wallets.add(wallet_address)
                    
                for wallet_address in affected_wallets:
                    if wallet_address in self._host_managers:
                        logger.info(f"重新加载用户 {wallet_address} 的代理列表")
                        self.refresh_user_agents(wallet_address)
            except Exception as e:
                logger.error(f"清理过期代理操作失败: {e}")
                # 如果是事务中，尝试回滚
                try:
                    if self._db_connection:
                        self._db_connection.rollback()
                except Exception:
                    pass
                
                # 尝试重新连接数据库
                self._ensure_db_connection()
            finally:
                # 确保游标关闭
                try:
                    if cursor:
                        cursor.close()
                except Exception:
                    pass
        except Exception as err:
            logger.error(f"清理过期代理时出错: {err}")
            

    def get_agent_status(self, wallet_address: str = None) -> List[Dict[str, Any]]:
        """
        获取代理状态信息
        
        Args:
            wallet_address: 可选，指定钱包地址。如果不提供，则获取所有代理状态
            
        Returns:
            List[Dict[str, Any]]: 代理状态信息列表
        """
        if self._memory_mode:
            logger.warning("内存模式下不支持获取代理状态")
            return []
            
        try:
            # 确保数据库连接有效
            self._ensure_db_connection()
            
            cursor = self._db_connection.cursor()
            
            if wallet_address:
                # 获取指定钱包地址的代理状态
                cursor.execute(
                    """
                    SELECT nft_mint_id, agent_url, is_online, agent_card, expire_at 
                    FROM user_agents 
                    WHERE wallet_address = %s
                    """,
                    (wallet_address,)
                )
            else:
                # 获取所有代理状态
                cursor.execute(
                    """
                    SELECT wallet_address, nft_mint_id, agent_url, is_online, agent_card, expire_at 
                    FROM user_agents
                    """
                )
            
            results = []
            for row in cursor.fetchall():
                if wallet_address:
                    nft_mint_id, agent_url, is_online, agent_card_json, expire_at = row
                    agent_info = {
                        'nft_mint_id': nft_mint_id,
                        'agent_url': agent_url,
                        'is_online': is_online,
                        'expire_at': expire_at
                    }
                else:
                    wallet_address_db, nft_mint_id, agent_url, is_online, agent_card_json, expire_at = row
                    agent_info = {
                        'wallet_address': wallet_address_db,
                        'nft_mint_id': nft_mint_id,
                        'agent_url': agent_url,
                        'is_online': is_online,
                        'expire_at': expire_at
                    }
                
                # 解析agent_card
                if agent_card_json:
                    try:
                        agent_info['agent_card'] = json.loads(agent_card_json)
                    except:
                        logger.warning(f"解析代理卡片JSON失败: {agent_card_json[:100]}...")
                
                results.append(agent_info)
            
            cursor.close()
            return results
            
        except Exception as e:
            logger.error(f"获取代理状态时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return []

    def queryAgentsByAddress(self, wallet_address: str) -> List[Dict[str, Any]]:
        """
        从数据库查询用户的所有代理信息
        
        Args:
            wallet_address: 用户钱包地址
            
        Returns:
            List[Dict[str, Any]]: 代理信息列表，包含在线状态、过期时间等
        """
        logger.info(f"查询用户 {wallet_address} 的代理信息")
        
            
        try:
            # 确保数据库连接有效
            self._ensure_db_connection()
            
            cursor = self._db_connection.cursor()
            
            # 从数据库获取代理信息
            cursor.execute(
                """
                SELECT nft_mint_id, agent_url, is_online, agent_card, expire_at 
                FROM user_agents 
                WHERE wallet_address = %s
                """,
                (wallet_address,)
            )
            
            results = []
            for row in cursor.fetchall():
                nft_mint_id, agent_url, is_online, agent_card_json, expire_at = row
                
                # 创建基本信息
                agent_info = {
                    'nft_mint_id': nft_mint_id,
                    'url': agent_url,  # 使用URL作为标准字段
                    'is_online': is_online,
                    'expire_at': expire_at.isoformat() if expire_at else None
                }
                
                # 解析agent_card JSON
                if agent_card_json:
                    try:
                        card_data = json.loads(agent_card_json)
                        # 合并agent_card中的字段到结果中
                        agent_info.update(card_data)
                    except Exception as e:
                        logger.warning(f"解析代理卡片JSON失败: {str(e)}")
                        # 确保包含基本字段
                        if 'name' not in agent_info:
                            agent_info['name'] = f"Agent ({agent_url})"
                        if 'description' not in agent_info:
                            agent_info['description'] = "No description available"
                else:
                    # 为缺少card数据的agent提供默认值
                    agent_info['name'] = f"Agent ({agent_url})"
                    agent_info['description'] = "No description available"
                    agent_info['capabilities'] = {
                        'streaming': True,
                        'pushNotifications': False,
                        'stateTransitionHistory': False
                    }
                
                results.append(agent_info)
            
            cursor.close()
            logger.info(f"为用户 {wallet_address} 查询到 {len(results)} 个代理")
            return results
            
        except Exception as e:
            logger.error(f"查询用户代理信息时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return []

    def force_mark_agent_online(self, agent_url: str) -> bool:
        """
        强制将指定URL的代理标记为在线
        
        Args:
            agent_url: 代理URL
            
        Returns:
            bool: 操作是否成功
        """
        logger.info(f"手动将代理 {agent_url} 标记为在线")
        
        if self._memory_mode:
            logger.warning("内存模式下不支持修改代理状态")
            return False
            
        try:
            # 确保数据库连接有效
            self._ensure_db_connection()
            
            cursor = self._db_connection.cursor()
            
            # 查询匹配的代理
            cursor.execute(
                "SELECT id FROM user_agents WHERE agent_url = %s OR agent_url LIKE %s",
                (agent_url, f"%{agent_url}%")
            )
            
            agents = cursor.fetchall()
            if not agents:
                logger.warning(f"未找到URL包含 {agent_url} 的代理")
                cursor.close()
                return False
                
            updated_count = 0
            for (agent_id,) in agents:
                # 更新代理状态为在线
                cursor.execute(
                    "UPDATE user_agents SET is_online = 'yes' WHERE id = %s",
                    (agent_id,)
                )
                updated_count += 1
                
            self._db_connection.commit()
            cursor.close()
            
            logger.info(f"成功将 {updated_count} 个代理标记为在线")
            return True
            
        except Exception as e:
            logger.error(f"标记代理在线状态时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False

class UserSubscriptionChecker:
    """用户NFT订阅检查的定时任务管理器"""
    
    def __init__(self, user_session_manager):
        self.user_session_manager = user_session_manager
        self.timer_thread = None
        self.stop_flag = False
        self.lock = threading.Lock()  # 线程锁，确保线程安全
        self.scan_interval = 60  # 扫描间隔，单位秒，默认3分钟
        self.activity_threshold = 20  # 活跃用户阈值，单位分钟
        
    def start_checker(self):
        """启动集中式订阅检查任务"""
        with self.lock:
            if self.timer_thread and self.timer_thread.is_alive():
                logger.debug("集中式订阅检查任务已在运行")
                return
                
            # 设置停止标志为False
            self.stop_flag = False
            
            # 创建并启动定时任务线程
            self.timer_thread = threading.Thread(
                target=self._checker_task,
                daemon=True,  # 设置为守护线程，主程序退出时自动结束
                name="SubscriptionChecker"  # 添加线程名称便于调试
            )
            self.timer_thread.start()
            
            logger.info(f"已启动集中式订阅检查任务，扫描间隔: {self.scan_interval}秒，活跃用户阈值: {self.activity_threshold}分钟")
    
    def stop_checker(self):
        """停止检查任务"""
        with self.lock:
            if not self.timer_thread or not self.timer_thread.is_alive():
                logger.debug("集中式订阅检查任务未在运行")
                return
                
            self.stop_flag = True
            logger.debug("已标记停止集中式订阅检查任务")
            
            # 等待线程结束，最多等待10秒
            self.timer_thread.join(timeout=10)
            
            # 确认线程已停止
            if not self.timer_thread.is_alive():
                logger.info("集中式订阅检查任务已停止")
            else:
                logger.warning("集中式订阅检查任务可能未正常停止")
    
    def update_user_activity(self, wallet_address: str):
        """更新用户最后活跃时间
        
        此方法保留用户活跃度更新功能，但不再触发单独的检查线程
        """
        # 由于不再使用单独的线程，此方法现在什么都不做
        # 用户活跃度更新在UserSessionManager.update_user_activity中完成
        pass
    
    def _checker_task(self):
        """集中式检查任务的执行函数"""
        next_check_time = time.time()  # 初始化下一次检查时间
        
        while True:
            # 检查是否需要停止
            with self.lock:
                if self.stop_flag:
                    logger.debug("集中式订阅检查任务已停止")
                    return
            
            # 精确控制执行间隔
            current_time = time.time()
            if current_time < next_check_time:
                # 如果还没到下一次检查时间，等待适当的时间
                sleep_time = min(next_check_time - current_time, 2)  # 最多等待5秒，以便及时响应停止请求
                time.sleep(sleep_time)
                continue
                
            # 记录开始时间
            start_time = time.time()
            
            try:
                # 获取活跃用户并检查订阅
                self._check_active_users()
                
                # 计算下一次检查时间，考虑执行时间
                execution_time = time.time() - start_time
                next_check_time = start_time + self.scan_interval
                
                # 记录执行时间，用于监控 - 使用UTC时间保持与数据库一致
                next_check_utc = datetime.datetime.utcfromtimestamp(next_check_time)
                logger.info(f"集中式订阅检查完成，耗时: {execution_time:.2f}秒，下次检查UTC时间: {next_check_utc}")
                
            except Exception as e:
                logger.error(f"执行集中式订阅检查任务时出错: {e}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
                
                # 出错后等待一段时间再次尝试
                next_check_time = time.time() + 60  # 出错后1分钟后重试
    
    def _check_active_users(self):
        """检查所有活跃用户的订阅状态"""
        # 只在数据库模式下执行，内存模式不支持此功能
        if self.user_session_manager._memory_mode:
            logger.debug("内存模式下不支持集中式订阅检查")
            return
        
        if not self.user_session_manager._db_connection:
            logger.warning("数据库未连接，无法执行集中式订阅检查")
            return
            
        try:
            # 确保数据库连接有效
            self.user_session_manager._ensure_db_connection()
            
            cursor = self.user_session_manager._db_connection.cursor()
            
            # 查询活跃用户 - 最近30分钟内活跃的用户
            # 使用UTC时间与数据库中的时间进行比较
            active_time_threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=self.activity_threshold)
            
            logger.info(f"查询活跃用户，UTC时间阈值: {active_time_threshold}")
            
            cursor.execute(
                "SELECT wallet_address FROM users WHERE last_active > %s",
                (active_time_threshold,)
            )
            
            active_users = cursor.fetchall()
            cursor.close()
            
            if not active_users:
                logger.info(f"未找到最近{self.activity_threshold}分钟内活跃的用户")
                return
                
            logger.info(f"找到{len(active_users)}个活跃用户，开始检查订阅")
            
            # 使用线程池处理用户订阅检查
            max_workers = min(10, len(active_users))  # 最多10个线程，避免过多并发
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有活跃用户的订阅检查任务
                futures = []
                for (wallet_address,) in active_users:
                    future = executor.submit(self._check_user_subscription_wrapper, wallet_address)
                    futures.append(future)
                
                # 等待所有任务完成，但设置总超时时间
                done, not_done = concurrent.futures.wait(
                    futures,
                    timeout=120,  # 总超时时间2分钟
                    return_when=concurrent.futures.ALL_COMPLETED
                )
                
                # 处理未完成的任务
                if not_done:
                    logger.warning(f"{len(not_done)}个用户订阅检查任务未在超时时间内完成")
                    
            logger.info(f"完成所有活跃用户的订阅检查，共{len(active_users)}个用户")
                
        except Exception as e:
            logger.error(f"检查活跃用户订阅状态时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
    
    def _check_user_subscription_wrapper(self, wallet_address: str):
        """包装异步订阅检查函数，使其可以在线程池中运行"""
        try:
            # 创建一个事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 在事件循环中运行异步订阅检查
                async def check_with_timeout():
                    try:
                        # 30秒超时
                        await asyncio.wait_for(
                            self.user_session_manager.update_user_subscriptions(wallet_address),
                            timeout=30.0
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"检查用户 {wallet_address} NFT订阅超时")
                    except Exception as e:
                        logger.error(f"检查用户 {wallet_address} NFT订阅时出错: {e}")
                
                # 执行带超时的异步检查
                loop.run_until_complete(check_with_timeout())
                
            finally:
                # 清理事件循环资源
                try:
                    # 取消所有挂起任务
                    pending = asyncio.all_tasks(loop)
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                except Exception as e:
                    logger.error(f"清理事件循环任务时出错: {e}")
                finally:
                    # 关闭事件循环
                    loop.close()
                    
        except Exception as e:
            logger.error(f"检查用户 {wallet_address} 的订阅包装函数出错: {e}")

class ExpiredAgentCleaner:
    """定时清理过期代理的任务管理器"""
    
    def __init__(self, user_session_manager):
        self.user_session_manager = user_session_manager
        self.timer_thread = None
        self.stop_flag = False
        self.lock = threading.Lock()
        self.interval = 30  # 每30秒扫描一次
        
    def start_cleaner(self):
        """启动清理任务"""
        with self.lock:
            if self.timer_thread and self.timer_thread.is_alive():
                logger.debug("过期代理清理任务已在运行")
                return
                
            # 设置停止标志为False
            self.stop_flag = False
            
            # 创建并启动定时任务线程
            self.timer_thread = threading.Thread(
                target=self._cleaner_task,
                daemon=True  # 设置为守护线程，主程序退出时自动结束
            )
            self.timer_thread.start()
            
            logger.debug(f"已启动过期代理清理任务，间隔: {self.interval}秒")
    
    def stop_cleaner(self):
        """停止清理任务"""
        with self.lock:
            self.stop_flag = True
            logger.debug("已标记停止过期代理清理任务")
    
    def _cleaner_task(self):
        """清理任务的执行函数"""
        while True:
            # 检查是否需要停止
            with self.lock:
                if self.stop_flag:
                    logger.debug("过期代理清理任务已停止")
                    return
            
            try:
                # 执行清理过期代理的操作
                self._clean_expired_agents()
            except Exception as e:
                logger.error(f"清理过期代理时出错: {e}")
            
            # 等待指定的时间间隔
            time.sleep(self.interval)
    
    def _clean_expired_agents(self):
        """清理所有过期的代理"""
        logger.info("开始清理过期代理")
        
        # 确保数据库连接有效
        try:
            # 强制使用数据库模式
            self.user_session_manager._memory_mode = False
            
            # 确保数据库连接
            self.user_session_manager._ensure_db_connection()
            
            if not self.user_session_manager._db_connection:
                logger.error("无法连接到数据库，跳过本次清理")
                return
                    
            # 创建游标
            cursor = None
            try:
                cursor = self.user_session_manager._db_connection.cursor()
                
                # 查询所有过期的代理
                cursor.execute(
                    """
                    SELECT wallet_address, agent_url, nft_mint_id 
                    FROM user_agents 
                    WHERE expire_at IS NOT NULL AND expire_at < CURRENT_TIMESTAMP
                    """
                )
                
                expired_agents = cursor.fetchall()
                if not expired_agents:
                    logger.info("未发现过期代理")
                    return
                    
                logger.info(f"发现 {len(expired_agents)} 个过期代理，准备清理")
                
                # 删除过期的代理
                cursor.execute(
                    """
                    DELETE FROM user_agents 
                    WHERE expire_at IS NOT NULL AND expire_at < CURRENT_TIMESTAMP
                    """
                )
                
                deleted_count = cursor.rowcount
                self.user_session_manager._db_connection.commit()
                
                logger.info(f"已清理 {deleted_count} 个过期代理")
                
                # 重新加载受影响用户的代理列表
                affected_wallets = set()
                for wallet_address, _, _ in expired_agents:
                    affected_wallets.add(wallet_address)
                    
                for wallet_address in affected_wallets:
                    if wallet_address in self.user_session_manager._host_managers:
                        logger.info(f"重新加载用户 {wallet_address} 的代理列表")
                        self.user_session_manager.refresh_user_agents(wallet_address)
            except Exception as e:
                logger.error(f"清理过期代理操作失败: {e}")
                # 如果是事务中，尝试回滚
                try:
                    if self.user_session_manager._db_connection:
                        self.user_session_manager._db_connection.rollback()
                except Exception:
                    pass
                
                # 尝试重新连接数据库
                self.user_session_manager._ensure_db_connection()
            finally:
                # 确保游标关闭
                try:
                    if cursor:
                        cursor.close()
                except Exception:
                    pass
        except Exception as err:
            logger.error(f"清理过期代理时出错: {err}")


class AgentStatusChecker:
    """代理状态检查的定时任务管理器"""
    
    def __init__(self, user_session_manager):
        self.user_session_manager = user_session_manager
        self.timer_thread = None
        self.stop_flag = False
        self.lock = threading.Lock()
        self.interval = 30  # 增加到300秒检查一次，减少检查频率
        self.max_retries = 1  # 检查失败时最大重试次数
        self.retry_delay = 2  # 重试间隔(秒)
        self.last_check_time = {}  # 记录每个代理最后一次检查时间
        self.agent_failures = {}  # 记录每个代理连续失败次数
        self.stable_agents = set()  # 记录稳定的代理，这些代理可以降低检查频率

    def start_checker(self):
        """启动检查任务"""
        with self.lock:
            if self.timer_thread and self.timer_thread.is_alive():
                logger.debug("代理状态检查任务已在运行")
                return
                
            # 设置停止标志为False
            self.stop_flag = False
            
            # 创建并启动定时任务线程
            self.timer_thread = threading.Thread(
                target=self._checker_task,
                daemon=True,  # 设置为守护线程，主程序退出时自动结束
                name="AgentStatusChecker"  # 添加线程名称便于调试
            )
            self.timer_thread.start()
            
            logger.debug(f"已启动代理状态检查任务，间隔: {self.interval}秒")
    
    def stop_checker(self):
        """停止检查任务"""
        with self.lock:
            if not self.timer_thread or not self.timer_thread.is_alive():
                logger.debug("代理状态检查任务未在运行")
                return
                
            self.stop_flag = True
            logger.debug("已标记停止代理状态检查任务")
            
            # 等待线程结束，最多等待10秒
            self.timer_thread.join(timeout=10)
            
            # 确认线程已停止
            if not self.timer_thread.is_alive():
                logger.info("代理状态检查任务已停止")
            else:
                logger.warning("代理状态检查任务可能未正常停止")
    
    def restart_checker(self):
        """重启检查任务"""
        self.stop_checker()
        # 确保完全停止
        time.sleep(1)
        self.start_checker()
        logger.debug("代理状态检查任务已重启")
    
    def _checker_task(self):
        """检查任务的执行函数"""
        next_check_time = time.time()  # 初始化下一次检查时间
        
        while True:
            # 检查是否需要停止
            with self.lock:
                if self.stop_flag:
                    logger.debug("代理状态检查任务已停止")
                    return
            
            # 精确控制执行间隔
            current_time = time.time()
            if current_time < next_check_time:
                # 如果还没到下一次检查时间，等待适当的时间
                sleep_time = min(next_check_time - current_time, 2)  # 最多等待5秒，以便及时响应停止请求
                time.sleep(sleep_time)
                continue
                
            # 记录开始时间
            start_time = time.time()
            
            try:
                # 使用超时控制，避免检查过程阻塞太久
                check_timeout = self.interval * 0.8  # 使用80%的间隔时间作为超时限制
                
                # 启动一个守护线程执行检查
                check_thread = threading.Thread(
                    target=self._check_all_agents,
                    daemon=True,
                    name="AgentStatusCheck"
                )
                check_thread.start()
                
                # 等待检查完成，但不超过超时时间
                check_thread.join(timeout=check_timeout)
                
                if check_thread.is_alive():
                    logger.warning(f"代理状态检查超时（超过{check_timeout}秒），将在下一周期继续")
                    # 不需要强制终止线程，因为它是守护线程
            except Exception as e:
                logger.error(f"执行代理状态检查任务时出错: {e}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
            
            # 计算下一次检查时间，保持固定间隔
            next_check_time = start_time + self.interval
    
    def _check_all_agents(self):
        """检查所有代理的状态"""
        logger.debug("开始检查所有代理状态")
        
        if self.user_session_manager._memory_mode:
            logger.warning("内存模式下不支持代理状态检查")
            return
            
        try:
            # 确保数据库连接有效
            self.user_session_manager._ensure_db_connection()
            
            cursor = self.user_session_manager._db_connection.cursor()
            
            # 获取所有代理，直接从数据库中获取而不依赖内存中的agent列表
            cursor.execute("SELECT id, agent_url, is_online FROM user_agents")
            agents = cursor.fetchall()
            
            logger.debug(f"找到 {len(agents)} 个代理需要检查状态")
            
            # 批量更新状态，避免频繁提交事务
            updates = []
            
            for agent_id, agent_url, current_status in agents:
                try:
                    # 检查代理状态，设置明确的超时时间
                    is_online, agent_card = self._check_agent_status(agent_url)
                    
                    # 只有状态真正变化时才更新数据库
                    if self._status_changed(current_status, is_online):
                        logger.info(f"代理 {agent_url} 状态变化: {current_status} -> {is_online}")
                        
                        # 收集更新信息
                        if agent_card:
                            agent_card_json = json.dumps(agent_card)
                            updates.append((is_online, agent_card_json, agent_id))
                        else:
                            updates.append((is_online, None, agent_id))
                    else:
                        logger.debug(f"代理 {agent_url} 状态未变: {is_online}")
                        
                except Exception as e:
                    logger.error(f"检查代理 {agent_url} 状态时出错: {e}")
                    continue
            
            # 批量执行更新，只在有状态变化时
            if updates:
                logger.debug(f"有 {len(updates)} 个代理状态需要更新")
                with_cards = [(status, card, id) for status, card, id in updates if card is not None]
                without_cards = [(status, id) for status, card, id in updates if card is None]
                
                # 更新带卡片数据的代理
                if with_cards:
                    cursor.executemany(
                        "UPDATE user_agents SET is_online = %s, agent_card = %s WHERE id = %s",
                        with_cards
                    )
                
                # 更新不带卡片数据的代理
                if without_cards:
                    cursor.executemany(
                        "UPDATE user_agents SET is_online = %s WHERE id = %s",
                        without_cards
                    )
                
                # 提交事务
                self.user_session_manager._db_connection.commit()
            else:
                logger.debug("没有代理状态变化，跳过数据库更新")
            
            cursor.close()
            
            logger.debug("完成所有代理状态检查")
            
        except Exception as e:
            logger.error(f"检查代理状态过程中出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            
    def _status_changed(self, old_status, new_status):
        """
        判断代理状态是否真正变化
        
        Args:
            old_status: 旧状态 ('yes', 'no', 'unknown')
            new_status: 新状态 ('yes', 'no')
            
        Returns:
            bool: 如果状态真正变化则返回True，否则返回False
        """
        # 如果原状态是unknown，则总是需要更新
        if old_status == 'unknown':
            return True
            
        # 如果新旧状态不同，则需要更新
        if old_status != new_status:
            return True
            
        # 其他情况则不需要更新
        return False
    
    def _check_agent_status(self, agent_url):
        """
        检查单个代理的状态，带有重试机制
        
        Args:
            agent_url: 代理URL
            
        Returns:
            tuple: (is_online, agent_card)
                is_online: 'yes' 或 'no'
                agent_card: 代理卡片数据，如果获取失败则为None
        """
        # 对于稳定的代理，降低检查频率
        if agent_url in self.stable_agents:
            # 如果最后一次检查时间存在且在60秒内，则跳过检查，保持上次状态
            now = time.time()
            if agent_url in self.last_check_time and now - self.last_check_time[agent_url] < 300:  # 5分钟
                logger.debug(f"代理 {agent_url} 为稳定代理，跳过此次检查")
                return 'yes', None
        
        # 记录当前检查时间
        self.last_check_time[agent_url] = time.time()
        
        # 首次尝试
        result = self._try_check_agent(agent_url)
        
        # 如果失败且配置了重试，进行重试
        if result[0] == 'no' and self.max_retries > 0:
            # 更新失败计数
            self.agent_failures[agent_url] = self.agent_failures.get(agent_url, 0) + 1
            
            # 进行重试
            for retry in range(self.max_retries):
                logger.debug(f"代理 {agent_url} 检查失败，进行第 {retry+1}/{self.max_retries} 次重试")
                
                # 等待一段时间后重试
                time.sleep(self.retry_delay)
                
                # 重试检查
                retry_result = self._try_check_agent(agent_url)
                
                # 如果重试成功，则使用重试结果
                if retry_result[0] == 'yes':
                    # 重置失败计数
                    self.agent_failures[agent_url] = 0
                    
                    # 如果连续成功多次，标记为稳定代理
                    if agent_url not in self.stable_agents and self.agent_failures.get(agent_url, 0) == 0:
                        self.stable_agents.add(agent_url)
                        logger.debug(f"代理 {agent_url} 被标记为稳定代理")
                    
                    return retry_result
        
        # 如果代理连续成功，标记为稳定代理
        if result[0] == 'yes':
            # 重置失败计数
            self.agent_failures[agent_url] = 0
            
            # 如果连续成功多次，标记为稳定代理
            if agent_url not in self.stable_agents and self.agent_failures.get(agent_url, 0) == 0:
                self.stable_agents.add(agent_url)
                logger.debug(f"代理 {agent_url} 被标记为稳定代理")
        # 如果连续失败次数过多，从稳定代理列表中移除
        elif agent_url in self.stable_agents and self.agent_failures.get(agent_url, 0) >= 3:
            self.stable_agents.remove(agent_url)
            logger.debug(f"代理 {agent_url} 因连续失败而从稳定代理列表中移除")
        
        return result
    
    def _try_check_agent(self, agent_url):
        """
        尝试检查代理状态的实际实现
        
        Args:
            agent_url: 代理URL
            
        Returns:
            tuple: (is_online, agent_card)
        """
        try:
            import requests
            
            logger.debug(f"正在检查代理状态: {agent_url}")
            
            # 构建.well-known/agent.json URL
            agent_json_url = self._build_agent_json_url(agent_url)
            logger.debug(f"请求agent.json URL: {agent_json_url}")
            
            # 设置较短的超时时间，避免长时间等待
            # 连接超时2秒，读取超时3秒
            response = requests.get(agent_json_url, timeout=(2, 3))
            
            if response.status_code == 200:
                try:
                    # 尝试解析JSON响应
                    agent_card = response.json()
                    
                    # 验证是否是有效的agent card
                    if isinstance(agent_card, dict) and 'name' in agent_card and 'description' in agent_card:
                        logger.debug(f"代理 {agent_url} 在线，获取到有效的agent card")
                        return 'yes', agent_card
                    else:
                        logger.debug(f"代理 {agent_url} 在线，但返回的不是有效的agent card格式")
                        return 'yes', None
                except Exception as json_err:
                    # 响应不是有效的JSON
                    logger.debug(f"代理 {agent_url} 返回的不是有效的JSON: {json_err}")
                    return 'yes', None
            else:
                # 响应状态码不是200
                logger.debug(f"代理 {agent_url} 返回状态码: {response.status_code}")
                return 'no', None
                
        except requests.exceptions.Timeout:
            # 请求超时
            logger.debug(f"请求代理 {agent_url} 超时")
            return 'no', None
        except requests.exceptions.ConnectionError:
            # 连接错误
            logger.debug(f"连接代理 {agent_url} 失败")
            return 'no', None
        except Exception as e:
            # 其他错误
            logger.warning(f"请求代理 {agent_url} 时发生未知错误: {e}")
            return 'no', None
    
    def _build_agent_json_url(self, agent_url):
        """
        构建获取agent.json的完整URL
        
        Args:
            agent_url: 基础代理URL
            
        Returns:
            str: agent.json的完整URL
        """
        # 清理URL中可能的@前缀
        if agent_url.startswith('@'):
            agent_url = agent_url[1:]
            
        # 检查URL是否已包含.well-known/agent.json
        if "/.well-known/agent.json" in agent_url:
            return agent_url
            
        # 确保地址以/结尾
        if not agent_url.endswith("/"):
            agent_url += "/"
            
        # 拼接.well-known/agent.json
        agent_url += ".well-known/agent.json"
        
        # 确保使用http://开头的URL
        if not (agent_url.startswith("http://") or agent_url.startswith("https://")):
            agent_url = "http://" + agent_url
            
        return agent_url

# 命令行工具功能
async def cli_mark_agent_online(agent_url):
    """命令行工具：将代理标记为在线"""
    manager = UserSessionManager.get_instance()
    result = manager.force_mark_agent_online(agent_url)
    if result:
        print(f"成功将代理 {agent_url} 标记为在线")
    else:
        print(f"标记代理 {agent_url} 为在线失败")
    return result

# 如果直接运行此文件，则执行命令行功能
if __name__ == "__main__":
    import sys
    import asyncio
    
    if len(sys.argv) < 2:
        print("用法: python user_session_manager.py mark_online <agent_url>")
        sys.exit(1)
        
    command = sys.argv[1]
    
    if command == "mark_online":
        if len(sys.argv) < 3:
            print("错误: 请提供代理URL")
            print("用法: python user_session_manager.py mark_online <agent_url>")
            sys.exit(1)
            
        agent_url = sys.argv[2]
        asyncio.run(cli_mark_agent_online(agent_url))
    else:
        print(f"未知命令: {command}")
        print("可用命令: mark_online")
        sys.exit(1)
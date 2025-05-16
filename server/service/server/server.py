import asyncio
import base64
import threading
import os
import uuid
import logging
import json
from typing import Any, Optional
from fastapi import APIRouter
from fastapi import Request, Response, WebSocket, WebSocketDisconnect
from common.types import Message, Task, TextPart, DataPart, FilePart, FileContent, TaskStatus, TaskState, Artifact
from .in_memory_manager import InMemoryFakeAgentManager
from .application_manager import ApplicationManager
from .adk_host_manager import ADKHostManager, get_message_id
from .user_session_manager import UserSessionManager
from .websocket_manager import WebSocketManager
from service.types import (
    Conversation,
    Event,
    CreateConversationResponse,
    ListConversationResponse,
    SendMessageResponse,
    MessageInfo,
    ListMessageResponse,
    PendingMessageResponse,
    ListTaskResponse,
    RegisterAgentResponse,
    ListAgentResponse,
    GetEventResponse,
    ExtendedAgentCard
)
import secrets
import re
import dotenv
import hashlib
from fastapi import FastAPI, APIRouter, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Awaitable, Callable, List, Optional, Tuple, Union, Dict
import datetime
from concurrent.futures import ThreadPoolExecutor
import sys
import time
from utils.solana_verifier import solana_verifier, sdk_available
from hosts.multiagent.remote_agent_connection import (
    TaskCallbackArg,
)
from utils.agent_card import get_agent_card
from google.adk import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationServer:
  """ConversationServer是用于在UI中提供代理交互的后端

  这定义了Mesop系统用于与代理交互和提供有关执行详细信息的接口。
  现在支持多用户，每个用户有独立的代理环境。
  """
  def __init__(self, router: APIRouter):
    agent_manager = os.environ.get("A2A_HOST", "ADK")
    self.default_manager: ApplicationManager
    self.use_multi_user = True  # 启用多用户模式
    
    # 获取WebSocket管理器实例
    self.ws_manager = WebSocketManager.get_instance()
    
    # 获取API密钥环境变量
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        # 如果环境变量中没有API密钥，设置一个默认值以避免会话错误
        api_key = "default_key_placeholder"
        os.environ["GOOGLE_API_KEY"] = api_key
        logger.warning("未设置API密钥，使用占位符。某些功能可能不可用。")
    
    uses_vertex_ai = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
    
    # 日志记录API设置
    if uses_vertex_ai:
      logger.info("使用Vertex AI认证")
    elif api_key:
      # 隐藏完整的API key，只显示前5位和后5位
      masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***"
      logger.info(f"使用API Key认证: {masked_key}")
    
    # 初始化默认管理器
    if agent_manager.upper() == "ADK":
      self.default_manager = ADKHostManager(api_key=api_key, uses_vertex_ai=uses_vertex_ai)
    else:
      self.default_manager = InMemoryFakeAgentManager()
      
    # 初始化用户会话管理器
    if self.use_multi_user:
      self.user_session_manager = UserSessionManager.get_instance()
      
    self._file_cache = {} # dict[str, FilePart] maps file id to message data
    self._message_to_cache = {} # dict[str, str] maps message id to cache id

    router.add_api_route(
        "/conversation/create",
        self._create_conversation,
        methods=["POST"])
    router.add_api_route(
        "/conversation/list",
        self._list_conversations_in_db,
        methods=["POST"])
    router.add_api_route(
        "/conversation/delete",
        self._delete_conversation,
        methods=["POST"])
    router.add_api_route(
        "/message/send",
        self._send_message,
        methods=["POST"])
    router.add_api_route(
        "/events/get",
        self._get_events,
        methods=["POST"])
    router.add_api_route(
        "/message/list",
        self._list_messages,
        methods=["POST"])
    router.add_api_route(
        "/message/pending",
        self._pending_messages,
        methods=["POST"])
    router.add_api_route(
        "/task/list",
        self._list_tasks,
        methods=["POST"])
    # 注释掉代理注册接口 - 暂不支持该功能
    # router.add_api_route(
    #     "/agent/register",
    #     self._register_agent,
    #     methods=["POST"])
    router.add_api_route(
        "/agent/list",
        self._list_agents,
        methods=["POST"])
    router.add_api_route(
        "/message/file/{file_id}",
        self._files,
        methods=["GET"])
    # router.add_api_route(
    #     "/api_key/update",
    #     self._update_api_key,
    #     methods=["POST"])
    # 添加历史会话查询API
    router.add_api_route(
        "/history/conversations",
        self._get_user_history_conversations,
        methods=["GET"])
    router.add_api_route(
        "/history/messages/{conversation_id}",
        self._get_history_messages,
        methods=["GET"])
        
    # 添加WebSocket路由
    router.add_websocket_route("/api/ws", self._websocket_endpoint)

    # 启动定期清理任务
    if self.use_multi_user:
      threading.Thread(target=self._run_cleanup_task, daemon=True).start()

  def _get_wallet_address(self, request: Request) -> Optional[str]:
    """从请求头中获取钱包地址"""
    wallet_address = request.headers.get('X-Solana-PublicKey')
    if not wallet_address:
      logger.warning("请求中缺少钱包地址")
    return wallet_address
    
  def _get_user_manager(self, request: Request) -> ApplicationManager:
    """获取用户特定的管理器"""
    # 获取鉴权头信息
    headers = {}
    if 'X-Solana-PublicKey' in request.headers:
      headers['X-Solana-PublicKey'] = request.headers.get('X-Solana-PublicKey')
    if 'X-Solana-Nonce' in request.headers:
      headers['X-Solana-Nonce'] = request.headers.get('X-Solana-Nonce')
    if 'X-Solana-Signature' in request.headers:
      headers['X-Solana-Signature'] = request.headers.get('X-Solana-Signature')
    
    if not self.use_multi_user:
      # 如果单用户模式，更新默认manager的headers
      if isinstance(self.default_manager, ADKHostManager):
        self.default_manager.headers = headers
        self.default_manager._host_agent.headers = headers
      return self.default_manager
      
    wallet_address = self._get_wallet_address(request)
    if not wallet_address:
      logger.warning("使用默认管理器处理请求")
      return self.default_manager
    
    # 更新用户活跃状态
    self._update_user_activity(wallet_address)
      
    # 获取用户特定的manager
    manager = self.user_session_manager.get_host_manager(wallet_address, headers=headers)
    
    # 更新manager的headers
    if isinstance(manager, ADKHostManager):
      manager.headers = headers
      manager._host_agent.headers = headers
      
    return manager
    
  def _update_user_activity(self, wallet_address: str):
    """更新用户活跃状态"""
    if self.use_multi_user and wallet_address:
      try:
        # 更新用户活跃状态
        self.user_session_manager.update_user_activity(wallet_address)
      except Exception as e:
        logger.error(f"更新用户活跃状态时出错: {e}")

  def _run_cleanup_task(self):
    """定期运行清理任务"""
    import time
    while True:
      try:
        # 每30分钟清理一次不活跃会话
        time.sleep(30 * 60)
        if self.use_multi_user:
          self.user_session_manager.cleanup_inactive_sessions(timeout_minutes=60)
      except Exception as e:
        logger.error(f"清理任务出错: {e}")

  # 更新管理器中的API密钥
  def update_api_key(self, api_key: str):
    if isinstance(self.default_manager, ADKHostManager):
      self.default_manager.update_api_key(api_key)

  async def _create_conversation(self, request: Request):
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    
    # 如果启用了多用户模式，检查用户会话数量限制
    if self.use_multi_user and wallet_address:
      # 检查用户的会话数量
      conversation_count = self.user_session_manager.get_user_conversation_count(wallet_address)
      if conversation_count >= 5:
        logger.warning(f"用户 {wallet_address} 的会话数量已达到上限(5个)")
        return {
          "error": "You have reached the maximum number of conversations (5). Please delete some conversations before creating a new one."
        }
    
    manager = self._get_user_manager(request)
    c = manager.create_conversation()
    
    # 如果是多用户模式，保存会话记录到数据库
    if self.use_multi_user:
      wallet_address = self._get_wallet_address(request)
      if wallet_address:
        self.user_session_manager.save_conversation(
          wallet_address=wallet_address,
          conversation_id=c.conversation_id,
          name=c.name if hasattr(c, 'name') else "",
          is_active=c.is_active
        )
    
    return CreateConversationResponse(result=c)

  async def _send_message(self, request: Request):
    message_data = await request.json()
    message = Message(**message_data['params'])
    
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    
    # 如果是多用户模式且有钱包地址，先刷新用户的代理列表
    if self.use_multi_user and wallet_address:
      self.user_session_manager.refresh_user_agents(wallet_address)
    
    # 获取用户的管理器
    manager = self._get_user_manager(request)
    message = manager.sanitize_message(message)
    
    # 在消息元数据中添加钱包地址信息，用于代理响应时确定消息所属用户
    if self.use_multi_user and wallet_address and message.metadata:
      message.metadata['wallet_address'] = wallet_address
    
    # 如果是多用户模式，保存消息到数据库
    conversation_id = message.metadata.get('conversation_id', '')
    if self.use_multi_user and wallet_address and conversation_id:
      # 保存消息
      self.user_session_manager.save_message_from_object(
        wallet_address=wallet_address,
        message=message
      )
      
      # 限制会话消息数量，只保留最新的10条
      self.user_session_manager.limit_conversation_messages(
        wallet_address=wallet_address,
        conversation_id=conversation_id,
        max_messages=10  # 保留最新的10条消息
      )
      
      # WebSocket推送消息通知
      try:
        # 发送消息创建通知
        ws_message = {
          "type": "new_message",
          "conversation_id": conversation_id,
          "message": {
            "id": message.metadata.get('message_id', ''),
            "role": message.role,
            "content": [
              {
                "type": part.type,
                "text": part.text if hasattr(part, 'text') else None
              }
              for part in message.parts
              if part.type == 'text'
            ]
          }
        }
        asyncio.create_task(self.ws_manager.send_message(wallet_address, ws_message))
      except Exception as e:
        logger.error(f"通过WebSocket发送消息通知时出错: {e}")
      
      # 如果当前存在任务，将消息添加到任务历史记录
      for task in manager.tasks:
        if task['sessionId'] == conversation_id:
          # 将用户消息添加到任务历史记录
          if not hasattr(task, 'history') or task.history is None:
            from common.types import Message as TaskMessage
            task.history = []
          
          # 检查消息是否已存在于历史记录中
          message_id = message.metadata.get('message_id')
          if message_id:
            existing_ids = [
              m.metadata.get('message_id') 
              for m in task.history 
              if m.metadata and 'message_id' in m.metadata
            ]
            if message_id in existing_ids:
              print(f"消息 {message_id} 已存在于任务 {task.id} 的历史记录中，跳过添加")
              break
          
          # 添加消息到任务历史
          task.history.append(message)
          print(f"已将用户消息 {message_id} 添加到任务 {task.id} 的历史记录中")
          
          # 保存更新后的任务
          self.user_session_manager.save_task(wallet_address, task)
          break
    
    # 改进的异步任务处理，增强稳定性和错误恢复能力
    async def process_message_with_timeout():
        """使用超时机制处理消息"""
        try:
            # 增加超时时间到60秒，确保有足够的处理时间
            response = await asyncio.wait_for(
                manager.process_message(message),
                timeout=60.0
            )
            
            # 如果有响应且是多用户模式，通过WebSocket推送代理响应
            if response and self.use_multi_user and wallet_address and conversation_id:
                try:
                    # 检查响应消息ID是否存在于日志中
                    response_id = ""
                    if hasattr(response, 'metadata') and response.metadata and 'message_id' in response.metadata:
                        response_id = response.metadata['message_id']
                    
                    # 构建代理响应WebSocket消息
                    agent_message = {
                        "type": "new_message",
                        "conversation_id": conversation_id,
                        "message": {
                            "id": response_id,
                            "role": "agent",  # 使用agent角色标识
                            "content": [
                                {
                                    "type": part.type,
                                    "text": part.text if hasattr(part, 'text') else None
                                }
                                for part in response.parts
                                if part.type == 'text'
                            ]
                        }
                    }
                    
                    # 发送代理响应通知
                    logger.info(f"通过WebSocket推送代理响应: ID={response_id}")
                    asyncio.create_task(self.ws_manager.send_message(wallet_address, agent_message))
                except Exception as e:
                    logger.error(f"通过WebSocket发送代理响应通知时出错: {e}")
        except asyncio.TimeoutError:
            logger.error(f"处理消息超时: {message.metadata.get('message_id', 'unknown')}")
            # 在超时情况下尝试取消任务并清理资源
            try:
                # 尝试在超时时通知用户
                if message.metadata and 'message_id' in message.metadata:
                    # 记录超时状态以便前端可以显示
                    if hasattr(manager, '_pending_message_ids') and message.metadata['message_id'] in manager._pending_message_ids:
                        manager._pending_message_ids[message.metadata['message_id']] = "处理超时，请重试"
            except Exception as cleanup_err:
                logger.error(f"超时处理清理失败: {cleanup_err}")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

    # 使用线程池执行异步任务，而不是为每个请求创建新线程
    def run_async_task():
        """在线程池中运行异步任务"""
        try:
            # 为当前线程创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 在事件循环中运行任务
            try:
                loop.run_until_complete(process_message_with_timeout())
            except Exception as e:
                logger.error(f"执行异步任务失败: {e}")
            finally:
                # 关闭前取消所有挂起的任务
                tasks = asyncio.all_tasks(loop)
                for task in tasks:
                    task.cancel()
                
                # 等待任务取消完成
                if tasks:
                    try:
                        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    except Exception:
                        pass
                    
                # 关闭循环并释放资源
                loop.close()
        except Exception as e:
            logger.error(f"消息处理线程出错: {e}")
            
    # 监听数据库消息变化的函数
    def monitor_agent_messages():
        """监听代理消息，并通过WebSocket推送"""
        try:
            # 等待处理完成后，查询数据库中最新的代理消息
            if self.use_multi_user and wallet_address and conversation_id:
                # 获取最新的代理消息（暂停500ms等待处理完成）
                import time
                time.sleep(0.5)
                
                # 查询最新的代理消息
                messages = self.user_session_manager.get_conversation_messages(
                    conversation_id=conversation_id,
                    wallet_address=wallet_address,
                    limit=1
                )
                
                # 发送最新的代理消息
                if messages and len(messages) > 0:
                    agent_message = messages[0]
                    response_id = agent_message.get('message_id', '')
                    
                    # 构建WebSocket消息
                    ws_message = {
                        "type": "new_message",
                        "conversation_id": conversation_id,
                        "message": {
                            "id": response_id,
                            "role": "agent",
                            "content": []
                        }
                    }
                    
                    # 添加内容
                    if 'content' in agent_message and 'parts' in agent_message['content']:
                        ws_message["message"]["content"] = [
                            {
                                "type": part.get('type', 'text'),
                                "text": part.get('text', '')
                            }
                            for part in agent_message['content']['parts']
                            if 'type' in part and part.get('type') == 'text'
                        ]
                    
                    # 发送WebSocket消息
                    logger.info(f"从数据库推送代理消息: ID={response_id}")
                    asyncio.run(self.ws_manager.send_message(wallet_address, ws_message))
        except Exception as e:
            logger.error(f"监控代理消息时出错: {e}")
    
    # 提交任务到线程池
    thread_pool = None
    
    # 尝试从主模块获取线程池
    try:
        if 'main' in sys.modules:
            main_module = sys.modules['main']
            if hasattr(main_module, 'thread_pool'):
                thread_pool = main_module.thread_pool
    except Exception:
        pass
    
    # 如果没有找到全局线程池，则创建一个局部的
    if thread_pool is None:
        thread_pool = ThreadPoolExecutor(max_workers=20, thread_name_prefix="message_worker")
    
    # 提交消息处理任务到线程池
    thread_pool.submit(run_async_task)
    
    # 提交监控代理消息的任务到线程池
    thread_pool.submit(monitor_agent_messages)
    
    return SendMessageResponse(result=MessageInfo(
        message_id=message.metadata['message_id'],
        conversation_id=message.metadata['conversation_id'] if 'conversation_id' in message.metadata else '',
    ))

  async def _list_messages(self, request: Request):
    message_data = await request.json()
    conversation_id = message_data['params']
    request_id = message_data.get('id', str(uuid.uuid4()))
    
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    
    # 如果没有获取到
    if not wallet_address and self.use_multi_user:
      return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": [],
        "error": {
          "code": -32000,
          "message": "Invalid wallet address"
        }
      }
    
    # 获取会话相关的任务
    tasks_by_message_id = {}
    if self.use_multi_user and wallet_address:
      try:
        # 直接获取会话的所有任务
        #user_session_manager = UserSessionManager.get_instance()
        conversation_tasks = self.user_session_manager.get_conversation_tasks(
          conversation_id=conversation_id,
          wallet_address=wallet_address
        )
        
     
        # 创建消息ID到任务的映射
        for task_data in conversation_tasks:
          # 检查任务数据是否完整
          if 'data' in task_data and isinstance(task_data['data'], dict):
            task_obj = task_data['data']
            
            # 将任务关联到状态消息
            if 'status' in task_obj and task_obj['status'] and 'message' in task_obj['status']:
              status_msg = task_obj['status']['message']
              if status_msg and 'metadata' in status_msg and 'message_id' in status_msg['metadata']:
                msg_id = status_msg['metadata']['message_id']
                if msg_id:
                  tasks_by_message_id[msg_id] = task_data
                  #logger.info(f"将任务 {task_data.get('id', 'unknown')} 关联到消息 {msg_id}")
                  
            # 将任务关联到历史消息
            if 'history' in task_obj and task_obj['history']:
              for history_msg in task_obj['history']:
                if history_msg and isinstance(history_msg, dict) and 'metadata' in history_msg and 'message_id' in history_msg['metadata']:
                  msg_id = history_msg['metadata']['message_id']
                  if msg_id:
                    tasks_by_message_id[msg_id] = task_data
                    #logger.info(f"将任务 {task_data.get('id', 'unknown')} 关联到历史消息 {msg_id}")
        
        #logger.info(f"任务映射表: {list(tasks_by_message_id.keys())}")
      except Exception as e:
        logger.error(f"获取任务信息时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 如果是多用户模式且能获取到钱包地址，从数据库读取消息
    messages = []
    if self.use_multi_user and wallet_address:
      try:
        # 从数据库获取消息，同时使用wallet_address和conversation_id确保查询正确
        db_messages = self.user_session_manager.get_conversation_messages(
            conversation_id=conversation_id,
            wallet_address=wallet_address,
            limit=20
        )
        logger.info(f"从数据库获取到 {len(db_messages) if db_messages else 0} 条消息")
        
        if db_messages:
          # 将数据库格式的消息转换为Message对象
          from common.types import Message, TextPart, DataPart, FilePart, FileContent
          converted_messages = []
          
          for msg_data in db_messages:
            try:
              # 从内容构建消息对象
              content = msg_data.get('content', {})
              
              # 创建消息对象
              if 'parts' in content:
                parts = []
                for part_data in content.get('parts', []):
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
                
                # 处理元数据
                message_id = msg_data.get('message_id')
                metadata = {'message_id': message_id, 'conversation_id': conversation_id}
                if 'metadata' in content:
                  for key, value in content.get('metadata', {}).items():
                    metadata[key] = value
                
                # 创建消息对象
                message = Message(
                  role=msg_data.get('role', 'user'),
                  parts=parts,
                  metadata=metadata
                )
                
                # 添加关联的任务信息
                if message_id in tasks_by_message_id:
                  task_data = tasks_by_message_id[message_id]
                  task_info = self._prepare_task_for_message(task_data)
                  
                  if task_info:
                    # 直接赋值确保元数据被正确更新
                    if not hasattr(message, 'metadata') or message.metadata is None:
                      message.metadata = {}
                    
                    # 将任务信息添加到消息元数据中
                    if 'tasks' not in message.metadata:
                      message.metadata['tasks'] = []
                    message.metadata['tasks'].append(task_info)
                    logger.info(f"消息 {message_id} 添加任务成功")
                
                converted_messages.append(message)
              else:
                # 简单消息处理
                message = Message(
                  role=msg_data.get('role', 'user'),
                  parts=[TextPart(text="无法显示消息内容")],
                  metadata={'message_id': msg_data.get('message_id'), 'conversation_id': conversation_id}
                )
                converted_messages.append(message)
                
            except Exception as e:
              logger.error(f"转换消息格式出错: {e}")
              import traceback
              logger.error(traceback.format_exc())
          
          messages = converted_messages
      except Exception as e:
        logger.error(f"从数据库读取消息时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 如果没有从数据库获取到消息，则从内存中获取
    if not messages:
      # 从内存获取消息
      manager = self._get_user_manager(request)
      conversation = manager.get_conversation(conversation_id)
      
      if conversation:
        # 限制返回最新的10条消息
        if hasattr(conversation, 'messages') and len(conversation.messages) > 10:
          messages = conversation.messages[-10:]
        else:
          messages = conversation.messages
        
        logger.info(f"从内存获取到 {len(messages) if messages else 0} 条消息")
        
        # 添加任务信息到消息
        for message in messages:
          if hasattr(message, 'metadata') and message.metadata:
            message_id = message.metadata.get('message_id')
            if message_id and message_id in tasks_by_message_id:
              task_data = tasks_by_message_id[message_id]
              task_info = self._prepare_task_for_message(task_data)
              logger.info(f"为内存消息 {message_id} 添加任务信息: {task_info is not None}")
              if task_info:
                # 将任务信息添加到消息元数据中
                if not hasattr(message, 'metadata') or message.metadata is None:
                  message.metadata = {}
                
                if 'tasks' not in message.metadata:
                  message.metadata['tasks'] = []
                message.metadata['tasks'].append(task_info)
                logger.info(f"内存消息 {message_id} 添加任务成功")
    
    # 处理内容并返回
    processed_messages = self.cache_content(messages)
    
    # 检查处理后的消息是否包含任务信息
    task_count = 0
    for msg in processed_messages:
      if hasattr(msg, 'metadata') and msg.metadata and 'tasks' in msg.metadata:
        task_count += 1
    
    logger.info(f"响应包含 {len(processed_messages)} 条消息，其中 {task_count} 条包含任务信息")
    
    # 返回JSONRPC 2.0格式的响应
    return {
      "jsonrpc": "2.0",
      "id": request_id,
      "result": processed_messages,
      "error": None
    }
    
  def _prepare_task_for_message(self, task_data):
    """将任务数据准备为消息可用的格式"""
    try:
      # 确保任务数据完整
      if not task_data or not isinstance(task_data, dict):
        return None
      
      task_id = task_data.get('id') or task_data.get('task_id')
      session_id = task_data.get('sessionId') or task_data.get('session_id')
      
      # 使用_format_task_for_client的逻辑处理复杂的任务对象
      if 'data' in task_data and isinstance(task_data['data'], dict):
        task_obj = task_data['data']
        
        # 构建一个标准格式的任务对象
        formatted_task = {
          "id": task_obj.get('id') or task_id,
          "sessionId": task_obj.get('sessionId') or session_id,
          "status": {
            "state": task_data.get('state', 'completed'),
            "timestamp": task_data.get('updated_at', datetime.datetime.now().isoformat())
          }
        }
        
        # 添加消息信息
        if 'status' in task_obj and task_obj['status'] and 'message' in task_obj['status']:
          formatted_task['status']['message'] = task_obj['status']['message']
        
        # 添加制品信息
        if 'artifacts' in task_obj and task_obj['artifacts']:
          formatted_task['artifacts'] = task_obj['artifacts']
        
        # 添加历史信息
        if 'history' in task_obj and task_obj['history']:
          formatted_task['history'] = task_obj['history']
        
        return formatted_task
      
      # 简化版的任务信息
      return {
        "id": task_id,
        "sessionId": session_id,
        "status": {
          "state": task_data.get('state', 'completed'),
          "timestamp": task_data.get('updated_at', datetime.datetime.now().isoformat())
        }
      }
    except Exception as e:
      logger.error(f"准备任务数据时出错: {e}")
      import traceback
      logger.error(traceback.format_exc())
      return None

  def cache_content(self, messages: list[Message]):
    """处理消息内容，确保保留元数据中的任务信息"""
    rval = []
    for m in messages:
      # 保存原始元数据
      original_metadata = m.metadata.copy() if hasattr(m, 'metadata') and m.metadata else {}
      
      message_id = get_message_id(m)
      if not message_id:
        rval.append(m)
        continue
      new_parts = []
      for i, part in enumerate(m.parts):
        if part.type != 'file':
          new_parts.append(part)
          continue
        message_part_id = f"{message_id}:{i}"
        if message_part_id in self._message_to_cache:
          cache_id = self._message_to_cache[message_part_id]
        else:
          cache_id = str(uuid.uuid4())
          self._message_to_cache[message_part_id] = cache_id
        # Replace the part data with a url reference
        new_parts.append(FilePart(
            file=FileContent(
                mimeType=part.file.mimeType,
                uri=f"/message/file/{cache_id}",
            )
        ))
        if cache_id not in self._file_cache:
          self._file_cache[cache_id] = part
      m.parts = new_parts
      
      # 确保任务信息不丢失
      if 'tasks' in original_metadata and original_metadata['tasks']:
        if not hasattr(m, 'metadata') or m.metadata is None:
          m.metadata = {}
        m.metadata['tasks'] = original_metadata['tasks']
      
      rval.append(m)
    return rval

  async def _pending_messages(self, request: Request):
    manager = self._get_user_manager(request)
    return PendingMessageResponse(result=manager.get_pending_messages())

  async def _list_conversation(self, request: Request):
    manager = self._get_user_manager(request)
    return ListConversationResponse(result=manager.conversations)

  async def _list_conversations_in_db(self, request: Request):
    """
    直接从数据库读取对话历史记录，而不通过ADK管理器。
    这可以避免在第一次请求时的性能问题。
    
    Args:
        request: FastAPI请求对象，包含用户的钱包地址
        
    Returns:
        ListConversationResponse: 包含对话历史列表的响应对象
    """
    # 从请求头获取钱包地址
    wallet_address = self._get_wallet_address(request)
    if not wallet_address:
      logger.warning("请求中缺少钱包地址，无法获取对话历史")
      return ListConversationResponse(result=[])
    
    # 更新用户活跃状态
    self._update_user_activity(wallet_address)
    
    # # 直接访问用户会话管理器
    # user_session_manager = UserSessionManager.get_instance()
    
    # 检查是否内存模式，如果是则使用旧方法获取
    if self.user_session_manager._memory_mode:
      manager = self._get_user_manager(request)
      return ListConversationResponse(result=manager.conversations)
    
    # 直接从数据库获取会话列表
    try:
      # 确保数据库连接有效
      # user_session_manager._ensure_db_connection()
      
      # 获取会话列表
      db_conversations = self.user_session_manager.get_user_conversations(wallet_address)
      
      # 转换为Conversation对象列表
      from service.types import Conversation
      conversations = []
      
      for conv_data in db_conversations:
        conversation_id = conv_data['conversation_id']
        
        # 获取会话消息数量
        messages_count = 0
        try:
          # 获取会话消息列表
          conversation_messages = self.user_session_manager.get_conversation_messages(
            conversation_id=conversation_id,
            wallet_address=wallet_address
          )
          messages_count = len(conversation_messages) if conversation_messages else 0
          
          # 获取会话的所有消息内容(用于前端显示)
          messages = []
          for msg in conversation_messages:
            message_data = {
              "id": msg.get('message_id', ''),
              "role": msg.get('role', 'unknown'),
              "content": []
            }
            
            # 提取消息内容
            content = msg.get('content', {})
            if 'parts' in content and isinstance(content['parts'], list):
              for part in content['parts']:
                if part.get('type') == 'text':
                  message_data["content"].append({
                    "type": "text",
                    "text": part.get('text', '')
                  })
            
            messages.append(message_data)
        except Exception as e:
          logger.error(f"获取会话 {conversation_id} 的消息时出错: {e}")
        
        conversation = Conversation(
          conversation_id=conversation_id,
          name=conv_data.get('name', ''),
          is_active=conv_data.get('is_active', True),
          messages=messages,  # 添加消息列表
          message_count=messages_count  # 添加消息计数
        )
        conversations.append(conversation)
      
      # 获取请求ID
      request_data = await request.json()
      request_id = request_data.get('id', str(uuid.uuid4()))
      
      # 返回JSONRPC 2.0格式的响应
      return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": conversations,
        "error": None
      }
      
    except Exception as err:
      logger.error(f"从数据库获取对话历史时出错: {err}")
      # 出错时回退到使用管理器方法
      manager = self._get_user_manager(request)
      return ListConversationResponse(result=manager.conversations)

  async def _get_events(self, request: Request):
    manager = self._get_user_manager(request)
    return GetEventResponse(result=manager.events)

  async def _list_tasks(self, request: Request):
    manager = self._get_user_manager(request)
    
    # 获取请求参数
    try:
      message_data = await request.json()
      # 尝试获取conversation_id参数
      conversation_id = message_data.get('conversation_id', None)
      request_id = message_data.get('id', str(uuid.uuid4()))
    except:
      # 如果无法解析JSON或没有参数，默认为None
      conversation_id = None
      request_id = str(uuid.uuid4())
    
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    
    # 从内存中获取任务
    memory_tasks = manager.tasks
    logger.info(f"从内存获取到 {len(memory_tasks)} 个任务")
    
    # 如果指定了conversation_id，过滤内存中的任务
    if conversation_id:
      memory_tasks = [task for task in memory_tasks if 
                     hasattr(task, 'sessionId') and task.sessionId == conversation_id]
      logger.info(f"过滤会话 {conversation_id} 后剩余 {len(memory_tasks)} 个任务")
    
    # 如果是多用户模式且有钱包地址，尝试从数据库获取更多任务信息
    if self.use_multi_user and wallet_address:
      try:
        # 获取用户会话管理器
        user_session_manager = UserSessionManager.get_instance()
        
        # 如果数据库中有会话但运行在内存模式，仅返回内存中的任务
        if user_session_manager._memory_mode:
          formatted_tasks = [self._format_task_for_client(task) for task in memory_tasks]
          logger.info(f"内存模式返回 {len(formatted_tasks)} 个任务")
          return ListTaskResponse(id=request_id, result=formatted_tasks)
        
        # 查询任务
        db_tasks = []
        
        if conversation_id:
          # 如果指定了conversation_id，只查询该会话的任务
          tasks = user_session_manager.get_conversation_tasks(
            conversation_id=conversation_id,
            wallet_address=wallet_address
          )
          if tasks:
            db_tasks.extend(tasks)
            logger.info(f"从数据库获取到会话 {conversation_id} 的 {len(tasks)} 个任务")
        else:
          # 否则查询所有会话的任务
          conversations = user_session_manager.get_user_conversations(wallet_address)
          for conv in conversations:
            # 获取会话ID
            conv_id = conv.conversation_id if hasattr(conv, 'conversation_id') else conv.get('conversation_id')
            if conv_id:
              # 获取会话相关的任务
              tasks = user_session_manager.get_conversation_tasks(
                conversation_id=conv_id,
                wallet_address=wallet_address
              )
              if tasks:
                db_tasks.extend(tasks)
                logger.info(f"从数据库获取到会话 {conv_id} 的 {len(tasks)} 个任务")
        
        logger.info(f"从数据库总共获取 {len(db_tasks)} 个任务")
        
        # 合并内存中的任务和数据库中的任务，确保没有重复
        if db_tasks:
          # 转换数据库任务为Task对象
          from common.types import Task, TaskStatus, TaskState
          from datetime import datetime
          
          # 获取内存中任务的ID列表
          memory_task_ids = [t['id'] for t in memory_tasks]
          logger.info(f"内存中已有的任务ID: {memory_task_ids}")
          
          # 直接使用我们自己的格式化方法处理数据库任务
          for db_task in db_tasks:
            try:
              task_id = db_task.get('id') or db_task.get('task_id')
              
              # 检查任务是否已经在内存中
              if task_id in memory_task_ids:
                logger.info(f"任务 {task_id} 已在内存中存在，跳过添加")
                continue
              
              # 使用_prepare_task_for_message将任务数据转换为标准格式
              formatted_task = self._prepare_task_for_message(db_task)
              
              if formatted_task:
                #logger.info(f"成功转换数据库任务 {task_id}")
                
                # 将格式化后的任务添加到响应列表，避免Task类的限制
                memory_tasks.append({
                  "id": formatted_task["id"],
                  "sessionId": formatted_task["sessionId"],
                  "status": formatted_task["status"],
                  "artifacts": formatted_task.get("artifacts", []),
                  "history": formatted_task.get("history", []),
                  "metadata": formatted_task.get("metadata", {})
                })
            except Exception as e:
              logger.error(f"转换数据库任务时出错: {e}")
              import traceback
              logger.error(traceback.format_exc())
      except Exception as e:
        # 错误处理不应影响现有流程
        logger.error(f"获取数据库任务时出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 格式化响应
    formatted_tasks = []
    
    # 分别处理不同类型的任务对象
    for task in memory_tasks:
      try:
        # 如果已经是格式化后的字典，直接添加
        if isinstance(task, dict) and 'id' in task and 'status' in task:
          formatted_tasks.append(task)
          continue
          
        # 否则使用格式化方法处理
        formatted_task = self._format_task_for_client(task)
        formatted_tasks.append(formatted_task)
      except Exception as e:
        logger.error(f"格式化任务 {getattr(task, 'id', 'unknown')} 时出错: {e}")
    
    logger.info(f"最终返回 {len(formatted_tasks)} 个任务")
    
    # 返回ListTaskResponse对象
    return ListTaskResponse(id=request_id, result=formatted_tasks)

  def _format_task_for_client(self, task):
    """将Task对象格式化为统一的客户端格式"""
    try:
      # 处理状态消息
      status_message = None
      if hasattr(task.status, 'message') and task.status.message:
        status_message = {
          "role": task.status.message.role if hasattr(task.status.message, 'role') else "agent",
          "parts": [],
          "metadata": {}
        }
        
        # 添加消息部分
        if hasattr(task.status.message, 'parts') and task.status.message.parts:
          for part in task.status.message.parts:
            part_data = {
              "type": part.type if hasattr(part, 'type') else "text",
              "metadata": None
            }
            
            if hasattr(part, 'text'):
              part_data["text"] = part.text
            
            status_message["parts"].append(part_data)
        
        # 添加元数据
        if hasattr(task.status.message, 'metadata') and task.status.message.metadata:
          status_message["metadata"] = task.status.message.metadata
        else:
          # 确保至少包含以下字段
          status_message["metadata"] = {
            "conversation_id": task.sessionId,
            "message_id": str(uuid.uuid4()),
            "wallet_address": self._get_wallet_address_from_task(task)
          }
          
          # 添加last_message_id
          if hasattr(task, 'history') and task.history and len(task.history) > 0:
            last_message = task.history[-1]
            if hasattr(last_message, 'metadata') and last_message.metadata and 'message_id' in last_message.metadata:
              status_message["metadata"]["last_message_id"] = last_message.metadata['message_id']
      
      # 格式化时间戳
      timestamp = None
      if hasattr(task.status, 'timestamp'):
        if isinstance(task.status.timestamp, datetime.datetime):
          timestamp = task.status.timestamp.isoformat()
        else:
          timestamp = str(task.status.timestamp)
      else:
        # 如果没有时间戳，使用当前时间
        timestamp = datetime.datetime.now().isoformat()
      
      # 格式化状态
      status = {
        "state": task.status.state.value if hasattr(task.status.state, 'value') else str(task.status.state),
        "message": status_message,
        "timestamp": timestamp
      }
      
      # 格式化历史记录
      history = []
      if hasattr(task, 'history') and task.history:
        for msg in task.history:
          msg_data = {
            "role": msg.role if hasattr(msg, 'role') else "user",
            "parts": [],
            "metadata": {}
          }
          
          # 添加消息部分
          if hasattr(msg, 'parts') and msg.parts:
            for part in msg.parts:
              part_data = {
                "type": part.type if hasattr(part, 'type') else "text",
                "metadata": None
              }
              
              if hasattr(part, 'text'):
                part_data["text"] = part.text
              
              msg_data["parts"].append(part_data)
          
          # 添加元数据
          if hasattr(msg, 'metadata') and msg.metadata:
            msg_data["metadata"] = msg.metadata
          
          history.append(msg_data)
      
      # 格式化制品
      artifacts = []
      if hasattr(task, 'artifacts') and task.artifacts:
        for artifact in task.artifacts:
          artifact_data = {
            "name": artifact.name if hasattr(artifact, 'name') else "",
            "description": artifact.description if hasattr(artifact, 'description') else None,
            "parts": [],
            "metadata": artifact.metadata if hasattr(artifact, 'metadata') else None,
            "index": artifact.index if hasattr(artifact, 'index') else 0,
            "append": artifact.append if hasattr(artifact, 'append') else None,
            "lastChunk": artifact.lastChunk if hasattr(artifact, 'lastChunk') else True
          }
          
          # 添加制品部分
          if hasattr(artifact, 'parts') and artifact.parts:
            for part in artifact.parts:
              part_data = {
                "type": part.type if hasattr(part, 'type') else "text",
                "metadata": None
              }
              
              if hasattr(part, 'text'):
                part_data["text"] = part.text
              
              artifact_data["parts"].append(part_data)
          
          artifacts.append(artifact_data)
      
      # 创建标准格式的任务对象
      return {
        "id": task.id,
        "sessionId": task.sessionId if hasattr(task, 'sessionId') else None,
        "status": status,
        "artifacts": artifacts,
        "history": history,
        "metadata": task.metadata if hasattr(task, 'metadata') else None
      }
    except Exception as e:
      logger.error(f"格式化任务时出错: {e}")
      # 返回基本信息，确保不会中断流程
      return {
        "id": task.id if hasattr(task, 'id') else str(uuid.uuid4()),
        "sessionId": task.sessionId if hasattr(task, 'sessionId') else None,
        "status": {
          "state": str(task.status.state) if hasattr(task, 'status') and hasattr(task.status, 'state') else "completed",
          "message": None,
          "timestamp": datetime.datetime.now().isoformat()
        },
        "artifacts": [],
        "history": [],
        "metadata": None
      }
      
  def _get_wallet_address_from_task(self, task):
    """从任务中获取钱包地址"""
    # 从历史消息中获取
    if hasattr(task, 'history') and task.history:
      for msg in task.history:
        if hasattr(msg, 'metadata') and msg.metadata and 'wallet_address' in msg.metadata:
          return msg.metadata['wallet_address']
    
    # 从状态消息中获取
    if (hasattr(task, 'status') and hasattr(task.status, 'message') and 
        hasattr(task.status.message, 'metadata') and task.status.message.metadata and 
        'wallet_address' in task.status.message.metadata):
      return task.status.message.metadata['wallet_address']
    
    return "unknown"

  # 注释掉代理注册方法 - 暂不支持该功能
  # async def _register_agent(self, request: Request):
  #   message_data = await request.json()
  #   url = message_data['params']
  #   
  #   wallet_address = self._get_wallet_address(request)
  #   
  #   if self.use_multi_user and wallet_address:
  #     # 使用用户会话管理器注册代理
  #     self.user_session_manager.register_agent(wallet_address, url)
  #   else:
  #     # 使用默认管理器
  #     self.default_manager.register_agent(url)
  #     
  #   return RegisterAgentResponse()

  async def _list_agents(self, request: Request):
    """获取用户的代理列表"""
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    
    # 如果没有钱包地址，使用默认行为
    if not wallet_address:
        
            return ListAgentResponse(result=[])
    
    # 如果是多用户模式，从数据库获取代理信息
    if self.use_multi_user:
        # # 先刷新用户的代理列表
        # self.user_session_manager.refresh_user_agents(wallet_address)
        
        # 从数据库查询代理信息
        agents = self.user_session_manager.queryAgentsByAddress(wallet_address)
        
      
        
        # 返回格式化后的代理列表
        result = []
        for agent_info in agents:
            # 创建一个ExtendedAgentCard对象
            try:
                # 处理特殊字段
                capabilities = agent_info.get('capabilities', {
                    'streaming': True,
                    'pushNotifications': False,
                    'stateTransitionHistory': False
                })
                
                # 标准AgentCard字段
                card_data = {
                    'name': agent_info.get('name', f"Agent ({agent_info.get('url', 'Unknown')})"),
                    'description': agent_info.get('description', ''),
                    'url': agent_info.get('url', ''),
                    'provider': agent_info.get('provider'),
                    'version': agent_info.get('version', '1.0.0'),
                    'documentationUrl': agent_info.get('documentationUrl'),
                    'capabilities': capabilities,
                    'authentication': agent_info.get('authentication'),
                    'defaultInputModes': agent_info.get('defaultInputModes', ['text', 'text/plain']),
                    'defaultOutputModes': agent_info.get('defaultOutputModes', ['text', 'text/plain']),
                    'skills': agent_info.get('skills', []),
                    
                    # ExtendedAgentCard额外字段
                    'is_online': agent_info.get('is_online', 'unknown'),
                    'expire_at': agent_info.get('expire_at'),
                    'nft_mint_id': agent_info.get('nft_mint_id')
                }
                
                # 创建ExtendedAgentCard对象
                extended_card = ExtendedAgentCard(**card_data)
                result.append(extended_card)
            except Exception as e:
                logger.error(f"创建ExtendedAgentCard对象时出错: {e}")
                # 如果创建对象失败，直接使用原始字典
                result.append(agent_info)
        
        # 返回代理列表
        response = ListAgentResponse(result=result)
                
        return response
    else:
        # 非多用户模式，使用默认行为
        manager = self._get_user_manager(request)
        return ListAgentResponse(result=manager.agents)

  async def _files(self, file_id: str, request: Request):
    if file_id not in self._file_cache:
      raise Exception("file not found")
    part = self._file_cache[file_id]
    if "image" in part.file.mimeType:
      return Response(
          content=base64.b64decode(part.file.bytes),
          media_type=part.file.mimeType)
    return Response(content=part.file.bytes, media_type=part.file.mimeType)
  
  async def _update_api_key(self, request: Request):
    """更新API密钥"""
    try:
        data = await request.json()
        api_key = data.get("api_key", "")
        
        if not api_key:
            return {"status": "error", "message": "No valid API key provided"}
            
        # 更新环境变量
        os.environ["GOOGLE_API_KEY"] = api_key
        # 记录API key已更新（隐藏完整密钥）
        masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***" 
        logger.info(f"已全局更新API密钥: {masked_key}")
        
        # 更新默认管理器中的API密钥
        self.update_api_key(api_key)
        
        # 如果是多用户模式，同时更新所有用户的API密钥
        if self.use_multi_user:
            for wallet_address, manager in self.user_session_manager._host_managers.items():
                if isinstance(manager, ADKHostManager):
                    manager.api_key = api_key
                    logger.info(f"已更新用户 {wallet_address} 的API密钥")
        
        return {"status": "success", "message": "API key has been updated globally"}
    except Exception as e:
        logger.error(f"更新API密钥时出错: {e}")
        return {"status": "error", "message": str(e)}

  async def _get_user_history_conversations(self, request: Request):
    """获取用户的历史会话列表"""
    wallet_address = self._get_wallet_address(request)
    
    if not self.use_multi_user or not wallet_address:
      return {"result": []}
      
    try:
      conversations = self.user_session_manager.get_user_conversations(wallet_address)
      return {"result": conversations}
    except Exception as e:
      logger.error(f"获取历史会话列表时出错: {e}")
      return {"result": [], "error": str(e)}
      
  async def _get_history_messages(self, conversation_id: str, request: Request):
    """获取会话的历史消息"""
    wallet_address = self._get_wallet_address(request)
    
    if not self.use_multi_user:
      return {"result": []}
      
    try:
      # 查询会话所属的钱包地址
      if not wallet_address:
        wallet_address = self.user_session_manager.get_conversation_wallet_address(conversation_id)
        
      if not wallet_address:
        return {"result": [], "error": "Unable to determine conversation owner"}
        
      # 获取历史消息
      messages = self.user_session_manager.get_conversation_messages(conversation_id)
      return {"result": messages}
    except Exception as e:
      logger.error(f"获取历史消息时出错: {e}")
      return {"result": [], "error": str(e)}

  # 添加会话删除API
  async def _delete_conversation(self, request: Request):
    """删除会话接口"""
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    if not wallet_address:
      return {"error": "No valid wallet address provided", "status": "error", "code": 401}
    
    try:
      # 获取会话ID
      data = await request.json()
      conversation_id = data.get("conversation_id")
      if not conversation_id:
        return {"error": "No conversation ID provided", "status": "error", "code": 400}
      
      # 多用户模式下，验证用户是否拥有该会话
      if self.use_multi_user:
        # 检查会话所属
        owner_address = self.user_session_manager.get_conversation_wallet_address(conversation_id)
        if owner_address and owner_address != wallet_address:
          logger.warning(f"用户 {wallet_address} 尝试删除不属于自己的会话 {conversation_id}")
          return {
            "error": "You don't have permission to delete this conversation as you are not the owner", 
            "status": "error", 
            "code": 403
          }
        
        # 调用删除方法
        success = self.user_session_manager.delete_conversation(
          wallet_address=wallet_address, 
          conversation_id=conversation_id
        )
        
        if success:
          logger.info(f"用户 {wallet_address} 成功删除会话 {conversation_id}")
          return {"status": "success", "message": f"Conversation {conversation_id} has been successfully deleted"}
        else:
          return {"error": "Failed to delete conversation, it may not exist", "status": "error", "code": 404}
      else:
        # 非多用户模式下，直接从管理器中删除会话
        manager = self._get_user_manager(request)
        conversations = manager._conversations
        for i, conv in enumerate(conversations):
          if conv.conversation_id == conversation_id:
            del conversations[i]
            return {"status": "success", "message": f"Conversation {conversation_id} has been successfully deleted"}
        
        return {"error": "Conversation not found", "status": "error", "code": 404}
    except Exception as e:
      logger.error(f"删除会话时出错: {str(e)}")
      return {"error": f"Error deleting conversation: {str(e)}", "status": "error", "code": 500}

  async def _websocket_endpoint(self, websocket: WebSocket):
    """WebSocket连接处理"""
    # 从HTTP头和URL参数中获取鉴权信息
    # 1. 首先尝试从HTTP头获取
    wallet_address = websocket.headers.get('X-Solana-PublicKey')
    nonce = websocket.headers.get('X-Solana-Nonce')
    signature = websocket.headers.get('X-Solana-Signature')
    
    # 2. 如果没有从HTTP头获取到，尝试从URL参数获取
    if not wallet_address or not nonce or not signature:
      # 获取URL查询参数
      query_params = websocket.query_params
      if not wallet_address:
        wallet_address = query_params.get('publicKey')
      if not nonce:
        nonce = query_params.get('nonce')
      if not signature:
        signature = query_params.get('signature')
      
      logger.info(f"从URL参数获取鉴权信息: wallet={wallet_address[:10] if wallet_address else 'None'}")
    
    # 检查必要的鉴权头
    if not wallet_address:
      # 如果没有钱包地址，拒绝连接
      await websocket.close(code=1008, reason="Missing wallet address (X-Solana-PublicKey or publicKey)")
      logger.warning("WebSocket连接被拒绝: 缺少钱包地址")
      return
      
    # 验证签名 - 如果需要签名
    if not nonce or not signature:
      await websocket.close(code=1008, reason="Missing authentication data (nonce or signature)")
      logger.warning(f"WebSocket连接被拒绝: 缺少签名信息, wallet={wallet_address[:10] if len(wallet_address) > 10 else wallet_address}...")
      return
    
    # 验证签名 - 与HTTP接口使用相同的验证逻辑
    try:
      if not sdk_available:
        await websocket.close(code=1008, reason="Solana SDK verification not available")
        logger.error("WebSocket连接被拒绝: Solana SDK不可用")
        return
        
      # 使用相同的验证器验证签名
      if not solana_verifier.verify_signature(wallet_address, nonce, signature):
        # 检查是否签名过期
        try:
          nonce_timestamp = int(nonce)
          current_time = int(time.time() * 1000)
          
          if current_time > nonce_timestamp:
            await websocket.close(code=1008, reason="Signature expired, please sign again")
            logger.warning(f"WebSocket连接被拒绝: 签名已过期, wallet={wallet_address[:10] if len(wallet_address) > 10 else wallet_address}...")
          else:
            await websocket.close(code=1008, reason="Invalid signature")
            logger.warning(f"WebSocket连接被拒绝: 签名无效, wallet={wallet_address[:10] if len(wallet_address) > 10 else wallet_address}...")
        except:
          await websocket.close(code=1008, reason="Invalid nonce format")
          logger.warning(f"WebSocket连接被拒绝: nonce格式无效, wallet={wallet_address[:10] if len(wallet_address) > 10 else wallet_address}...")
        return
      
      # 记录连接前的WebSocket状态
      pre_connect_connections = self.ws_manager.get_active_connections_count()
      pre_connect_wallet_connections = self.ws_manager.get_active_connections_count(wallet_address)
      logger.info(f"WebSocket连接签名验证成功: wallet={wallet_address[:10] if len(wallet_address) > 10 else wallet_address}... (连接前: 总连接数={pre_connect_connections}, 当前钱包连接数={pre_connect_wallet_connections})")
    except Exception as e:
      # 验证过程发生异常
      await websocket.close(code=1008, reason="Authentication error")
      logger.error(f"WebSocket连接鉴权异常: {str(e)}")
      return
    
    # 建立连接
    await self.ws_manager.connect(websocket, wallet_address)
    
    # 记录连接后的WebSocket状态
    post_connect_connections = self.ws_manager.get_active_connections_count()
    post_connect_wallet_connections = self.ws_manager.get_active_connections_count(wallet_address)
    logger.info(f"WebSocket连接已建立: wallet={wallet_address[:10] if len(wallet_address) > 10 else wallet_address}... (连接后: 总连接数={post_connect_connections}, 当前钱包连接数={post_connect_wallet_connections})")
    
    try:
      # 发送连接成功消息
      await websocket.send_text(json.dumps({
        "type": "connection_established",
        "message": "WebSocket established",
        "wallet_address": wallet_address,
        "connection_info": {
          "total_connections": post_connect_connections,
          "wallet_connections": post_connect_wallet_connections
        }
      }))
      
      # 添加连接诊断测试消息
      test_message = {
        "type": "connection_test",
        "timestamp": time.time() * 1000,
        "message": "WebSocket连接测试消息"
      }
      
      # 使用单独的任务发送测试消息，避免阻塞主流程
      asyncio.create_task(
        self.ws_manager.send_message(wallet_address, test_message)
      )
      
      # 监听客户端消息
      while True:
        # 接收客户端消息
        data = await websocket.receive_text()
        
        # 处理心跳消息
        try:
          message = json.loads(data)
          message_type = message.get("type")
          
          if message_type == "ping":
            # 发送pong响应
            pong_response = {
              "type": "pong",
              "timestamp": message.get("timestamp"),
              "server_time": int(time.time() * 1000)
            }
            await websocket.send_text(json.dumps(pong_response))
            
          elif message_type == "connection_check":
            # 连接状态检查
            connection_info = {
              "type": "connection_status",
              "timestamp": int(time.time() * 1000),
              "wallet_address": wallet_address,
              "is_connected": True,
            }
            await websocket.send_text(json.dumps(connection_info))
        except Exception as e:
          logger.error(f"处理WebSocket消息时出错: {e}")
    
    except WebSocketDisconnect:
      # 客户端断开连接
      logger.info(f"客户端断开WebSocket连接: {wallet_address[:10] if len(wallet_address) > 10 else wallet_address}...")
    except Exception as e:
      logger.error(f"WebSocket连接出错: {e}")
    finally:
      # 记录断开前状态
      pre_disconnect_connections = self.ws_manager.get_active_connections_count()
      pre_disconnect_wallet_connections = self.ws_manager.get_active_connections_count(wallet_address)
      
      # 断开连接
      await self.ws_manager.disconnect(websocket, wallet_address)
      
      # 记录断开后状态
      post_disconnect_connections = self.ws_manager.get_active_connections_count()
      post_disconnect_wallet_connections = self.ws_manager.get_active_connections_count(wallet_address)
      
      logger.info(f"WebSocket连接已清理: wallet={wallet_address[:10] if len(wallet_address) > 10 else wallet_address}... " +
                 f"(断开前: 总={pre_disconnect_connections}, 钱包={pre_disconnect_wallet_connections}; " +
                 f"断开后: 总={post_disconnect_connections}, 钱包={post_disconnect_wallet_connections})")

  def notify_task_status_update(self, task) -> None:
    """通知任务状态更新"""
    try:
      if hasattr(task, 'sessionId') and task.sessionId:
        # 获取会话ID
        conversation_id = task.sessionId
        
        # 获取钱包地址
        wallet_address = None
        
        # 从任务历史中获取钱包地址
        if hasattr(task, 'history') and task.history:
          for msg in task.history:
            if (hasattr(msg, 'metadata') and msg.metadata and 
                'wallet_address' in msg.metadata):
              wallet_address = msg.metadata['wallet_address']
              break
        
        # 如果没有从历史中找到，尝试从状态消息中获取
        if not wallet_address and hasattr(task, 'status') and hasattr(task.status, 'message'):
          if (hasattr(task.status.message, 'metadata') and 
              task.status.message.metadata and 
              'wallet_address' in task.status.message.metadata):
            wallet_address = task.status.message.metadata['wallet_address']
        
        if wallet_address:
          # 创建标准格式的任务对象
          formatted_task = self._format_task_for_client(task)
          
          # 创建WebSocket消息，使用与接口一致的格式
          task_response = ListTaskResponse(
            id=str(uuid.uuid4()),
            result=[formatted_task]
          )
          
          ws_message = {
            "type": "task_update",
            "conversation_id": conversation_id,
            "jsonrpc": task_response.jsonrpc,
            "id": task_response.id,
            "result": task_response.result,
            "error": task_response.error
          }
          
          # 发送WebSocket消息
          asyncio.create_task(self.ws_manager.send_message(wallet_address, ws_message))
    except Exception as e:
      print(f"通知任务状态更新时出错: {e}")

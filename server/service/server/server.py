import asyncio
import base64
import threading
import os
import uuid
import logging
import json
from typing import Any, Optional
from fastapi import APIRouter
from fastapi import Request, Response
from common.types import Message, Task, FilePart, FileContent, TaskStatus, TaskState, Artifact
from .in_memory_manager import InMemoryFakeAgentManager
from .application_manager import ApplicationManager
from .adk_host_manager import ADKHostManager, get_message_id
from .user_session_manager import UserSessionManager
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
        self._list_conversation,
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
    if not self.use_multi_user:
      return self.default_manager
      
    wallet_address = self._get_wallet_address(request)
    if not wallet_address:
      logger.warning("使用默认管理器处理请求")
      return self.default_manager
    
    # 更新用户活跃状态并启动订阅检查
    self._update_user_activity(wallet_address)
      
    return self.user_session_manager.get_host_manager(wallet_address)
    
  def _update_user_activity(self, wallet_address: str):
    """更新用户活跃状态并启动订阅检查"""
    if self.use_multi_user and wallet_address:
      try:
        # 更新用户活跃状态
        self.user_session_manager.update_user_activity(wallet_address)
        
        # 启动订阅检查定时任务
        self.user_session_manager.subscription_checker.start_subscription_checker(wallet_address)
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
    
    # 改进的异步任务处理，增强稳定性和错误恢复能力
    async def process_message_with_timeout():
        """使用超时机制处理消息"""
        try:
            # 增加超时时间到60秒，确保有足够的处理时间
            await asyncio.wait_for(
                manager.process_message(message),
                timeout=60.0
            )
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
    
    # 使用全局线程池运行异步任务，避免创建过多线程
    # 从全局变量获取线程池
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
    
    # 提交任务到线程池
    thread_pool.submit(run_async_task)
    
    return SendMessageResponse(result=MessageInfo(
        message_id=message.metadata['message_id'],
        conversation_id=message.metadata['conversation_id'] if 'conversation_id' in message.metadata else '',
    ))

  async def _list_messages(self, request: Request):
    message_data = await request.json()
    conversation_id = message_data['params']
    
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    
    # 如果没有获取到
    if not wallet_address and self.use_multi_user:
       wallet_address='11111111111111111111111111111111'
    
    # 如果是多用户模式且能获取到钱包地址，从数据库读取消息
    if self.use_multi_user and wallet_address:
      try:
        # 从数据库获取消息，同时使用wallet_address和conversation_id确保查询正确
        messages = self.user_session_manager.get_conversation_messages(
            conversation_id=conversation_id,
            wallet_address=wallet_address,
            limit=20
        )
        if messages:
          # 将数据库格式的消息转换为Message对象
          from common.types import Message, TextPart, DataPart, FilePart, FileContent
          converted_messages = []
          
          for msg_data in messages:
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
                metadata = {'message_id': msg_data.get('message_id'), 'conversation_id': conversation_id}
                if 'metadata' in content:
                  for key, value in content.get('metadata', {}).items():
                    metadata[key] = value
                
                # 创建消息对象
                message = Message(
                  role=msg_data.get('role', 'user'),
                  parts=parts,
                  metadata=metadata
                )
                
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
          
          # 返回处理后的消息
          return ListMessageResponse(result=self.cache_content(converted_messages))
      except Exception as e:
        logger.error(f"从数据库读取消息时出错: {e}")
    
    # 如果不是多用户模式或无法从数据库获取，则使用原有的内存模式
    manager = self._get_user_manager(request)
    conversation = manager.get_conversation(conversation_id)
    
    if conversation:
      # 限制返回最新的10条消息
      if hasattr(conversation, 'messages') and len(conversation.messages) > 10:
        messages_to_return = conversation.messages[-10:]
      else:
        messages_to_return = conversation.messages
      
      return ListMessageResponse(result=self.cache_content(messages_to_return))
    
    return ListMessageResponse(result=[])

  def cache_content(self, messages: list[Message]):
    rval = []
    for m in messages:
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
      rval.append(m)
    return rval

  async def _pending_messages(self, request: Request):
    manager = self._get_user_manager(request)
    return PendingMessageResponse(result=manager.get_pending_messages())

  async def _list_conversation(self, request: Request):
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
    except:
      # 如果无法解析JSON或没有参数，默认为None
      conversation_id = None
    
    # 获取用户钱包地址
    wallet_address = self._get_wallet_address(request)
    
    # 现有逻辑：从内存中获取任务
    memory_tasks = manager.tasks
    
    # 如果指定了conversation_id，过滤内存中的任务
    if conversation_id:
      memory_tasks = [task for task in memory_tasks if 
                     hasattr(task, 'sessionId') and task.sessionId == conversation_id]
    
    # 如果是多用户模式且有钱包地址，尝试从数据库获取更多任务信息
    if self.use_multi_user and wallet_address:
      try:
        # 获取用户会话管理器
        user_session_manager = UserSessionManager.get_instance()
        
        # 如果数据库中有会话但运行在内存模式，仅返回内存中的任务
        if user_session_manager._memory_mode:
          return ListTaskResponse(result=memory_tasks)
        
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
        
        # 合并内存中的任务和数据库中的任务，确保没有重复
        if db_tasks:
          # 转换数据库任务为Task对象
          from common.types import Task, TaskStatus, TaskState
          from datetime import datetime
          
          # 获取内存中任务的ID列表
          memory_task_ids = [t.id for t in memory_tasks]
          
          # 将数据库中的任务添加到结果中（如果不在内存中）
          for db_task in db_tasks:
            if db_task['id'] not in memory_task_ids:
              # 创建一个基本的Task对象
              try:
                status = TaskStatus(
                  state=db_task['state'] if db_task['state'] else TaskState.UNKNOWN,
                  timestamp=datetime.now()
                )
                
                task = Task(id=db_task['id'], sessionId=db_task['sessionId'], status=status)
                
                # 添加到结果列表
                memory_tasks.append(task)
              except Exception as e:
                print(f"转换数据库任务时出错: {e}")
      except Exception as e:
        # 错误处理不应影响现有流程
        print(f"获取数据库任务时出错: {e}")
    
    # 返回合并后的任务列表
    return ListTaskResponse(result=memory_tasks)

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
        if not self.use_multi_user:
            # 非多用户模式，返回默认管理器的代理
            manager = self._get_user_manager(request)
            return ListAgentResponse(result=manager.agents)
        else:
            # 多用户模式但没有钱包地址，返回空列表
            logger.warning("获取代理列表时未提供钱包地址")
            return ListAgentResponse(result=[])
    
    # 如果是多用户模式，从数据库获取代理信息
    if self.use_multi_user:
        # 先刷新用户的代理列表
        self.user_session_manager.refresh_user_agents(wallet_address)
        
        # 从数据库查询代理信息
        agents = self.user_session_manager.queryAgentsByAddress(wallet_address)
        
        # 添加调试日志
        print("从数据库获取的代理信息:")
        print(f"代理数量: {len(agents)}")
        for i, agent in enumerate(agents):
            print(f"代理 {i+1}:")
            print(f"  URL: {agent.get('url')}")
            print(f"  在线状态: {agent.get('is_online')}")
            print(f"  过期时间: {agent.get('expire_at')}")
            print(f"  NFT Mint ID: {agent.get('nft_mint_id')}")
        
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
        
        # 调试日志
        print("返回的响应:")
        print(f"代理数量: {len(response.result) if response.result else 0}")
        for i, agent in enumerate(response.result or []):
            print(f"代理 {i+1}:")
            if hasattr(agent, 'model_dump'):
                agent_dict = agent.model_dump()
                print(f"  URL: {agent_dict.get('url')}")
                print(f"  在线状态: {agent_dict.get('is_online')}")
                print(f"  过期时间: {agent_dict.get('expire_at')}")
                print(f"  NFT Mint ID: {agent_dict.get('nft_mint_id')}")
            else:
                print(f"  数据: {agent}")
                
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

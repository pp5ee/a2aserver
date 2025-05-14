import asyncio
import datetime
import json
import os
from typing import Tuple, Optional, Any
import uuid
from service.types import Conversation, Event
from common.types import (
    Message,
    Task,
    TextPart,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    Artifact,
    AgentCard,
    DataPart,
    FilePart,
    FileContent,
    Part,
)
from hosts.multiagent.host_agent import HostAgent
from hosts.multiagent.remote_agent_connection import (
    TaskCallbackArg,
)
from utils.agent_card import get_agent_card
from service.server.application_manager import ApplicationManager
from service.server.websocket_manager import WebSocketManager
from google.adk import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.events.event import Event as ADKEvent
from google.adk.events.event_actions import EventActions as ADKEventActions
from google.genai import types
import base64
import time


class ADKHostManager(ApplicationManager):
  """An implementation of memory based management with fake agent actions

  This implements the interface of the ApplicationManager to plug into
  the AgentServer. This acts as the service contract that the Mesop app
  uses to send messages to the agent and provide information for the frontend.
  """
  _conversations: list[Conversation]
  _messages: list[Message]
  _tasks: list[Task]
  _events: dict[str, Event]
  _pending_message_ids: list[str]
  _agents: list[AgentCard]
  _task_map: dict[str, str]

  def __init__(self, api_key: str = "", uses_vertex_ai: bool = False, headers: dict = None):
    self._conversations = []
    self._messages = []
    self._tasks = []
    self._events = {}
    self._pending_message_ids = []
    self._agents = []
    self._artifact_chunks = {}
    self._session_service = InMemorySessionService()
    self._artifact_service = InMemoryArtifactService()
    self._memory_service = InMemoryMemoryService()
    self.headers = headers or {}
    self._host_agent = HostAgent([], self.task_callback, headers=self.headers)
    self.user_id = "test_user"
    self.app_name = "A2A"
    self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
    self.uses_vertex_ai = uses_vertex_ai or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
    
    # 获取WebSocket管理器实例
    self.ws_manager = WebSocketManager.get_instance()
    
    # Set environment variables based on auth method
    if self.uses_vertex_ai:
      os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

    elif self.api_key:
      # Use API key authentication
      os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
      os.environ["GOOGLE_API_KEY"] = self.api_key
      
    self._initialize_host()
    
    # Map of message id to task id
    self._task_map = {}
    # Map to manage 'lost' message ids until protocol level id is introduced
    self._next_id = {} # dict[str, str]: previous message to next message

  def update_api_key(self, api_key: str):
    """Update the API key without reinitializing the host to avoid session issues"""
    if api_key and api_key != self.api_key:
      self.api_key = api_key
      
      # Only update environment if not using Vertex AI
      if not self.uses_vertex_ai:
        os.environ["GOOGLE_API_KEY"] = api_key
        # 不再调用self._initialize_host()以避免会话问题

  def _initialize_host(self):
    agent = self._host_agent.create_agent()
    self._host_runner = Runner(
        app_name=self.app_name,
        agent=agent,
        artifact_service=self._artifact_service,
        session_service=self._session_service,
        memory_service=self._memory_service,
    )

  def create_conversation(self) -> Conversation:
    session = self._session_service.create_session(
        app_name=self.app_name,
        user_id=self.user_id)
    conversation_id = session.id
    c = Conversation(conversation_id=conversation_id, is_active=True)
    self._conversations.append(c)
    return c

  def sanitize_message(self, message: Message) -> Message:
    if not message.metadata:
      message.metadata = {}
    if 'message_id' not in message.metadata:
      message.metadata.update({'message_id': str(uuid.uuid4())})
    if 'conversation_id' in message.metadata:
      conversation = self.get_conversation(message.metadata['conversation_id'])
      if conversation:
        if conversation.messages:
          # Get the last message
          last_message_id = get_message_id(conversation.messages[-1])
          if last_message_id:
            message.metadata.update({'last_message_id': last_message_id})
    return message

  async def process_message(self, message: Message):
    # 添加消息处理开始时间记录
    start_time = time.time()
    
    # 获取消息ID和会话ID，用于追踪和错误处理
    message_id = get_message_id(message)
    conversation_id = (
        message.metadata['conversation_id']
        if 'conversation_id' in message.metadata
        else None
    )
    
    # 错误检查：确保有效的消息ID和会话ID
    if not message_id:
      print(f"警告: 消息没有有效的ID，跳过处理")
      return
    
    if not conversation_id:
      print(f"警告: 消息 {message_id} 没有有效的会话ID，跳过处理")
      if message_id in self._pending_message_ids:
        self._pending_message_ids.remove(message_id)
      return
    
    # 添加消息到处理队列
    try:
      self._messages.append(message)
      self._pending_message_ids.append(message_id)
      
      # 获取或创建会话
      conversation = self.get_conversation(conversation_id)
      if conversation:
        conversation.messages.append(message)
      else:
        # 如果会话不存在，创建新会话
        print(f"会话 {conversation_id} 不存在，创建新会话")
        conversation = self.create_conversation()
        conversation.conversation_id = conversation_id
        conversation.messages.append(message)
      
      # 添加事件记录
      self.add_event(Event(
          id=str(uuid.uuid4()),
          actor='user',
          content=message,
          timestamp=datetime.datetime.utcnow().timestamp(),
      ))
      
      final_event: GenAIEvent | None = None
      
      # 会话管理
      try:
        session = self._session_service.get_session(
            app_name='A2A',
            user_id='test_user',
            session_id=conversation_id)
        
        # 检查会话是否有效
        if not session or not hasattr(session, 'state') or session.state is None:
          # 创建新会话
          session = self._session_service.create_session(
              app_name=self.app_name,
              user_id=self.user_id,
              session_id=conversation_id)
      except Exception as e:
        # 会话获取失败，记录错误并创建新会话
        
        session = self._session_service.create_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=conversation_id)
            
      # 更新会话状态
      state_update = {
          'input_message_metadata': message.metadata,
          'session_id': conversation_id
      }
      
      last_message_id = get_last_message_id(message)
      if (last_message_id and
          last_message_id in self._task_map and
          task_still_open(next(
              filter(
                  lambda x: x.id == self._task_map[last_message_id],
                  self._tasks),
              None))):
            state_update['task_id'] = self._task_map[last_message_id]
      
      # 更新会话状态，容错处理
      try:
        self._session_service.append_event(session, ADKEvent(
            id=ADKEvent.new_id(),
            author="host_agent",
            invocation_id=ADKEvent.new_id(),
            actions=ADKEventActions(state_delta=state_update),
        ))
      except AttributeError as e:
        print(f"警告: 无法更新会话状态: {e}")
      except Exception as e:
        print(f"更新会话状态时出错: {e}")
      
      # 处理消息，使用更健壮的错误处理
      response = None
      try:
        # 设置超时控制，防止无限等待
        async def process_with_timeout():
          nonlocal final_event
          async for event in self._host_runner.run_async(
              user_id=self.user_id,
              session_id=conversation_id,
              new_message=self.adk_content_from_message(message)
          ):
            self.add_event(Event(
                id=event.id,
                actor=event.author,
                content=self.adk_content_to_message(event.content, conversation_id),
                timestamp=event.timestamp,
            ))
            print(f"event: {event}")
            final_event = event
        
        # 执行带超时的处理，90秒超时
        await asyncio.wait_for(process_with_timeout(), timeout=90.0)
        
        # 处理结果，生成响应消息
        if final_event:
          final_event.content.role = 'model'
          response = self.adk_content_to_message(final_event.content, conversation_id)
          last_message_id = get_message_id(message)
          new_message_id = ""
          if last_message_id and last_message_id in self._next_id:
            new_message_id = self._next_id[last_message_id]
          else:
            new_message_id = str(uuid.uuid4())
            last_message_id = None
          response.metadata = {
              **message.metadata,
              **{'last_message_id': last_message_id,
                 'message_id': new_message_id}
          }
          self._messages.append(response)
    
          # 保存代理响应到数据库
          try:
            # 从消息元数据中获取钱包地址
            wallet_address = message.metadata.get('wallet_address')
            if wallet_address and conversation_id:
              from service.server.user_session_manager import UserSessionManager
              UserSessionManager.get_instance().save_message_from_object(
                wallet_address=wallet_address,
                message=response
              )
              print(f"已保存代理响应到数据库，消息ID: {new_message_id}")
              
              # 通过WebSocket推送消息通知
              try:
                # 构建WebSocket消息
                ws_message = {
                  "type": "new_message",
                  "conversation_id": conversation_id,
                  "message": {
                    "id": new_message_id,
                    "role": "agent",
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
                
                # 确保消息内容不为空 
                if not ws_message["message"]["content"]:
                  print(f"警告: WebSocket消息内容为空，部分内容可能无法正常显示")
                
                # 异步发送WebSocket消息，确保执行
                send_task = asyncio.create_task(self.ws_manager.send_message(wallet_address, ws_message))
                
                # 尝试等待任务完成，最多等待5秒
                try:
                  await asyncio.wait_for(send_task, timeout=5.0)
                  print(f"已成功通过WebSocket推送代理响应，消息ID: {new_message_id}")
                except asyncio.TimeoutError:
                  print(f"WebSocket消息发送超时，但任务仍在后台执行")
                
                # 如果是重要消息，尝试多次发送以增加可靠性（最多重试3次）
                max_retries = 3
                retry_count = 0
                retry_delay = 1.0  # 秒
                
                # 在消息发送失败时，安排定时重发（仅对agent消息执行）
                async def retry_send():
                  nonlocal retry_count
                  while retry_count < max_retries:
                    await asyncio.sleep(retry_delay * (retry_count + 1))  # 递增延迟
                    try:
                      print(f"正在重试发送WebSocket消息，尝试 #{retry_count+1}，消息ID: {new_message_id}")
                      await self.ws_manager.send_message(wallet_address, ws_message)
                      print(f"WebSocket消息重发成功，尝试 #{retry_count+1}，消息ID: {new_message_id}")
                      break  # 发送成功则退出循环
                    except Exception as e:
                      print(f"WebSocket消息重发失败，尝试 #{retry_count+1}，错误: {e}")
                      retry_count += 1
                
                # 创建重试任务（不等待完成，让它在后台运行）
                asyncio.create_task(retry_send())
                
              except Exception as e:
                print(f"通过WebSocket发送消息通知时出错: {e}")
              
              # 如果有相关任务，将响应添加到任务历史记录
              for task in self._tasks:
                if task.sessionId == conversation_id:
                  # 确保任务有历史消息字段
                  if not hasattr(task, 'history') or task.history is None:
                    task.history = []
                  
                  # 检查消息是否已存在于历史记录中
                  message_id = new_message_id
                  existing_ids = [get_message_id(m) for m in task.history if get_message_id(m) is not None]
                  if message_id in existing_ids:
                    print(f"消息 {message_id} 已存在于任务 {task.id} 的历史记录中，跳过添加")
                    break
                  
                  # 添加代理响应到任务历史
                  task.history.append(response)
                  print(f"已将代理响应消息 {message_id} 添加到任务 {task.id} 的历史记录中")
                  
                  # 保存更新后的任务
                  self._save_task_to_db(task)
                  break
          except Exception as e:
            print(f"保存代理响应到数据库时出错: {e}")
    
        # 将响应添加到会话
        if response and conversation:
          conversation.messages.append(response)
          
      except asyncio.TimeoutError:
        # 处理超时，生成超时提示消息
        print(f"消息 {message_id} 处理超时")
        error_msg = Message(
          id=f"timeout_{message_id}",
          role="agent",
          parts=[TextPart(text="消息处理超时，请稍后重试")],
          metadata={
            'conversation_id': conversation_id,
            'message_id': f"timeout_{message_id}"
          }
        )
        if conversation:
          conversation.messages.append(error_msg)
          
      except Exception as e:
        # 处理其他错误
        import traceback
        print(f"处理消息 {message_id} 时出错: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        error_msg = Message(
          id=f"error_{message_id}",
          role="agent",
          parts=[TextPart(text=f"处理消息时出错: {str(e)}")],
          metadata={
            'conversation_id': conversation_id,
            'message_id': f"error_{message_id}"
          }
        )
        if conversation:
          conversation.messages.append(error_msg)
      
      # 清理：从待处理列表中移除
      if message_id in self._pending_message_ids:
        self._pending_message_ids.remove(message_id)
        
      # 记录处理时间
      processing_time = time.time() - start_time
      print(f"消息 {message_id} 处理完成，耗时: {processing_time:.2f}秒")
      
    except Exception as outer_e:
      # 捕获外部异常，确保不会导致服务器崩溃
      import traceback
      print(f"处理消息 {message_id} 的外层异常: {outer_e}")
      print(f"外层错误详情: {traceback.format_exc()}")
      
      # 清理：从待处理列表中移除
      if message_id in self._pending_message_ids:
        self._pending_message_ids.remove(message_id)

  def add_task(self, task: Task):
    self._tasks.append(task)

  def update_task(self, task: Task):
    for i, t in enumerate(self._tasks):
      if t.id == task.id:
        self._tasks[i] = task
        return

  def task_callback(self, task: TaskCallbackArg, agent_card: AgentCard):
    self.emit_event(task, agent_card)
    current_task = None
    
    # 获取会话ID
    conversation_id = get_conversation_id(task)
    
    if isinstance(task, TaskStatusUpdateEvent):
      current_task = self.add_or_get_task(task)
      current_task.status = task.status
      self.attach_message_to_task(task.status.message, current_task.id)
      
      # 检查消息是否存在并且有效，然后添加到历史记录
      if task.status and task.status.message:
        self.insert_message_history(current_task, task.status.message)
      
      self.update_task(current_task)
      self.insert_id_trace(task.status.message)
      
      # 推送任务状态更新
      self._push_task_update_to_websocket(current_task)
      
      # 尝试保存任务到数据库
      self._save_task_to_db(current_task)
      
      return current_task
    elif isinstance(task, TaskArtifactUpdateEvent):
      current_task = self.add_or_get_task(task)
      self.process_artifact_event(current_task, task)
      self.update_task(current_task)
      
      # 推送任务产出物更新
      self._push_task_update_to_websocket(current_task)
      
      # 尝试保存任务到数据库
      self._save_task_to_db(current_task)
      
      return current_task
    # Otherwise this is a Task, either new or updated
    elif not any(filter(lambda x: x.id == task.id, self._tasks)):
      self.attach_message_to_task(task.status.message, task.id)
      self.insert_id_trace(task.status.message)
      self.add_task(task)
      
      # 推送新任务
      self._push_task_update_to_websocket(task)
      
      # 尝试保存任务到数据库
      self._save_task_to_db(task)
      
      return task
    else:
      self.attach_message_to_task(task.status.message, task.id)
      self.insert_id_trace(task.status.message)
      self.update_task(task)
      
      # 推送任务更新
      self._push_task_update_to_websocket(task)
      
      # 尝试保存任务到数据库
      self._save_task_to_db(task)
      
      return task
      
  def _push_task_update_to_websocket(self, task: Task):
    """将任务更新推送到WebSocket"""
    try:
      # 获取钱包地址
      wallet_address = None
      
      # 从任务状态消息中获取钱包地址
      if task.status and task.status.message and task.status.message.metadata:
        wallet_address = task.status.message.metadata.get('wallet_address')
      
      # 如果没有在状态消息中找到，尝试在任务历史中查找
      if not wallet_address and hasattr(task, 'history') and task.history:
        for message in task.history:
          if message.metadata and 'wallet_address' in message.metadata:
            wallet_address = message.metadata.get('wallet_address')
            break
      
      # 如果找不到钱包地址，不执行推送
      if not wallet_address:
        print(f"无法推送任务更新：找不到钱包地址，任务ID: {task.id}")
        return
      
      # 获取会话ID
      conversation_id = task.sessionId if hasattr(task, 'sessionId') else None
      if not conversation_id:
        print(f"无法推送任务更新：找不到会话ID，任务ID: {task.id}")
        return
      
      # 创建任务状态消息
      task_status = {
        "type": "task_update",
        "conversation_id": conversation_id,
        "task": {
          "id": task.id,
          "sessionId": task.sessionId,
          "status": {
            "state": task.status.state.value if hasattr(task.status.state, 'value') else str(task.status.state),
            "message": ""
          }
        }
      }
      
      # 获取与任务关联的消息ID
      message_id = None
      
      # 首先从任务状态消息的元数据中查找
      if task.status and task.status.message and task.status.message.metadata:
        message_id = task.status.message.metadata.get('message_id')
      
      # 如果没找到，尝试从任务历史中查找最早的用户消息ID
      if not message_id and hasattr(task, 'history') and task.history:
        # 首先查找最早的用户消息
        for msg in task.history:
          if msg.role == 'user' and msg.metadata and 'message_id' in msg.metadata:
            message_id = msg.metadata.get('message_id')
            break
        
        # 如果还没找到，尝试找任何含有message_id的消息
        if not message_id:
          for msg in task.history:
            if msg.metadata and 'message_id' in msg.metadata:
              message_id = msg.metadata.get('message_id')
              break
      
      # 将消息ID添加到任务状态消息中
      if message_id:
        task_status["message_id"] = message_id
        print(f"任务更新消息关联到消息ID: {message_id}, 任务ID: {task.id}")
      else:
        print(f"警告: 无法找到与任务关联的消息ID, 任务ID: {task.id}")
      
      # 添加状态消息文本
      if task.status.message:
        if hasattr(task.status.message, 'parts') and task.status.message.parts:
          for part in task.status.message.parts:
            if part.type == 'text' and hasattr(part, 'text'):
              task_status["task"]["status"]["message"] = part.text
              break
        elif hasattr(task.status.message, 'text'):
          # 直接使用text属性
          task_status["task"]["status"]["message"] = task.status.message.text
        elif isinstance(task.status.message, str):
          # 如果是字符串类型
          task_status["task"]["status"]["message"] = task.status.message
        elif isinstance(task.status.message, dict) and 'text' in task.status.message:
          # 如果是字典类型且包含text字段
          task_status["task"]["status"]["message"] = task.status.message['text']
      
      # 添加时间戳
      if hasattr(task.status, 'timestamp'):
        task_status["task"]["status"]["timestamp"] = task.status.timestamp.isoformat() if hasattr(task.status.timestamp, 'isoformat') else str(task.status.timestamp)
      
      # 添加历史记录
      if hasattr(task, 'history') and task.history:
        task_status["task"]["history"] = [
          {
            "role": msg.role,
            "parts": [
              {
                "type": part.type,
                "text": part.text if hasattr(part, 'text') else None
              }
              for part in msg.parts
              if part.type == 'text'
            ]
          }
          for msg in task.history
        ]
      
      # 添加artifacts
      if hasattr(task, 'artifacts') and task.artifacts:
        task_status["task"]["artifacts"] = [
          {
            "name": artifact.name,
            "parts": [
              {
                "type": part.type,
                "text": part.text if hasattr(part, 'text') else None
              }
              for part in artifact.parts
              if part.type == 'text'
            ]
          }
          for artifact in task.artifacts
        ]
      
      # 异步发送WebSocket消息
      # 创建异步任务发送消息，但不等待
      async def send_task_update():
        try:
          await self.ws_manager.send_message(wallet_address, task_status)
          print(f"已成功推送任务更新，任务ID: {task.id}, 状态: {task_status['task']['status']['state']}")
        except Exception as e:
          print(f"发送任务更新时出错: {e}")
      
      # 使用事件循环运行异步任务
      try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
          # 如果事件循环已经在运行，创建任务但不等待结果
          asyncio.create_task(send_task_update())
        else:
          # 如果事件循环未运行，则运行直到完成
          loop.run_until_complete(send_task_update())
      except RuntimeError:
        # 如果获取事件循环失败，创建新的事件循环
        print("获取事件循环失败，创建新的事件循环以发送任务更新")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(send_task_update())
        new_loop.close()
      
    except Exception as e:
      print(f"推送任务更新到WebSocket时出错: {e}")
      import traceback
      print(traceback.format_exc())

  def _save_task_to_db(self, task: Task):
    """尝试将任务保存到数据库"""
    try:
      # 从任务状态消息中获取钱包地址
      wallet_address = None
      if task.status and task.status.message and task.status.message.metadata:
        wallet_address = task.status.message.metadata.get('wallet_address')
      
      # 如果没有在状态消息中找到，尝试在任务历史中查找
      if not wallet_address and task.history:
        for message in task.history:
          if message.metadata and 'wallet_address' in message.metadata:
            wallet_address = message.metadata.get('wallet_address')
            break
      
      # 如果找到了钱包地址，保存任务到数据库
      if wallet_address:
        from service.server.user_session_manager import UserSessionManager
        UserSessionManager.get_instance().save_task(wallet_address, task)
        print(f"已保存任务 {task.id} 到数据库")
    except Exception as e:
      print(f"保存任务到数据库时出错: {e}")

  def emit_event(self, task: TaskCallbackArg, agent_card: AgentCard):
    """Emit an event for agent actions."""
    # 检查对象类型，确定如何处理
    content = None
    conversation_id = get_conversation_id(task)
    
    # 如果task没有event属性，是直接的Task对象
    if not hasattr(task, 'event') or task.event is None:
      # 这是直接传入的Task对象
      if hasattr(task, 'status') and task.status:
        if hasattr(task.status, 'message') and task.status.message:
          content = task.status.message
        else:
          content = Message(
            parts=[TextPart(text=str(task.status.state))],
            role="agent",
            metadata={'conversation_id': conversation_id} if conversation_id else {},
          )
      elif hasattr(task, 'artifacts') and task.artifacts:
        parts = []
        for a in task.artifacts:
          if hasattr(a, 'parts'):
            parts.extend(a.parts)
        content = Message(
            parts=parts,
            role="agent",
            metadata={'conversation_id': conversation_id} if conversation_id else {},
        )
      else:
        content = Message(
            parts=[TextPart(text="处理中...")],
            role="agent",
            metadata={'conversation_id': conversation_id} if conversation_id else {},
        )
      
      # 创建一个事件记录
      self.add_event(Event(
        id=str(uuid.uuid4()),
        actor=agent_card.name,
        content=content,
        timestamp=datetime.datetime.utcnow().timestamp(),
      ))
      return
    
    # 以下是原来的处理逻辑，处理有event属性的对象
    if not task.event:
      return
    conversation_id = get_conversation_id(task.event)
    if not conversation_id:
      return
    event_id = str(uuid.uuid4())
    if task.event.type == "task_status_update":
      e = task.event  # type: TaskStatusUpdateEvent
      self.add_event(Event(
          id=event_id,
          actor=agent_card.name,
          content=e,
          timestamp=datetime.datetime.utcnow().timestamp(),
      ))
      if e.status.state == TaskState.COMPLETE:
        task_id = e.task_id
        task = next(filter(lambda x: x.id == task_id, self._tasks), None)
        if task:
          # We know the task is complete, now try to attach the message
          adk_content = types.Content(
              role='model',
              parts=[types.Part.from_text(text='')],
          )
          response = self.adk_content_to_message(adk_content, conversation_id)
          for h in task.history:
            if h.role == 'agent' and h.parts:
              response = h
              break
          message_id = get_message_id(task.message)
          last_message_id = get_last_message_id(task.message)
          if message_id:
            response.metadata.update({'message_id': str(uuid.uuid4())})
            response.metadata.update({'conversation_id': conversation_id})
            response.metadata.update({'last_message_id': message_id})
            self._next_id[message_id] = response.metadata['message_id']
            self._messages.append(response)
            if last_message_id and message_id in self._pending_message_ids:
              self._pending_message_ids.remove(message_id)
            conversation = self.get_conversation(conversation_id)
            if conversation:
              conversation.messages.append(response)
            
            # 尝试保存代理响应的消息
            try:
              from service.server.user_session_manager import UserSessionManager
              # 检查消息中是否有钱包地址信息
              wallet_address = None
              if task.message and task.message.metadata and 'wallet_address' in task.message.metadata:
                wallet_address = task.message.metadata['wallet_address']
              
              # 如果没有钱包地址，尝试从会话中查找
              if not wallet_address and conversation_id:
                # 查找会话相关的钱包地址（这需要在UserSessionManager中实现获取会话对应钱包地址的功能）
                wallet_address = UserSessionManager.get_instance().get_conversation_wallet_address(conversation_id)
              
              # 保存消息
              if wallet_address:
                UserSessionManager.get_instance().save_message_from_object(
                  wallet_address=wallet_address,
                  message=response
                )
            except Exception as e:
              print(f"保存代理响应消息时出错: {e}")
    elif task.event.type == "task_artifact_update":
      e = task.event  # type: TaskArtifactUpdateEvent
      self.add_event(Event(
          id=event_id,
          actor=agent_card.name,
          content=e,
          timestamp=datetime.datetime.utcnow().timestamp(),
      ))
      # We know that this might create a complete event.
      self.process_artifact_event(
          next(filter(
              lambda x: x.id == e.task_id, self._tasks), None),
          e)

  def attach_message_to_task(self, message: Message | None, task_id: str):
    if message and message.metadata and 'message_id' in message.metadata:
      self._task_map[message.metadata['message_id']] = task_id

  def insert_id_trace(self, message: Message | None):
    if not message:
      return
    message_id = get_message_id(message)
    last_message_id = get_last_message_id(message)
    if message_id and last_message_id:
      self._next_id[last_message_id] = message_id

  def insert_message_history(self, task: Task, message: Message | None):
    """将消息添加到任务的历史记录中"""
    if message is None:
      return
      
    if task.history is None:
      task.history = []
    
    # 检查是否已存在相同消息ID的历史记录
    message_id = get_message_id(message)
    if not message_id:
      return
      
    # 检查是否已存在相同ID的消息，使用精确比较
    existing_ids = [get_message_id(m) for m in task.history if get_message_id(m) is not None]
    if message_id in existing_ids:
      print(f"消息 {message_id} 已存在于任务历史中，跳过添加")
      return
    
    # 添加消息到历史记录
    task.history.append(message)
    print(f"已将消息 {message_id} 添加到任务 {task.id} 的历史记录中")
    
    # 尝试保存任务到数据库
    self._save_task_to_db(task)

  def add_or_get_task(self, task: TaskCallbackArg):
    current_task = next(filter(lambda x: x.id == task.id, self._tasks), None)
    if not current_task:
      conversation_id = None
      if task.metadata and 'conversation_id' in task.metadata:
        conversation_id = task.metadata['conversation_id']
      current_task = Task(
          id=task.id,
          status=TaskStatus(state = TaskState.SUBMITTED), #initialize with submitted
          metadata=task.metadata,
          artifacts = [],
          sessionId=conversation_id,
      )
      self.add_task(current_task)
      return current_task

    return current_task

  def process_artifact_event(self, current_task,task_update_event):
    artifact = task_update_event.artifact
    print(f"Artifact in adk process_artifact_event function: {artifact}")
    
    # 确保 artifacts 列表存在
    if not current_task.artifacts:
      current_task.artifacts = []
      
    if not artifact.append:
      # 收到首个块或完整制品
      if artifact.lastChunk is None or artifact.lastChunk:
        # 这是完整的制品，直接添加
        current_task.artifacts.append(artifact)
        
        # 修改点：如果这是最后一个块（lastChunk=True），确保所有临时存储的制品也被添加
        if artifact.lastChunk and task_update_event.id in self._artifact_chunks:
          # 按照索引顺序整理和添加所有临时制品
          chunks = self._artifact_chunks.get(task_update_event.id, {})
          for index in sorted(chunks.keys()):
            current_task.artifacts.append(chunks[index])
          
          # 清理临时存储
          self._artifact_chunks.pop(task_update_event.id, None)
      else:
        # 这是制品的一个块，存入临时存储
        if task_update_event.id not in self._artifact_chunks:
          self._artifact_chunks[task_update_event.id] = {}
        self._artifact_chunks[task_update_event.id][artifact.index] = artifact
    else:
      # 接收到追加块，添加到现有临时制品
      current_temp_artifact = self._artifact_chunks[task_update_event.id][artifact.index]
      current_temp_artifact.parts.extend(artifact.parts)
      
      if artifact.lastChunk:
        # 这是最后一个块，添加完成的制品
        current_task.artifacts.append(current_temp_artifact)
        
        # 删除此块的临时存储
        del self._artifact_chunks[task_update_event.id][artifact.index]
        
        # 修改点：同样确保所有其他临时制品也被添加
        chunks = self._artifact_chunks.get(task_update_event.id, {})
        for index in sorted(chunks.keys()):
          current_task.artifacts.append(chunks[index])
        
        # 清理整个任务的临时存储
        self._artifact_chunks.pop(task_update_event.id, None)

  def add_event(self, event: Event):
    self._events[event.id] = event

  def get_conversation(
      self,
      conversation_id: Optional[str]
  ) -> Optional[Conversation]:
    if not conversation_id:
      return None
    return next(
        filter(lambda c: c.conversation_id == conversation_id,
               self._conversations), None)

  def get_pending_messages(self) -> list[Tuple[str, str]]:
    rval = []
    for message_id in self._pending_message_ids:
      if message_id in self._task_map:
        task_id = self._task_map[message_id]
        task = next(filter(lambda x: x.id == task_id, self._tasks), None)
        if not task:
          rval.append((message_id, ""))
        elif task.history and task.history[-1].parts:
          if len(task.history) == 1:
            rval.append((message_id, "Working..."))
          else:
            part = task.history[-1].parts[0]
            rval.append((
                message_id,
                part.text if part.type == "text" else "Working..."))
      else:
        rval.append((message_id, ""))
    return rval

  def register_agent(self, url):
    # 处理URL格式
    # 处理以@开头的URL
    if url.startswith('@http://') or url.startswith('@https://'):
      print(f"检测到以@开头的URL，移除前缀@: {url}")
      url = url[1:]  # 去掉@符号
    
    # 去除.well-known/agent.json后缀，我们将在获取时添加
    if "/.well-known/agent.json" in url:
      url = url.split("/.well-known/agent.json")[0]
      print(f"移除.well-known/agent.json后缀，使用基本URL: {url}")
    
    # 检查URL是否以http://或https://开头
    if not (url.startswith('http://') or url.startswith('https://')):
      url = 'http://' + url
      print(f"添加http://前缀: {url}")
    
    # 检查代理是否已经注册
    for agent in self._agents:
      if agent.url == url:
        print(f"代理 {url} 已经注册，跳过重复注册")
        return agent
    
    # 注册新代理
    try:
      agent_data = get_agent_card(url)
      if not agent_data.url:
        agent_data.url = url
      self._agents.append(agent_data)
      self._host_agent.register_agent_card(agent_data)
      # 更新host agent定义
      self._initialize_host()
      print(f"成功注册代理: {url}")
      return agent_data
    except Exception as e:
      print(f"注册代理 {url} 失败: {e}")
      # 返回错误信息而不是抛出异常，以便调用者可以处理
      return None

  @property
  def agents(self) -> list[AgentCard]:
    return self._agents

  @property
  def conversations(self) -> list[Conversation]:
    return self._conversations

  @property
  def tasks(self) -> list[Task]:
    return self._tasks

  @property
  def events(self) -> list[Event]:
    return sorted(self._events.values(), key=lambda x: x.timestamp)

  def adk_content_from_message(self, message: Message) -> types.Content:
    print(f"adk_content_from_message: {message}")
    parts: list[types.Part] = []
    for part in message.parts:
      if part.type == "text":
        parts.append(types.Part.from_text(text=part.text))
      elif part.type == "data":
        json_string = json.dumps(part.data)
        parts.append(types.Part.from_text(text=json_string))
      elif part.type == "file":
        if part.uri:
          parts.append(types.Part.from_uri(
              file_uri=part.uri,
              mime_type=part.mimeType
          ))
        elif content_part.bytes:
          parts.append(types.Part.from_bytes(
              data=part.bytes.encode('utf-8'),
              mime_type=part.mimeType)
          )
        else:
          raise ValueError("Unsupported message type")
    return types.Content(parts=parts, role=message.role)

  def adk_content_to_message(self, content: types.Content, conversation_id: str) -> Message:
    print(f"adk_content_to_message CONTEXT: {content}")
    parts: list[Part] = []
    if not content.parts:
      return Message(
          parts=[],
          role=content.role if content.role == 'user' else 'agent',
          metadata={'conversation_id': conversation_id},
      )
    for part in content.parts:
      if part.text:
        # try parse as data
        try:
          data = json.loads(part.text)
          parts.append(DataPart(data=data))
        except:
          parts.append(TextPart(text=part.text))
      elif part.inline_data:
        parts.append(FilePart(
            data=part.inline_data.decode('utf-8'),
            mimeType=part.inline_data.mime_type
        ))
      elif part.file_data:
        parts.append(FilePart(
            file=FileContent(
                uri=part.file_data.file_uri,
                mimeType=part.file_data.mime_type
            )
        ))
      # These aren't managed by the A2A message structure, these are internal
      # details of ADK, we will simply flatten these to json representations.
      elif part.video_metadata:
        parts.append(DataPart(data=part.video_metadata.model_dump()))
      elif part.thought:
        parts.append(TextPart(text="thought"))
      elif part.executable_code:
        parts.append(DataPart(data=part.executable_code.model_dump()))
      elif part.function_call:
        parts.append(DataPart(data=part.function_call.model_dump()))
      elif part.function_response:
        parts.extend(self._handle_function_response(part, conversation_id))
      else:
        raise ValueError("Unexpected content, unknown type")
    return Message(
        role=content.role if content.role == 'user' else 'agent',
        parts=parts,
        metadata={'conversation_id': conversation_id},
    )

  def _handle_function_response(self, part: types.Part, conversation_id: str) -> list[Part]:
    parts = []
    try:
      for p in part.function_response.response['result']:
        if isinstance(p, str):
          parts.append(TextPart(text=p))
        elif isinstance(p, dict):
          if 'type' in p and p['type'] == 'file':
            parts.append(FilePart(**p))
          else:
            parts.append(DataPart(data=p))
        elif isinstance(p, DataPart):
          if 'artifact-file-id' in p.data:
            file_part = self._artifact_service.load_artifact(user_id=self.user_id,
                                                          session_id=conversation_id,
                                                          app_name=self.app_name,
                                                          filename = p.data['artifact-file-id'])
            file_data = file_part.inline_data
            base64_data = base64.b64encode(file_data.data).decode('utf-8')
            parts.append(FilePart(
              file=FileContent(
                  bytes=base64_data, mimeType=file_data.mime_type, name='artifact_file'
              )
            ))
          else:
            parts.append(DataPart(data=p.data))
        else:
          parts.append(TextPart(text=json.dumps(p)))
    except Exception as e:
      print("Couldn't convert to messages:", e)
      parts.append(DataPart(data=part.function_response.model_dump()))
    return parts

def get_message_id(m: Message | None) -> str  | None:
  if not m or not m.metadata or 'message_id' not in m.metadata:
    return None
  return m.metadata['message_id']

def get_last_message_id(m: Message | None) -> str | None:
  if not m or not m.metadata or 'last_message_id' not in m.metadata:
    return None
  return m.metadata['last_message_id']

def get_conversation_id(
    t: (Task |
        TaskStatusUpdateEvent |
        TaskArtifactUpdateEvent |
        Message |
        None)
) -> str | None:
  if (t and
      hasattr(t, 'metadata') and
      t.metadata and
      'conversation_id' in t.metadata):
    return t.metadata['conversation_id']
  return None

def task_still_open(task: Task | None) -> bool:
  if not task:
    return False
  return task.status.state in [
      TaskState.SUBMITTED, TaskState.WORKING, TaskState.INPUT_REQUIRED
  ]


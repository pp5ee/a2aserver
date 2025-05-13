from typing import Callable
import uuid
from common.types import (
    AgentCard,
    Task,
    TaskSendParams,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    TaskStatus,
    TaskState,
)
from common.client import A2AClient

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]

class RemoteAgentConnections:
  """A class to hold the connections to the remote agents."""

  def __init__(self, agent_card: AgentCard, headers: dict = None):
    self.agent_client = A2AClient(agent_card, headers=headers)
    self.card = agent_card

    self.conversation_name = None
    self.conversation = None
    self.pending_tasks = set()

  def get_agent(self) -> AgentCard:
    return self.card

  async def send_task(
      self,
      request: TaskSendParams,
      task_callback: TaskUpdateCallback | None,
  ) -> Task | None:
    """Sends a task to remote agent, returns a task."""
    print(f"[日志] RemoteAgentConnections.send_task 开始: task_id={request.id}, agent={self.card.name}")
    
    # 创建默认任务对象，以防API调用失败
    default_task = Task(
      id=request.id,
      metadata=request.metadata,
      sessionId=request.sessionId,
      status=TaskStatus(state=TaskState.SUBMITTED)
    )
    
    try:
      if self.card.capabilities.streaming:
        print(f"[日志] 使用流式API调用: {self.card.url}")
        task = None
        if task_callback:
          print(f"[日志] 调用流式任务回调，状态: SUBMITTED")
          task_callback(Task(
              id=request.id,
              sessionId=request.sessionId,
              status=TaskStatus(
                  state=TaskState.SUBMITTED,
                  message=request.message,
              ),
              history=[request.message],
          ), self.card)
        try:
          print(f"[日志] 开始流式发送任务")
          async for response in self.agent_client.send_task_streaming(request.model_dump()):
            print(f"[日志] 收到流式响应")
            merge_metadata(response.result, request)
            # For task status updates, we need to propagate metadata and provide
            # a unique message id.
            if (hasattr(response.result, 'status') and
                hasattr(response.result.status, 'message') and
                response.result.status.message):
              merge_metadata(response.result.status.message, request.message)
              m = response.result.status.message
              if not m.metadata:
                m.metadata = {}
              if 'message_id' in m.metadata:
                m.metadata['last_message_id'] = m.metadata['message_id']
              m.metadata['message_id'] = str(uuid.uuid4())
              print(f"[日志] 生成新消息ID: {m.metadata['message_id']}")
            if task_callback:
              print(f"[日志] 调用流式任务回调")
              task = task_callback(response.result, self.card)
            if hasattr(response.result, 'final') and response.result.final:
              print(f"[日志] 收到最终响应，结束流式处理")
              break
          return task
        except Exception as e:
          import traceback
          print(f"[错误] 流式处理过程中出错: {str(e)}")
          print(traceback.format_exc())
          # 如果流式处理失败，返回默认任务，状态为失败
          default_task.status = TaskStatus(
            state=TaskState.FAILED,
            description=f"Stream processing error: {str(e)}"
          )
          return default_task
      else: # Non-streaming
        print(f"[日志] 使用非流式API调用: {self.card.url}")
        try:
          response = await self.agent_client.send_task(request.model_dump())
          print(f"[日志] 收到非流式响应")
          
          merge_metadata(response.result, request)
          # For task status updates, we need to propagate metadata and provide
          # a unique message id.
          if (hasattr(response.result, 'status') and
              hasattr(response.result.status, 'message') and
              response.result.status.message):
            merge_metadata(response.result.status.message, request.message)
            m = response.result.status.message
            if not m.metadata:
              m.metadata = {}
            if 'message_id' in m.metadata:
              m.metadata['last_message_id'] = m.metadata['message_id']
            m.metadata['message_id'] = str(uuid.uuid4())
            print(f"[日志] 生成新消息ID: {m.metadata['message_id']}")

          if task_callback:
            print(f"[日志] 调用非流式任务回调")
            task_callback(response.result, self.card)
            
          print(f"[日志] 任务处理完成: {response.result.id if hasattr(response.result, 'id') else 'unknown'}")
          return response.result
        except Exception as e:
          import traceback
          print(f"[错误] 非流式处理过程中出错: {str(e)}")
          print(traceback.format_exc())
          # 如果非流式处理失败，返回默认任务，状态为失败
          default_task.status = TaskStatus(
            state=TaskState.FAILED,
            description=f"Non-stream processing error: {str(e)}"
          )
          return default_task
    except Exception as e:
      import traceback
      print(f"[错误] 发送任务过程中出错: {str(e)}")
      print(traceback.format_exc())
      # 如果任务处理过程中出现未捕获的异常，返回失败状态的默认任务
      default_task.status = TaskStatus(
        state=TaskState.FAILED,
        description=f"Unexpected error: {str(e)}"
      )
      return default_task

def merge_metadata(target, source):
  if not hasattr(target, 'metadata') or not hasattr(source, 'metadata'):
    return
  if target.metadata and source.metadata:
    target.metadata.update(source.metadata)
  elif source.metadata:
    target.metadata = dict(**source.metadata)


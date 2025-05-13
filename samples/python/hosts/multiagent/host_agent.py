import sys
import asyncio
import functools
import json
import uuid
import threading
import logging
from typing import List, Optional, Callable

from google.genai import types
import base64

from google.adk import Agent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from .remote_agent_connection import (
    RemoteAgentConnections,
    TaskUpdateCallback
)
from common.client import A2ACardResolver
from common.types import (
    AgentCard,
    Message,
    TaskState,
    Task,
    TaskSendParams,
    TextPart,
    DataPart,
    Part,
    TaskStatusUpdateEvent,
)


class HostAgent:
  """The host agent.

  This is the agent responsible for choosing which remote agents to send
  tasks to and coordinate their work.
  """

  def __init__(
      self,
      remote_agent_addresses: List[str],
      task_callback: TaskUpdateCallback | None = None,
      headers: dict = None
  ):
    logging.info(f"Initializing HostAgent, remote agent address count: {len(remote_agent_addresses)}")
    self.task_callback = task_callback
    self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
    self.cards: dict[str, AgentCard] = {}
    self.headers = headers or {}
    for address in remote_agent_addresses:
      logging.info(f"Processing remote agent address: {address}")
      try:
        card_resolver = A2ACardResolver(address)
        card = card_resolver.get_agent_card()
        logging.info(f"Successfully parsed agent card: {card.name}, URL: {card.url}")
        remote_connection = RemoteAgentConnections(card, headers=self.headers)
        self.remote_agent_connections[card.name] = remote_connection
        self.cards[card.name] = card
      except Exception as e:
        import traceback
        logging.error(f"Error processing remote agent address {address}: {str(e)}")
        logging.error(traceback.format_exc())
    agent_info = []
    for ra in self.list_remote_agents():
      agent_info.append(json.dumps(ra))
    self.agents = '\n'.join(agent_info)
    logging.info(f"HostAgent initialization complete, agent count: {len(self.cards)}")

  def register_agent_card(self, card: AgentCard):
    logging.info(f"Registering agent card: {card.name}, URL: {card.url}")
    remote_connection = RemoteAgentConnections(card, headers=self.headers)
    self.remote_agent_connections[card.name] = remote_connection
    self.cards[card.name] = card
    agent_info = []
    for ra in self.list_remote_agents():
      agent_info.append(json.dumps(ra))
    self.agents = '\n'.join(agent_info)
    logging.info(f"Agent registration complete: {card.name}")

  def create_agent(self) -> Agent:
    logging.info("Creating agent")
    try:
      agent = Agent(
          model="gemini-2.0-flash-001",
          name="host_agent",
          instruction=self.root_instruction,
          before_model_callback=self.before_model_callback,
          description=(
              "This agent orchestrates the decomposition of the user request into"
              " tasks that can be performed by the child agents."
          ),
          tools=[
              self.list_remote_agents,
              self.send_task,
          ],
      )
      logging.info("Agent created successfully")
      return agent
    except Exception as e:
      import traceback
      logging.error(f"Error creating agent: {str(e)}")
      logging.error(traceback.format_exc())
      raise e

  def root_instruction(self, context: ReadonlyContext) -> str:
    logging.info("Generating root_instruction")
    current_agent = self.check_state(context)
    logging.info(f"Current active agent: {current_agent['active_agent']}")
    instruction = f"""You are an expert delegator that can delegate the user request to the
appropriate remote agents.

Discovery:
- You can use `list_remote_agents` to list the available remote agents you
can use to delegate the task.

Execution:
- For actionable tasks, you can use `create_task` to assign tasks to remote agents to perform.
Be sure to include the remote agent name when you respond to the user.

You can use `check_pending_task_states` to check the states of the pending
tasks.

Please rely on tools to address the request, and don't make up the response. If you are not sure, please ask the user for more details.
Focus on the most recent parts of the conversation primarily.

If there is an active agent, send the request to that agent with the update task tool.
If there are some general questions that do not need the active agent, you can answer them yourself.

Agents:
{self.agents}

Current agent: {current_agent['active_agent']}
"""
    logging.info("root_instruction generation completed")
    return instruction

  def check_state(self, context: ReadonlyContext):
    logging.info("Checking state")
    state = context.state
    logging.info(f"State content: {state}")
    if ('session_id' in state and
        'session_active' in state and
        state['session_active'] and
        'agent' in state):
      logging.info(f"Active agent present: {state['agent']}")
      return {"active_agent": f'{state["agent"]}'}
    logging.info("No active agent")
    return {"active_agent": "None"}

  def before_model_callback(self, callback_context: CallbackContext, llm_request):
    logging.info("before_model_callback called")
    state = callback_context.state
    logging.info(f"Current state: {state}")
    if 'session_active' not in state or not state['session_active']:
      if 'session_id' not in state:
        state['session_id'] = str(uuid.uuid4())
        logging.info(f"Generated new session ID: {state['session_id']}")
      state['session_active'] = True
      logging.info("Session set to active state")
    
    # Log message content for debugging
    if hasattr(llm_request, 'messages') and llm_request.messages:
      for msg in llm_request.messages:
        if hasattr(msg, 'parts') and msg.parts:
          logging.info(f"Message role: {msg.role}, content: {[p.text if hasattr(p, 'text') else 'non-text content' for p in msg.parts if hasattr(p, 'text')]}")
    logging.info("before_model_callback completed")

  def list_remote_agents(self):
    """List the available remote agents you can use to delegate the task."""
    logging.info("Listing remote agents")
    if not self.remote_agent_connections:
      logging.info("No remote agents available")
      return []

    remote_agent_info = []
    for card in self.cards.values():
      remote_agent_info.append(
          {"name": card.name, "description": card.description}
      )
    logging.info(f"Found {len(remote_agent_info)} remote agents")
    return remote_agent_info

  async def send_task(
      self,
      agent_name: str,
      message: str,
      tool_context: ToolContext):
    """Sends a task either streaming (if supported) or non-streaming.

    This will send a message to the remote agent named agent_name.

    Args:
      agent_name: The name of the agent to send the task to.
      message: The message to send to the agent for the task.
      tool_context: The tool context this method runs in.

    Yields:
      A dictionary of JSON data.
    """
    logging.info(f"send_task called, agent name: {agent_name}, message: {message[:50]}...")
    if agent_name not in self.remote_agent_connections:
      logging.error(f"Agent {agent_name} not found, available agents: {list(self.remote_agent_connections.keys())}")
      raise ValueError(f"Agent {agent_name} not found")
    state = tool_context.state
    state['agent'] = agent_name
    logging.info(f"Setting state['agent'] = {agent_name}")
    card = self.cards[agent_name]
    client = self.remote_agent_connections[agent_name]
    if not client:
      logging.error(f"Client for {agent_name} is not available")
      raise ValueError(f"Client not available for {agent_name}")
    if 'task_id' in state:
      taskId = state['task_id']
      logging.info(f"Using existing task ID: {taskId}")
    else:
      taskId = str(uuid.uuid4())
      logging.info(f"Generated new task ID: {taskId}")
    sessionId = state['session_id']
    logging.info(f"Session ID: {sessionId}")
    task: Task
    messageId = ""
    metadata = {}
    if 'input_message_metadata' in state:
      metadata.update(**state['input_message_metadata'])
      logging.info(f"Updated metadata from state: {metadata}")
      if 'message_id' in state['input_message_metadata']:
        messageId = state['input_message_metadata']['message_id']
        logging.info(f"Got message ID from metadata: {messageId}")
    if not messageId:
      messageId = str(uuid.uuid4())
      logging.info(f"Generated new message ID: {messageId}")
    metadata.update(**{'conversation_id': sessionId, 'message_id': messageId})
    logging.info(f"Final metadata: {metadata}")
    request: TaskSendParams = TaskSendParams(
        id=taskId,
        sessionId=sessionId,
        message=Message(
            role="user",
            parts=[TextPart(text=message)],
            metadata=metadata,
        ),
        acceptedOutputModes=["text", "text/plain", "image/png"],
        # pushNotification=None,
        metadata={'conversation_id': sessionId},
    )
    logging.info(f"Preparing to send task request: {taskId}")
    try:
      task = await client.send_task(request, self.task_callback)
      logging.info(f"Task sent successfully: {task.id}, status: {task.status.state}")
    except Exception as e:
      import traceback
      logging.error(f"Error sending task: {str(e)}")
      logging.error(traceback.format_exc())
      raise e
    # Assume completion unless a state returns that isn't complete
    state['session_active'] = task.status.state not in [
        TaskState.COMPLETED,
        TaskState.CANCELED,
        TaskState.FAILED,
        TaskState.UNKNOWN,
    ]
    logging.info(f"Setting session active state: {state['session_active']}")
    if task.status.state == TaskState.INPUT_REQUIRED:
      # Force user input back
      logging.info("Task requires user input")
      tool_context.actions.skip_summarization = True
      tool_context.actions.escalate = True
    elif task.status.state == TaskState.CANCELED:
      # Open question, should we return some info for cancellation instead
      logging.error(f"Task cancelled: {task.id}")
      raise ValueError(f"Agent {agent_name} task {task.id} is cancelled")
    elif task.status.state == TaskState.FAILED:
      # Raise error for failure
      logging.error(f"Task failed: {task.id}")
      raise ValueError(f"Agent {agent_name} task {task.id} failed")
    response = []
    if task.status.message:
      # Assume the information is in the task message.
      logging.info("Getting response from task message")
      response.extend(convert_parts(task.status.message.parts, tool_context))
    if task.artifacts:
      logging.info(f"Task has {len(task.artifacts)} artifacts")
      for artifact in task.artifacts:
        response.extend(convert_parts(artifact.parts, tool_context))
    logging.info(f"Task completed, returning response: {len(response)} items")
    return response

def convert_parts(parts: list[Part], tool_context: ToolContext):
  rval = []
  for p in parts:
    rval.append(convert_part(p, tool_context))
  return rval

def convert_part(part: Part, tool_context: ToolContext):
  if part.type == "text":
    return part.text
  elif part.type == "data":
    return part.data
  elif part.type == "file":
    # Repackage A2A FilePart to google.genai Blob
    # Currently not considering plain text as files    
    file_id = part.file.name
    file_bytes = base64.b64decode(part.file.bytes)    
    file_part = types.Part(
      inline_data=types.Blob(
        mime_type=part.file.mimeType,
        data=file_bytes))
    tool_context.save_artifact(file_id, file_part)
    tool_context.actions.skip_summarization = True
    tool_context.actions.escalate = True
    return DataPart(data = {"artifact-file-id": file_id})
  return f"Unknown type: {p.type}"


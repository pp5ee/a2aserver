import requests
from common.types import AgentCard
import logging

logger = logging.getLogger(__name__)

def get_agent_card(remote_agent_address: str) -> AgentCard:
  """
  Get the agent card from a remote agent address.
  
  Args:
      remote_agent_address: 远程代理地址，可以是基本URL或完整URL
      
  Returns:
      AgentCard: 代理卡片对象
  """
  # 检查URL是否已包含.well-known/agent.json
  if not remote_agent_address.endswith("/.well-known/agent.json"):
    # 确保地址以/结尾，然后拼接.well-known/agent.json
    if not remote_agent_address.endswith("/"):
      remote_agent_address += "/"
    remote_agent_address += ".well-known/agent.json"
  
 
  
  # 确保使用http://开头的URL
  if not (remote_agent_address.startswith("http://") or remote_agent_address.startswith("https://")):
    remote_agent_address = "http://" + remote_agent_address
  
  try:
    agent_card = requests.get(remote_agent_address, timeout=1)
    agent_card.raise_for_status()  # 确保请求成功
    return AgentCard(**agent_card.json())
  except requests.exceptions.RequestException as e:
 
    raise

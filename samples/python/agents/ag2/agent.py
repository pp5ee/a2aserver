import logging
import os
import traceback
import json
from dotenv import load_dotenv
from typing import AsyncIterable, Any, Literal
from pydantic import BaseModel
import yaml

from autogen import AssistantAgent, LLMConfig
from autogen.mcp import create_toolkit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

class ResponseModel(BaseModel):
    """Response model for the YouTube MCP agent."""
    text_reply: str
    closed_captions: str | None
    status: Literal["TERMINATE", ""]
    
    def format(self) -> str:
        """Format the response as a string."""
        if self.closed_captions is None:
            return self.text_reply
        else:
            return f"{self.text_reply}\n\nClosed Captions:\n{self.closed_captions}"


def load_config() -> dict:
    """从配置文件加载API配置"""
    load_dotenv()
    
    # 首先尝试读取环境变量
    config = {
        "base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        "model": os.getenv("LLM_MODEL", "openai/gpt-4o")
    }
    
    # 尝试从配置文件读取（如果存在）
    config_paths = [
        "./config.yaml",
        "./config.yml", 
        "./agent_config.yaml",
        "./agent_config.yml",
        os.path.join(os.path.dirname(__file__), "config.yaml"),
        os.path.join(os.path.dirname(__file__), "config.yml")
    ]
    
    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    yaml_config = yaml.safe_load(f)
                    if yaml_config and isinstance(yaml_config, dict):
                        # 更新配置，保留YAML中的值
                        if "llm" in yaml_config:
                            llm_config = yaml_config["llm"]
                            if "base_url" in llm_config:
                                config["base_url"] = llm_config["base_url"]
                            if "api_key" in llm_config:
                                config["api_key"] = llm_config["api_key"]
                            if "model" in llm_config:
                                config["model"] = llm_config["model"]
                        # 支持顶层配置
                        else:
                            if "base_url" in yaml_config:
                                config["base_url"] = yaml_config["base_url"]
                            if "api_key" in yaml_config:
                                config["api_key"] = yaml_config["api_key"]
                            if "model" in yaml_config:
                                config["model"] = yaml_config["model"]
                        
                        logger.info(f"已从配置文件 {config_path} 加载配置")
                        break
            except Exception as e:
                logger.warning(f"读取配置文件 {config_path} 出错: {e}")
    
    # 确保api_key不为空
    if not config["api_key"]:
        logger.warning("未找到API密钥，请在环境变量或配置文件中设置LLM_API_KEY或OPENAI_API_KEY")
    
    # 记录使用的配置（不包含密钥）
    safe_config = config.copy()
    if "api_key" in safe_config:
        api_key = safe_config["api_key"]
        if api_key and len(api_key) > 10:
            safe_config["api_key"] = f"{api_key[:5]}...{api_key[-5:]}"
        else:
            safe_config["api_key"] = "[未设置]"
    
    logger.info(f"使用LLM配置: {safe_config}")
    return config


class YoutubeMCPAgent:
    """Agent to access a Youtube MCP Server to download closed captions"""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        # Import AG2 dependencies here to isolate requirements
        try:
            # 加载配置
            config = load_config()
            
            # Set up LLM configuration with response format
            llm_config = LLMConfig(
                config_list=[{
                    "model": config["model"],
                    "base_url": config["base_url"],
                    "api_key": config["api_key"]
                }],
                response_format=ResponseModel
            )

            # Create the assistant agent that will use MCP tools
            self.agent = AssistantAgent(
                name="YoutubeMCPAgent",
                llm_config=llm_config,
                system_message=(
                    "You are a specialized assistant for processing YouTube videos. "
                    "You can use MCP tools to fetch captions and process YouTube content. "
                    "You can provide captions, summarize videos, or analyze content from YouTube. "
                    "If the user asks about anything not related to YouTube videos or doesn't provide a YouTube URL, "
                    "politely state that you can only help with tasks related to YouTube videos.\n\n"
                    "IMPORTANT: Always respond using the ResponseModel format with these fields:\n"
                    "- text_reply: Your main response text\n"
                    "- closed_captions: YouTube captions if available, null if not relevant\n"
                    "- status: Always use 'TERMINATE' for all responses \n\n"
                    "Example response:\n"
                    "{\n"
                    "  \"text_reply\": \"Here's the information you requested...\",\n"
                    "  \"closed_captions\": null,\n"
                    "  \"status\": \"TERMINATE\"\n"
                    "}"
                ),
            )

            self.initialized = True
            logger.info("MCP Agent initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import AG2 components: {e}")
            self.initialized = False
        except Exception as e:
            logger.error(f"初始化MCP Agent时出错: {e}")
            traceback.print_exc()
            self.initialized = False

    def get_agent_response(self, response: str) -> dict[str, Any]:
        """Format agent response in a consistent structure."""
        try:
            # Try to parse the response as a ResponseModel JSON
            response_dict = json.loads(response)
            model = ResponseModel(**response_dict)
            
            # All final responses should be treated as complete
            return {
                "is_task_complete": True,
                "require_user_input": False,
                "content": model.format()
            }
        except Exception as e:
            # Log but continue with best-effort fallback
            logger.error(f"Error parsing response: {e}, response: {response}")
            
            # Default to treating it as a completed response
            return {
                "is_task_complete": True, 
                "require_user_input": False,
                "content": response
            }

    async def stream(self, query: str, sessionId: str) -> AsyncIterable[dict[str, Any]]:
        """Stream updates from the MCP agent."""
        if not self.initialized:
            yield {
                "is_task_complete": False,
                "require_user_input": True,
                "content": "Agent initialization failed. Please check the dependencies and logs."
            }
            return

        try:
            # Initial response to acknowledge the query
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "content": "Processing request..."
            }

            logger.info(f"Processing query: {query[:50]}...")

            try:                
                # Create stdio server parameters for mcp-youtube
                server_params = StdioServerParameters(
                    command="mcp-youtube",
                )

                # Connect to the MCP server using stdio client
                async with stdio_client(server_params) as (read, write), ClientSession(read, write) as session:
                    # Initialize the connection
                    await session.initialize()

                    # Create toolkit and register tools
                    toolkit = await create_toolkit(session=session)
                    toolkit.register_for_llm(self.agent)

                    result = await self.agent.a_run(
                        message=query,
                        tools=toolkit.tools,
                        max_turns=2,  # Fixed at 2 turns to allow tool usage
                        user_input=False,
                    )

                    # Extract the content from the result
                    try:
                        # Process the result
                        await result.process()
                        
                        # Get the summary which contains the output
                        response = await result.summary

                    except Exception as extraction_error:
                        logger.error(f"Error extracting response: {extraction_error}")
                        traceback.print_exc()
                        response = f"Error processing request: {str(extraction_error)}"

                    # Final response
                    yield self.get_agent_response(response)
                    
            except Exception as e:
                logger.error(f"Error during processing: {traceback.format_exc()}")
                yield {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": f"Error processing request: {str(e)}"
                }
        except Exception as e:
            logger.error(f"Error in streaming agent: {traceback.format_exc()}")
            yield {
                "is_task_complete": False,
                "require_user_input": True,
                "content": f"Error processing request: {str(e)}"
            }

    def invoke(self, query: str, sessionId: str) -> dict[str, Any]:
        """Synchronous invocation of the MCP agent."""
        raise NotImplementedError(
            "Synchronous invocation is not supported by this agent. Use the streaming endpoint (tasks/sendSubscribe) instead."
        )

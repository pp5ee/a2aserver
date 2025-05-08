"""A UI solution and host service to interact with the agent framework.
run:
  uv main.py
"""
import asyncio
import os
import threading
import logging
import json
import time
from typing import Optional

import mesop as me

from state.state import AppState
from components.page_scaffold import page_scaffold
from components.api_key_dialog import api_key_dialog
from pages.home import home_page_content
from pages.agent_list import agent_list_page
from pages.conversation import conversation_page
from pages.event_list import event_list_page
from pages.settings import settings_page_content
from pages.task_list import task_list_page
from state import host_agent_service
from service.server.server import ConversationServer
# 导入API文档设置
from api_docs import setup_swagger_docs

# 导入Solana验证器
try:
    from utils.solana_verifier import solana_verifier, sdk_available
    if sdk_available:
        logging.info("成功加载Solana验证器，SDK可用")
    else:
        logging.error("Solana验证器已加载但SDK不可用，所有签名验证将失败")
    SOLANA_VERIFIER_AVAILABLE = True
except ImportError as e:
    SOLANA_VERIFIER_AVAILABLE = False
    logging.error(f"无法导入Solana验证器: {str(e)}，所有签名验证将失败")
    
    # 不再创建模拟验证器，确保当SDK不可用时签名验证必须失败

from fastapi import FastAPI, APIRouter, Request, Response, HTTPException
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi.responses import JSONResponse

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def on_load(e: me.LoadEvent):  # pylint: disable=unused-argument
    """On load event"""
    state = me.state(AppState)
    me.set_theme_mode(state.theme_mode)
    if "conversation_id" in me.query_params:
      state.current_conversation_id = me.query_params["conversation_id"]
    else:
      state.current_conversation_id = ""
    
    # 获取环境变量中的API key信息，但不再显示API key对话框
    uses_vertex_ai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
    api_key = os.getenv("GOOGLE_API_KEY", "")
    
    if uses_vertex_ai:
        state.uses_vertex_ai = True
    elif api_key:
        state.api_key = api_key
    
    # 不再显示API key对话框
    state.api_key_dialog_open = False

# Policy to allow the lit custom element to load
security_policy=me.SecurityPolicy(
    allowed_script_srcs=[
      'https://cdn.jsdelivr.net',
    ]
  )


@me.page(
    path="/",
    title="Chat",
    on_load=on_load,
    security_policy=security_policy,
)
def home_page():
    """Main Page"""
    state = me.state(AppState)
    # 不再显示API key对话框
    with page_scaffold():  # pylint: disable=not-context-manager
        home_page_content(state)


@me.page(
    path="/agents",
    title="Agents",
    on_load=on_load,
    security_policy=security_policy,
)
def another_page():
    """Another Page"""
    agent_list_page(me.state(AppState))


@me.page(
    path="/conversation",
    title="Conversation",
    on_load=on_load,
    security_policy=security_policy,
)
def chat_page():
    """Conversation Page."""
    conversation_page(me.state(AppState))

@me.page(
    path="/event_list",
    title="Event List",
    on_load=on_load,
    security_policy=security_policy,
)
def event_page():
    """Event List Page."""
    event_list_page(me.state(AppState))


@me.page(
    path="/settings",
    title="Settings",
    on_load=on_load,
    security_policy=security_policy,
)
def settings_page():
    """Settings Page."""
    settings_page_content()


@me.page(
    path="/task_list",
    title="Task List",
    on_load=on_load,
    security_policy=security_policy,
)
def task_page():
    """Task List Page."""
    task_list_page(me.state(AppState))

# Setup the server global objects
app = FastAPI()
router = APIRouter()
agent_server = ConversationServer(router)
app.include_router(router)

# 设置API文档（Swagger UI和ReDoc）
try:
    # 加载pyyaml库
    import yaml
    setup_swagger_docs(app)
    logger.info("API documentation configured, can be accessed at /api/docs or /api/redoc")
except ImportError:
    logger.warning("pyyaml library not installed, cannot load API documentation. install: pip install pyyaml")
except Exception as e:
    logger.warning(f"API文档配置失败: {str(e)}")



# add middleware to verify signature and record request header information
@app.middleware("http")
async def verify_signature_middleware(request: Request, call_next):
    """verify signature in header and ensure user exists in database"""
    # define api paths that need signature verification
    api_paths = [
        "/conversation/create",
        "/message/send",
        "/agent/register",
        "/conversation/list",
        "/message/list",
        "/task/list",
        "/agent/list",
        "/events/get"
    ]
    
    # 检查请求路径是否需要验证
    path = request.url.path
    needs_verification = any(api_path in path for api_path in api_paths)
    
    if needs_verification:
        # get verification information from header
        public_key = request.headers.get("X-Solana-PublicKey")
        nonce = request.headers.get("X-Solana-Nonce")
        signature = request.headers.get("X-Solana-Signature")
        
        # 验证签名
        if not public_key:
            logger.warning(f"public key in header is required: {path}")
            return Response(
                content=json.dumps({"error": "public key in header is required"}),
                status_code=401,
                media_type="application/json"
            )
        
        # if nonce or signature is not provided, return error
        if not nonce or not signature:
            logger.warning(f"signature in header is required: path={path}, public_key={public_key[:10]}...")
            return Response(
                content=json.dumps({"error": "signature in header is required"}),
                status_code=401,
                media_type="application/json"
            )
        
        # 检查验证器是否可用
        if not SOLANA_VERIFIER_AVAILABLE:
            logger.error(f"server signature verification component is not available, please contact the administrator")
            return Response(
                content=json.dumps({"error": "server signature verification component is not available, please contact the administrator"}),
                status_code=500,
                media_type="application/json"
            )
        
        # 验证签名
        if not solana_verifier.verify_signature(public_key, nonce, signature):
            # 根据验证失败的原因返回不同的错误信息
            try:
                nonce_timestamp = int(nonce)
                current_time = int(time.time() * 1000)
                
                if current_time > nonce_timestamp:
                    # signature expired
                    return Response(
                        content=json.dumps({"error": "signature expired, please sign again"}),
                        status_code=401,
                        media_type="application/json"
                    )
            except ValueError:
                pass
                
            # invalid signature
            return Response(
                content=json.dumps({"error": "invalid signature, please sign again"}),
                status_code=401,
                media_type="application/json"
            )
        
        # record successful verification
        if path in ["/message/send", "/agent/register", "/conversation/create"]:
            logger.info(f"signature verification successful: path={path}, public_key={public_key[:10]}...")
        
        # ensure user exists in database
        try:
            from service.server.user_session_manager import UserSessionManager
            UserSessionManager.get_instance()._ensure_user_exists(public_key)
        except Exception as e:
            logger.error(f"error adding user to database: {str(e)}")
    
    response = await call_next(request)
    return response

# add global error handling middleware
@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    """global exception handling"""
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"error occurred while processing the request: {str(e)}")
        # return JSON format error response
        return Response(
            content=json.dumps({"error": 'internal server error'}),
            status_code=500,
            media_type="application/json"
        )

# 定义一个简单的健康检查端点
@app.get("/health")
async def health_check():
    """health check endpoint"""
    return {"status": "ok", "multi_user": True, "memory_mode": True}

# 添加JSONP支持的中间件
@app.middleware("http")
async def jsonp_middleware(request: Request, call_next):
    """jsonp middleware"""
    callback = request.query_params.get("callback")
    response = await call_next(request)
    
    if callback and response.headers.get("content-type") == "application/json":
        # 获取原始内容
        content = await response.body()
        # 包装为JSONP格式
        jsonp_content = f"{callback}({content.decode('utf-8')})".encode()
        # 创建新的响应
        return Response(
            content=jsonp_content,
            status_code=response.status_code,
            media_type="application/javascript"
        )
    
    return response

@app.get("/api/metadata-proxy/{path:path}")
async def metadata_proxy(path: str, request: Request):
    """
    proxy metadata request, solve CORS problem
    """
    import httpx
    
    # 获取完整的URL路径，包括查询参数
    full_path = request.url.path.replace("/api/metadata-proxy/", "")
    query_string = request.url.query.decode()
    if query_string:
        full_path = f"{full_path}?{query_string}"
    
    # 构建目标URL
    target_url = f"http://8.214.38.69:10003/{full_path}"
    
    try:
        logger.info(f"proxy request: {target_url}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(target_url)
            
            # 获取内容类型
            content_type = response.headers.get("content-type", "application/json")
            
            # 返回响应
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers={"content-type": content_type}
            )
    except Exception as e:
        logger.error(f"proxy request failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"proxy request failed: {str(e)}"}
        )

@app.get("/api/agent/status")
async def get_agent_status(request: Request, wallet_address: Optional[str] = None):
    """
    get agent status information
    
    Args:
        wallet_address: optional, specify the wallet address. if not provided, get all agent status
        
    Returns:
        agent status information list
    """
    # 获取代理状态
    from service.server.user_session_manager import UserSessionManager
    user_session_manager = UserSessionManager.get_instance()
    agent_status = user_session_manager.get_agent_status(wallet_address)
    
    return {
        "success": True,
        "data": agent_status
    }

app.mount(
    "/",
    WSGIMiddleware(
        me.create_wsgi_app(debug_mode=os.environ.get("DEBUG_MODE", "") == "true")
    ),
)
# add CORS middleware to support cross-domain requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all sources, should be limited in production environment
    allow_credentials=False,
    allow_methods=["*"],  # allow all methods
    allow_headers=["*"],  # allow all request headers
    expose_headers=["*"]  # allow expose all response headers
)

if __name__ == "__main__":    

    import uvicorn
    # Setup the connection details, these should be set in the environment
    host = os.environ.get("A2A_UI_HOST", "0.0.0.0")
    port = int(os.environ.get("A2A_UI_PORT", "12000"))

    # Set the client to talk to the server
    host_agent_service.server_url = f"http://{host}:{port}"

    logger.info(f"server started at {host}:{port}, multi-user support enabled")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        reload_includes=["*.py", "*.js"],
        timeout_graceful_shutdown=0,
    )

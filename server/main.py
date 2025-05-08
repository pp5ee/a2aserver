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
    logger.info("API文档已配置，可访问 /api/docs 或 /api/redoc")
except ImportError:
    logger.warning("未安装pyyaml库，无法加载API文档。安装: pip install pyyaml")
except Exception as e:
    logger.warning(f"API文档配置失败: {str(e)}")

# 添加CORS中间件以支持跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制
    allow_credentials=False,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
    expose_headers=["*"]  # 允许暴露所有响应头
)

# 添加中间件验证签名并记录请求头信息
@app.middleware("http")
async def verify_signature_middleware(request: Request, call_next):
    """验证请求头中的签名信息并确保用户存在于数据库中"""
    # 定义需要验证签名的API路径
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
        # 获取请求头中的验证信息
        public_key = request.headers.get("X-Solana-PublicKey")
        nonce = request.headers.get("X-Solana-Nonce")
        signature = request.headers.get("X-Solana-Signature")
        
        # 验证签名
        if not public_key:
            logger.warning(f"请求缺少钱包地址: {path}")
            return Response(
                content=json.dumps({"error": "请求未包含钱包地址，请连接钱包"}),
                status_code=401,
                media_type="application/json"
            )
        
        # 如果没有nonce或signature，返回错误
        if not nonce or not signature:
            logger.warning(f"请求缺少签名信息: path={path}, public_key={public_key[:10]}...")
            return Response(
                content=json.dumps({"error": "请求需要钱包签名，请重新签名"}),
                status_code=401,
                media_type="application/json"
            )
        
        # 检查验证器是否可用
        if not SOLANA_VERIFIER_AVAILABLE:
            logger.error(f"签名验证失败: Solana验证器不可用")
            return Response(
                content=json.dumps({"error": "服务器签名验证组件不可用，请联系管理员"}),
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
                    # 签名已过期
                    return Response(
                        content=json.dumps({"error": "签名已过期，请重新签名"}),
                        status_code=401,
                        media_type="application/json"
                    )
            except ValueError:
                pass
                
            # 签名无效
            return Response(
                content=json.dumps({"error": "签名无效，请重新签名"}),
                status_code=401,
                media_type="application/json"
            )
        
        # 记录验证成功
        if path in ["/message/send", "/agent/register", "/conversation/create"]:
            logger.info(f"签名验证成功: path={path}, public_key={public_key[:10]}...")
        
        # 确保用户在数据库中存在
        try:
            from service.server.user_session_manager import UserSessionManager
            UserSessionManager.get_instance()._ensure_user_exists(public_key)
        except Exception as e:
            logger.error(f"将用户添加到数据库时出错: {str(e)}")
    
    response = await call_next(request)
    return response

# 添加全局错误处理中间件
@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    """全局异常处理"""
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}")
        # 返回JSON格式的错误响应
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json"
        )

# 定义一个简单的健康检查端点
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "multi_user": True, "memory_mode": True}

# 添加JSONP支持的中间件
@app.middleware("http")
async def jsonp_middleware(request: Request, call_next):
    """处理JSONP请求"""
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
    代理元数据请求，解决CORS问题
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
        logger.info(f"代理请求: {target_url}")
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
        logger.error(f"代理请求失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"代理请求失败: {str(e)}"}
        )

@app.get("/api/agent/status")
async def get_agent_status(request: Request, wallet_address: Optional[str] = None):
    """
    获取代理状态信息
    
    Args:
        wallet_address: 可选，指定钱包地址。如果不提供，则获取所有代理状态
        
    Returns:
        代理状态信息列表
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

if __name__ == "__main__":    

    import uvicorn
    # Setup the connection details, these should be set in the environment
    host = os.environ.get("A2A_UI_HOST", "0.0.0.0")
    port = int(os.environ.get("A2A_UI_PORT", "12000"))

    # Set the client to talk to the server
    host_agent_service.server_url = f"http://{host}:{port}"

    logger.info(f"启动A2A服务器在 {host}:{port}，已启用多用户支持")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        reload_includes=["*.py", "*.js"],
        timeout_graceful_shutdown=0,
    )

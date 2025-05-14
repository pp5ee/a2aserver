"""A UI solution and host service to interact with the agent framework.
run:
  uv main.py
  SSL_CERT_DIR=/etc/ssl/certs uv run main.py
  SSL_CERT_FILE=$(python3 -m certifi) uv run main.py
"""
import asyncio
import os
import threading
import logging
import json
import time
from typing import Optional
import re
from collections import defaultdict
from datetime import datetime, timedelta
import concurrent.futures
import psutil
import gc

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

# 全局线程池，用于异步任务执行
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=50, thread_name_prefix="a2a_worker")

# 添加性能监控
def monitor_system_resources():
    """定期监控系统资源使用情况"""
    try:
        # 获取当前进程
        process = psutil.Process(os.getpid())
        
        # 记录内存使用情况
        memory_info = process.memory_info()
        logger.info(f"内存使用: RSS={memory_info.rss/1024/1024:.2f}MB, VMS={memory_info.vms/1024/1024:.2f}MB")
        
        # 记录线程数量
        thread_count = len(process.threads())
        logger.info(f"线程数量: {thread_count}")
        
        # 记录CPU使用率
        cpu_percent = process.cpu_percent(interval=1.0)
        logger.info(f"CPU使用率: {cpu_percent}%")
        
        # 记录打开的文件数
        try:
            open_files = len(process.open_files())
            logger.info(f"打开的文件数: {open_files}")
        except:
            pass
        
        # 计算活跃线程池数量
        active_threads = len([t for t in threading.enumerate() if t.is_alive()])
        logger.info(f"活跃线程: {active_threads}/{threading.active_count()}")
        
        # 手动触发垃圾收集
        collected = gc.collect()
        logger.info(f"垃圾收集: 回收了 {collected} 个对象")
    except Exception as e:
        logger.error(f"监控系统资源时出错: {e}")

# 启动监控线程
def start_monitoring():
    """启动一个后台线程定期监控系统资源"""
    def monitoring_task():
        while True:
            try:
                monitor_system_resources()
                time.sleep(300)  # 每5分钟监控一次
            except Exception as e:
                logger.error(f"系统监控线程出错: {e}")
                time.sleep(60)  # 出错后等待1分钟再次尝试
    
    # 启动监控线程
    monitor_thread = threading.Thread(target=monitoring_task, daemon=True)
    monitor_thread.start()
    logger.info("系统资源监控线程已启动")

# 添加速率限制的类
class RateLimiter:
    def __init__(self, max_requests=200, time_window=60):
        """
        初始化速率限制器
        
        Args:
            max_requests: 在时间窗口内允许的最大请求数
            time_window: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.time_window = time_window
        # 存储每个IP的请求历史，使用字典的形式
        # 键是IP地址，值是一个列表，包含该IP地址的请求时间戳
        self.request_history = defaultdict(list)
        
        # 定期清理过期的请求历史
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动一个线程定期清理过期的请求历史"""
        thread = threading.Thread(target=self._cleanup_expired_records, daemon=True)
        thread.start()
    
    def _cleanup_expired_records(self):
        """定期清理过期的请求历史"""
        while True:
            try:
                now = datetime.now()
                # 遍历所有IP地址
                for ip in list(self.request_history.keys()):
                    # 计算过期时间点
                    cutoff_time = now - timedelta(seconds=self.time_window)
                    
                    # 过滤掉过期的请求记录
                    self.request_history[ip] = [
                        ts for ts in self.request_history[ip] 
                        if ts > cutoff_time
                    ]
                    
                    # 如果该IP没有请求记录了，删除该IP的键
                    if not self.request_history[ip]:
                        del self.request_history[ip]
            except Exception as e:
                logger.error(f"清理请求历史时出错: {e}")
            
            # 每10秒清理一次
            time.sleep(10)
    
    def is_allowed(self, ip: str) -> bool:
        """
        检查给定的IP是否被允许发送请求
        
        Args:
            ip: 客户端IP地址
            
        Returns:
            bool: 如果允许请求则返回True，否则返回False
        """
        now = datetime.now()
        
        # 添加当前请求到历史记录
        self.request_history[ip].append(now)
        
        # 计算过期时间点
        cutoff_time = now - timedelta(seconds=self.time_window)
        
        # 过滤非过期的请求记录
        recent_requests = [ts for ts in self.request_history[ip] if ts > cutoff_time]
        
        # 更新请求历史
        self.request_history[ip] = recent_requests
        
        # 检查请求次数是否超过限制
        return len(recent_requests) <= self.max_requests

    def get_remaining_requests(self, ip: str) -> int:
        """
        获取给定IP在当前时间窗口内还可以发送的请求数
        
        Args:
            ip: 客户端IP地址
            
        Returns:
            int: 剩余可用请求数
        """
        now = datetime.now()
        cutoff_time = now - timedelta(seconds=self.time_window)
        
        # 过滤非过期的请求记录
        recent_requests = [ts for ts in self.request_history[ip] if ts > cutoff_time]
        
        # 计算剩余请求数
        remaining = max(0, self.max_requests - len(recent_requests))
        return remaining
    
    def get_reset_time(self, ip: str) -> Optional[datetime]:
        """
        获取给定IP的速率限制何时重置
        
        Args:
            ip: 客户端IP地址
            
        Returns:
            Optional[datetime]: 重置时间，如果没有请求历史则返回None
        """
        if ip not in self.request_history or not self.request_history[ip]:
            return None
        
        # 获取最早的请求时间
        earliest_request = min(self.request_history[ip])
        
        # 计算重置时间
        reset_time = earliest_request + timedelta(seconds=self.time_window)
        return reset_time

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

# 创建全局的速率限制器实例，限制每个IP每分钟200次请求
rate_limiter = RateLimiter(max_requests=200, time_window=60)

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

# 添加速率限制中间件
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """限制请求速率的中间件，防止DoS攻击"""
    # 获取客户端IP
    client_ip = request.client.host if request.client else "unknown"
    
    # 白名单IP，跳过限制（可选）
    whitelist_ips = ["127.0.0.1", "::1"]  # localhost
    if client_ip in whitelist_ips:
        return await call_next(request)
    
    # 检查请求是否被允许
    if rate_limiter.is_allowed(client_ip):
        # 如果允许，处理请求
        response = await call_next(request)
        
        # 添加速率限制相关的头信息
        remaining = rate_limiter.get_remaining_requests(client_ip)
        reset_time = rate_limiter.get_reset_time(client_ip)
        
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        if reset_time:
            # 将重置时间转换为Unix时间戳
            reset_timestamp = int(reset_time.timestamp())
            response.headers["X-RateLimit-Reset"] = str(reset_timestamp)
        
        return response
    else:
        # 如果请求超过限制，返回429错误
        reset_time = rate_limiter.get_reset_time(client_ip)
        reset_seconds = int((reset_time - datetime.now()).total_seconds()) if reset_time else 60
        
        # 记录日志
        logger.warning(f"IP {client_ip} 超过速率限制，在 {reset_seconds} 秒后重置")
        
        # 构建响应
        error_response = {
            "error": "Too Many Requests",
            "message": f"请求频率超过限制。请在 {reset_seconds} 秒后重试。",
            "status": 429
        }
        
        response = Response(
            content=json.dumps(error_response),
            status_code=429,
            media_type="application/json"
        )
        
        # 添加标准的速率限制响应头
        response.headers["Retry-After"] = str(reset_seconds)
        
        return response

# 添加安全中间件，防止敏感文件访问
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """拦截对敏感路径的访问尝试"""
    path = request.url.path.lower()
    
    # 检查是否是敏感路径或可能的探测攻击
    sensitive_patterns = [
        "/.git/", "/.env", "/.config", "/admin", 
        "/.htaccess", "/.htpasswd", "/.svn", "/.DS_Store",
        "/wp-admin", "/wp-login", "/wp-includes",  # WordPress相关路径
        "/shell", "/phpinfo", "/phpmyadmin",  # 常见探测目标
        "/solr", "/jenkins", "/manager/html",  # 其他常见应用探测
    ]
    
    random_api_pattern = re.compile(r'^/[a-zA-Z0-9]{10,}/api/')
    
    # 检查敏感路径
    for pattern in sensitive_patterns:
        if pattern in path:
            logger.warning(f"检测到对敏感路径的访问尝试: {path}")
            return Response(
                content=json.dumps({"error": "Not Found"}),
                status_code=404,
                media_type="application/json"
            )
    
    # 检查随机格式的API探测请求
    if random_api_pattern.match(path):
        logger.warning(f"检测到可疑的API路径探测: {path}")
        return Response(
            content=json.dumps({"error": "Not Found"}),
            status_code=404,
            media_type="application/json"
        )
    
    # 继续处理正常请求
    return await call_next(request)

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

# 添加健康和资源监控中间件，位于全局异常处理middleware之后

# 添加资源监控中间件
@app.middleware("http")
async def resource_monitoring_middleware(request: Request, call_next):
    """监控每个请求的资源使用情况"""
    # 记录请求开始时间
    start_time = time.time()
    
    # 记录开始时的资源状态
    process = psutil.Process(os.getpid())
    start_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # 处理请求
    response = await call_next(request)
    
    # 请求结束，计算资源使用情况
    end_time = time.time()
    end_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # 计算差异
    duration = end_time - start_time
    memory_diff = end_memory - start_memory
    
    # 记录长时间运行的请求或内存消耗大的请求
    if duration > 1.0 or abs(memory_diff) > 5.0:
        path = request.url.path
        logger.info(
            f"资源监控 - 路径: {path}, "
            f"持续时间: {duration:.2f}秒, "
            f"内存变化: {memory_diff:.2f}MB, "
            f"当前内存: {end_memory:.2f}MB"
        )
    
    # 如果请求处理时间超过10秒，记录警告
    if duration > 10.0:
        logger.warning(
            f"请求处理时间过长 - 路径: {request.url.path}, "
            f"处理时间: {duration:.2f}秒"
        )
        
    # 如果内存使用超过预设阈值，触发垃圾回收
    if end_memory > 1000:  # 如果内存使用超过1GB
        logger.warning(f"内存使用过高: {end_memory:.2f}MB，触发垃圾回收")
        gc.collect()
    
    return response

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
# 添加CORS中间件以支持跨域请求 - 必须最先添加
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
    expose_headers=["*"]  # 允许暴露所有响应头
)
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

    # 启动监控线程
    start_monitoring()
    
    logger.info(f"server started at {host}:{port}, multi-user support enabled")
    
    # 使用更优化的Uvicorn配置运行应用，避免异步I/O阻塞
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.environ.get("DEBUG_MODE", "") == "true",
        reload_includes=["*.py", "*.js"] if os.environ.get("DEBUG_MODE", "") == "true" else None,
        workers=int(os.environ.get("UVICORN_WORKERS", "2")),  # 可通过环境变量调整工作进程数
        timeout_keep_alive=120,  # 增加keep-alive超时时间
        timeout_graceful_shutdown=30,  # 设置优雅关闭的超时时间
        loop="uvloop",  # 使用uvloop作为事件循环实现，比asyncio默认循环更高效
        limit_concurrency=1000,  # 限制并发连接数
        backlog=2048,  # 增加挂起连接队列大小
        log_level="info",
        proxy_headers=True,  # 启用代理头处理，确保正确识别客户端IP
        forwarded_allow_ips="*",  # 允许所有IP的转发头
        h11_max_incomplete_event_size=16*1024*1024,  # 增加HTTP解析缓冲区大小
    )

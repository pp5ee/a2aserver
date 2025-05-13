#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import os
import time
import uuid
import math
import psutil
from typing import Dict, List, Optional, Any, AsyncIterable, Literal

from fastapi import FastAPI, Request, HTTPException, Response, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import uvicorn
from fastapi.responses import JSONResponse, StreamingResponse

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Auth Headers Mock Agent")

# 启用CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A2A协议相关模型
class TaskRequest(BaseModel):
    task: str
    sessionId: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    taskId: Optional[str] = None

    # 添加兼容处理，同时支持不同格式的请求
    @classmethod
    def parse_request(cls, request_data: Dict[str, Any]) -> "TaskRequest":
        # 打印原始请求数据用于调试
        logger.info(f"原始请求数据: {json.dumps(request_data, default=str)}")
        
        if "task" in request_data:
            return cls(**request_data)
        elif "params" in request_data and isinstance(request_data["params"], dict):
            params = request_data["params"]
            query = params.get("query", "")
            task_id = params.get("taskId", str(uuid.uuid4()))
            return cls(task=query, sessionId=str(uuid.uuid4()), taskId=task_id)
        else:
            # 默认处理
            return cls(task="", sessionId=str(uuid.uuid4()), taskId=str(uuid.uuid4()))

class TaskResponse(BaseModel):
    is_task_complete: bool = False
    require_user_input: bool = False
    content: str
    error: Optional[str] = None
    id: Optional[str] = None
    taskId: Optional[str] = None
    status: Dict[str, Any] = Field(default_factory=lambda: {"message": ""})

    def to_dict(self) -> Dict[str, Any]:
        result = self.model_dump(exclude_none=True)
        # 确保status字段始终存在且不为None
        if 'status' not in result or result['status'] is None:
            result['status'] = {"message": self.content}
        else:
            # 确保status中包含message字段
            if "message" not in result['status'] or result['status']["message"] is None:
                result['status']["message"] = self.content
        return result

# Agent Card定义
AGENT_CARD = {
    "name": "Mock Remote Agent",
    "description": "An agent that performs math operations and monitors system hardware",
    "url": "http://localhost:10001",
    "version": "1.0.0",
    "defaultInputModes": ["text", "text/plain"],
    "defaultOutputModes": ["text", "text/plain"],
    "capabilities": {
        "streaming": True,  # 更新为支持流式请求
        "pushNotifications": False
    },
    "skills": [
        {
            "id": "math_operations",
            "name": "Math Operations Tool",
            "description": "Performs various mathematical operations",
            "tags": ["math", "calculator"],
            "examples": ["Calculate 2+2", "What is 15*3?"]
        },
        {
            "id": "system_monitor",
            "name": "System Hardware Monitor",
            "description": "Monitors system hardware usage",
            "tags": ["hardware", "monitoring"],
            "examples": ["Get CPU usage", "Check memory usage"]
        }
    ]
}

# 打印所有请求头信息
async def log_headers(request: Request):
    logger.info("------请求头信息------")
    for header_name, header_value in request.headers.items():
        logger.info(f"{header_name}: {header_value}")
    logger.info("---------------------")
    return request.headers

# 验证鉴权头的依赖函数
async def verify_auth_headers(
    request: Request,
    headers: Dict = Depends(log_headers),
    x_solana_publickey: Optional[str] = Header(None, alias="X-Solana-PublicKey"),
    x_solana_nonce: Optional[str] = Header(None, alias="X-Solana-Nonce"),
    x_solana_signature: Optional[str] = Header(None, alias="X-Solana-Signature")
):
    # 简单验证：确保所有必需的头都存在
    if not all([x_solana_publickey, x_solana_nonce, x_solana_signature]):
        logger.warning("鉴权头不完整")
        # 为了演示目的，不强制需要完整鉴权头，仅记录警告
        # 在生产环境中应该抛出以下异常
        # raise HTTPException(status_code=401, detail="缺少必要的鉴权头信息")
    
    # 这里可以添加更复杂的验证逻辑，如签名验证
    # 为了示例目的，我们只记录鉴权信息并继续
    logger.info(f"接收到鉴权头: PublicKey={x_solana_publickey}, Nonce={x_solana_nonce}")
    
    # 返回鉴权信息以便路由处理函数使用
    return {
        "publicKey": x_solana_publickey or "default_key",
        "nonce": x_solana_nonce or "default_nonce",
        "signature": x_solana_signature or "default_signature"
    }

# 提供Agent Card
@app.get("/.well-known/agent.json")
async def get_agent_card():
    return JSONResponse(content=AGENT_CARD)

# 解析数学表达式
def evaluate_math_expression(expression: str) -> str:
    try:
        # 安全地计算简单数学表达式
        # 注意：在真实环境中应使用更安全的方法
        # 此处仅用于演示
        allowed_chars = set("0123456789+-*/() .")
        if not all(c in allowed_chars for c in expression):
            return "错误：表达式包含不允许的字符"
        
        # 使用更安全的eval替代方法
        result = eval(expression, {"__builtins__": {}}, {"math": math})
        return f"计算结果: {expression} = {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"

# 获取系统硬件状态
def get_system_status() -> str:
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        status = (
            f"系统状态:\n"
            f"- CPU使用率: {cpu_percent}%\n"
            f"- 内存使用: {memory.percent}% (已用: {memory.used/1024/1024:.2f} MB, 总计: {memory.total/1024/1024:.2f} MB)\n"
            f"- 磁盘使用: {disk.percent}% (已用: {disk.used/1024/1024/1024:.2f} GB, 总计: {disk.total/1024/1024/1024:.2f} GB)"
        )
        return status
    except Exception as e:
        return f"获取系统状态时出错: {str(e)}"

# 从请求中提取查询文本
def extract_query_from_request(request_data: Dict[str, Any]) -> str:
    """从各种可能的请求格式中提取查询文本"""
    query = ""
    
    # 1. 直接从JSON-RPC方法参数中提取
    if "params" in request_data and isinstance(request_data["params"], dict):
        params = request_data["params"]
        
        # 2. 从query参数直接提取
        if "query" in params and isinstance(params["query"], str):
            query = params["query"]
        
        # 3. 从message对象中提取
        if not query and "message" in params:
            message = params["message"]
            
            # 3.1 直接从message.text提取
            if isinstance(message, dict) and "text" in message:
                query = message["text"]
            
            # 3.2 从message.parts[]数组中提取
            elif isinstance(message, dict) and "parts" in message and isinstance(message["parts"], list):
                for part in message["parts"]:
                    if isinstance(part, dict):
                        # 从text类型部分提取
                        if part.get("type") == "text" and "text" in part:
                            query += part["text"] + " "
                        # 从content字段提取
                        elif "content" in part and isinstance(part["content"], str):
                            query += part["content"] + " "
    
    # 4. 从其他可能的字段中提取
    if not query and "task" in request_data:
        query = request_data["task"]
    
    return query.strip()

# 处理任务请求（非流式）
@app.post("/")
async def handle_task(request: Request, auth_info: dict = Depends(verify_auth_headers)):
    try:
        # 直接从请求体获取原始JSON数据
        request_data = await request.json()
        logger.info(f"原始请求数据: {json.dumps(request_data, default=str)}")
        
        # 处理JSON-RPC格式请求
        params = request_data.get("params", {})
        task_id = params.get("id") or str(uuid.uuid4())
        session_id = params.get("sessionId") or str(uuid.uuid4())
        
        # 提取查询文本
        query = extract_query_from_request(request_data)
        logger.info(f"提取到的查询文本: '{query}'")
        logger.info(f"接收到任务请求: {query}, sessionId: {session_id}, taskId: {task_id}")
        logger.info(f"已验证用户: {auth_info['publicKey']}")
        
        # 处理请求
        query_lower = query.lower() if query else ""
        content = ""
        is_complete = True
        require_input = False
        
        if any(keyword in query_lower for keyword in ["计算", "compute", "math", "运算", "加", "减", "乘", "除"]) or any(c in "0123456789+-*/()." for c in query):
            # 提取数学表达式
            # 简单处理：假设表达式是查询中的数字和运算符
            expression = ''.join(c for c in query if c in "0123456789+-*/() .")
            if not expression:
                content = "请提供有效的数学表达式"
                is_complete = False
                require_input = True
            else:
                content = evaluate_math_expression(expression)
        elif any(keyword in query_lower for keyword in ["系统", "状态", "system", "status", "硬件", "hardware", "内存", "memory", "cpu"]):
            content = get_system_status()
        else:
            content = (
                "我是一个支持两种功能的模拟Agent:\n"
                "1. 数学运算 - 示例: '计算 2 + 2' 或 '5 * 10是多少'\n"
                "2. 系统状态 - 示例: '显示系统状态' 或 '硬件使用情况'"
            )
            is_complete = False
            require_input = True
        
        # 创建响应对象并确保status字段存在
        response = TaskResponse(
            is_task_complete=is_complete,
            require_user_input=require_input,
            content=content,
            id=task_id,
            taskId=task_id,
            status={"message": content}
        )
            
        # 返回字典格式的响应
        return response.to_dict()
    except Exception as e:
        logger.error(f"处理任务时出错: {str(e)}")
        logger.exception("详细错误信息:")
        task_id = str(uuid.uuid4())
        error_msg = f"处理请求时发生错误: {str(e)}"
        response = TaskResponse(
            is_task_complete=False,
            require_user_input=True,
            content=error_msg,
            error=error_msg,
            id=task_id,
            taskId=task_id,
            status={"message": error_msg}
        )
        return response.to_dict()

# 处理流式任务请求
@app.post("/stream")
async def handle_streaming_task(request: Request, auth_info: dict = Depends(verify_auth_headers)):
    try:
        # 直接从请求体获取原始JSON数据
        request_data = await request.json()
        logger.info(f"原始流式请求数据: {json.dumps(request_data, default=str)}")
        
        # 处理JSON-RPC格式请求
        params = request_data.get("params", {})
        task_id = params.get("id") or str(uuid.uuid4())
        session_id = params.get("sessionId") or str(uuid.uuid4())
        
        # 提取查询文本
        query = extract_query_from_request(request_data)
        logger.info(f"提取到的流式查询文本: '{query}'")
        logger.info(f"接收到流式任务请求: {query}, sessionId: {session_id}, taskId: {task_id}")
        logger.info(f"已验证用户: {auth_info['publicKey']}")
        
        # 创建生成响应的异步生成器
        async def generate_response():
            try:
                query_lower = query.lower() if query else ""
                if any(keyword in query_lower for keyword in ["计算", "compute", "math", "运算", "加", "减", "乘", "除"]) or any(c in "0123456789+-*/()." for c in query):
                    # 处理数学表达式
                    expression = ''.join(c for c in query if c in "0123456789+-*/() .")
                    if not expression:
                        message = "请提供有效的数学表达式"
                        yield json.dumps({
                            "is_task_complete": False,
                            "require_user_input": True,
                            "content": message,
                            "id": task_id,
                            "taskId": task_id,
                            "status": {"message": message}
                        })
                        return
                    
                    # 模拟思考过程
                    message = "正在分析数学表达式..."
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.5)
                    
                    message = f"正在分析数学表达式... 解析 \"{expression}\""
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.5)
                    
                    result = evaluate_math_expression(expression)
                    yield json.dumps({
                        "is_task_complete": True,
                        "require_user_input": False,
                        "content": result,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": result}
                    })
                
                elif any(keyword in query_lower for keyword in ["系统", "状态", "system", "status", "硬件", "hardware", "内存", "memory", "cpu"]):
                    # 获取系统状态，分段显示
                    message = "正在获取系统状态..."
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.5)
                    
                    message = "正在获取CPU信息..."
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.3)
                    
                    cpu_percent = psutil.cpu_percent(interval=0.5)
                    message = f"正在获取CPU信息... CPU使用率: {cpu_percent}%"
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.3)
                    
                    message = f"正在获取CPU信息... CPU使用率: {cpu_percent}%\n正在获取内存信息..."
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    
                    memory = psutil.virtual_memory()
                    await asyncio.sleep(0.3)
                    
                    message = (
                        f"正在获取CPU信息... CPU使用率: {cpu_percent}%\n"
                        f"正在获取内存信息... 内存使用: {memory.percent}% "
                        f"(已用: {memory.used/1024/1024:.2f} MB, 总计: {memory.total/1024/1024:.2f} MB)"
                    )
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.3)
                    
                    message = f"{message}\n正在获取磁盘信息..."
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    disk = psutil.disk_usage('/')
                    await asyncio.sleep(0.3)
                    
                    # 最终完整状态
                    final_status = (
                        f"系统状态:\n"
                        f"- CPU使用率: {cpu_percent}%\n"
                        f"- 内存使用: {memory.percent}% (已用: {memory.used/1024/1024:.2f} MB, 总计: {memory.total/1024/1024:.2f} MB)\n"
                        f"- 磁盘使用: {disk.percent}% (已用: {disk.used/1024/1024/1024:.2f} GB, 总计: {disk.total/1024/1024/1024:.2f} GB)"
                    )
                    yield json.dumps({
                        "is_task_complete": True,
                        "require_user_input": False,
                        "content": final_status,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": final_status}
                    })
                
                else:
                    # 默认帮助信息
                    message = "我是一个支持两种功能的模拟Agent:"
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.5)
                    
                    message = "我是一个支持两种功能的模拟Agent:\n1. 数学运算"
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.5)
                    
                    message = (
                        "我是一个支持两种功能的模拟Agent:\n"
                        "1. 数学运算 - 示例: '计算 2 + 2' 或 '5 * 10是多少'\n"
                        "2. 系统状态"
                    )
                    yield json.dumps({
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
                    await asyncio.sleep(0.5)
                    
                    message = (
                        "我是一个支持两种功能的模拟Agent:\n"
                        "1. 数学运算 - 示例: '计算 2 + 2' 或 '5 * 10是多少'\n"
                        "2. 系统状态 - 示例: '显示系统状态' 或 '硬件使用情况'"
                    )
                    yield json.dumps({
                        "is_task_complete": True,
                        "require_user_input": True,
                        "content": message,
                        "id": task_id,
                        "taskId": task_id,
                        "status": {"message": message}
                    })
        except Exception as e:
                logger.error(f"生成流式响应时出错: {str(e)}")
                logger.exception("详细错误信息:")
                error_msg = f"处理请求时发生错误: {str(e)}"
                yield json.dumps({
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": error_msg,
                    "error": error_msg,
                    "id": task_id,
                    "taskId": task_id,
                    "status": {"message": error_msg}
                })
        
        # 返回流式响应，注意设置正确的Content-Type
    return StreamingResponse(
            (f"data: {chunk}\n\n" for chunk in generate_response()),
            media_type="text/event-stream"
        )
    
    except Exception as e:
        logger.error(f"处理流式任务时出错: {str(e)}")
        logger.exception("详细错误信息:")
        task_id = str(uuid.uuid4())
        error_msg = f"处理请求时发生错误: {str(e)}"
        response = TaskResponse(
            is_task_complete=False,
            require_user_input=True,
            content=error_msg,
            error=error_msg,
            id=task_id,
            taskId=task_id,
            status={"message": error_msg}
        )
        return response.to_dict()

# 兼容旧路径
@app.post("/task/stream")
async def handle_task_stream_legacy(request: Request, auth_info: dict = Depends(verify_auth_headers)):
    """兼容旧路径的流式请求处理端点"""
    return await handle_streaming_task(request, auth_info)

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10001))
    logger.info(f"启动Auth Headers Mock Agent服务，端口: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, ssl_keyfile=None, ssl_certfile=None) 
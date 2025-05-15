from typing import List, Any, Optional
from pydantic import BaseModel

class TaskResponse(BaseModel):
    """任务响应类（jsonrpc 2.0格式）"""
    jsonrpc: str = "2.0"
    id: str
    result: List[Any]
    error: Optional[Any] = None 
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
import yaml
import os
from fastapi import FastAPI

def setup_swagger_docs(app: FastAPI):
    """设置Swagger文档，而不干扰现有API功能"""
    
    # 自定义OpenAPI文档函数
    def custom_openapi():
        # 尝试从文件读取OpenAPI文档
        openapi_path = os.path.join(os.path.dirname(__file__), 'openapi.yaml')
        if os.path.exists(openapi_path):
            try:
                with open(openapi_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            except Exception as e:
                print(f"Error loading OpenAPI file: {e}")
        
        # 如果文件不存在或读取失败，则使用FastAPI自动生成
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title="Demo3 API Documentation",
            version="1.0.0",
            description="API documentation for the Demo3 module with Solana wallet authentication",
            routes=app.routes,
        )
        
        # 自定义文档
        openapi_schema["info"] = {
            "title": "Demo3 API Documentation",
            "description": "API documentation for the Demo3 module of A2A project with Solana wallet authentication.",
            "version": "1.0.0",
            "contact": {
                "name": "A2A Team"
            }
        }
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    # 为应用程序添加自定义OpenAPI路由，使其不干扰现有API端点
    @app.get("/api/docs", include_in_schema=False)
    async def get_documentation():
        return get_swagger_ui_html(
            openapi_url="/api/openapi.json",
            title="Demo3 API Documentation",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
        )
    
    @app.get("/api/redoc", include_in_schema=False)
    async def get_redoc_documentation():
        return get_redoc_html(
            openapi_url="/api/openapi.json",
            title="Demo3 API Documentation",
            redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
        )
    
    @app.get("/api/openapi.json", include_in_schema=False)
    async def get_openapi_json():
        return custom_openapi()
    
    # 返回应用程序以支持链式调用
    return app 
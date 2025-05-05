# Demo3 API 文档使用说明

本项目提供了基于OpenAPI规范的API文档，方便开发者了解和使用所有可用的API接口。

## 使用方式

API文档提供了两种查看方式：

1. **Swagger UI**: 提供交互式界面，可直接在浏览器中测试API请求
   - 访问地址: `http://localhost:12000/api/docs`

2. **ReDoc**: 提供更友好的阅读体验
   - 访问地址: `http://localhost:12000/api/redoc`

3. **原始OpenAPI规范文件**:
   - 访问地址: `http://localhost:12000/api/openapi.json`
   - 文件位置: `demo3/ui/openapi.yaml`

## 鉴权说明

所有API请求需要使用Solana钱包签名进行鉴权。请在发送API请求时包含以下请求头:

- `X-Solana-PublicKey`: Solana钱包公钥
- `X-Solana-Nonce`: 签名到期的毫秒级时间戳
- `X-Solana-Signature`: 使用钱包私钥对Nonce签名后的Base64编码字符串

## 依赖安装

如果您想在本地运行API文档，需要安装以下依赖:

```bash
pip install pyyaml fastapi
```

## 文档定制

如需修改API文档，可以直接编辑`openapi.yaml`文件。系统会优先使用该文件中的定义，如果文件不存在或读取失败，则会自动从代码中生成文档。

## 注意事项

- API文档路径(`/api/docs`, `/api/redoc`, `/api/openapi.json`)不会影响现有API功能
- 所有API请求都需要Solana钱包签名，包括在Swagger UI中的测试
- 在生产环境中请配置适当的CORS和安全策略 
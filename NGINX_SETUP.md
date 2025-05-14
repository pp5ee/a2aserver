# A2A Nginx配置指南

本文档提供了使用Nginx为A2A前后端服务配置反向代理的说明。

## 概述

此配置将：
- 为前端和API设置HTTPS访问
- 配置SSL证书
- 将HTTPS请求反向代理到本地运行的服务
- 支持WebSocket安全连接 (WSS)

## 端口配置

- 前端服务: 本地端口 `3001`，通过 `https://agenticdao.net` 访问
- 后端API: 本地端口 `12000`，通过 `https://agenticdao.net/beapi/` 访问
  - 在本地开发环境中，API直接通过 `http://localhost:12000` 访问
- WebSocket服务: 本地端口 `12000`，路径 `/api/ws`
  - 生产环境: `wss://agenticdao.net/api/ws`
  - 开发环境: `ws://localhost:12000/api/ws`

## 部署步骤

1. 确保SSL证书文件位于正确位置：
   - `/home/ubuntu/agenticdao_ca.crt` (CA证书)
   - `/home/ubuntu/agenticdao.crt` (域名证书)
   - `/home/ubuntu/agenticdaonet.key` (私钥)

2. 运行Nginx配置脚本：
   ```bash
   chmod +x setup_nginx.sh
   ./setup_nginx.sh
   ```

3. 手动启动前端服务（端口3001）和后端服务（端口12000）

## 前端服务

您需要自行确保前端服务运行在端口3001上。例如，对于Vue.js项目，您可以：

```bash
cd ~/Documents/GitHub/a2aserver/server/vue-frontend
# 启动开发服务器
npm run serve -- --port 3001
# 或者构建并使用静态文件服务器
npm run build
npx serve -s dist -l 3001
```

## 前端API配置

前端代码现在会根据运行环境自动选择正确的API基础URL：

1. **本地开发环境**：
   - 当在 `localhost` 或 `127.0.0.1` 访问前端时
   - API请求会直接发送到 `http://localhost:12000`
   - WebSocket连接会使用 `ws://localhost:12000/api/ws`

2. **生产环境**：
   - 当在其他域名（如 `agenticdao.net`）访问前端时
   - API请求会发送到当前域名加 `/beapi`，例如 `https://agenticdao.net/beapi`
   - WebSocket连接会使用 `wss://agenticdao.net/api/ws`

前端代码中不需要做任何更改，配置会自动检测环境并使用合适的API和WebSocket URL。

## 后端服务

您需要自行确保后端服务运行在端口12000上。例如：

```bash
cd ~/Documents/GitHub/a2aserver/server
# 启动后端服务
python main.py
```

注意：后端API需要正确处理请求路径。由于Nginx配置会移除`/beapi`前缀再转发请求，后端不需要添加额外的路径前缀处理。

## WebSocket配置

Nginx的WebSocket配置允许前端通过WSS安全连接与后端WebSocket服务通信：

1. **支持的路径**: `/api/ws`
2. **协议升级**: 配置了必要的 `Upgrade` 和 `Connection` 头
3. **超时设置**: 
   - `proxy_read_timeout`: 300秒
   - `proxy_connect_timeout`: 75秒
   - `proxy_send_timeout`: 300秒
4. **认证传递**: 配置了Solana钱包认证相关的HTTP头传递

示例前端WebSocket连接代码:

```javascript
// 前端WebSocket连接自动判断环境
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsHost = location.hostname === 'localhost' || location.hostname === '127.0.0.1' 
  ? `${location.hostname}:12000` 
  : location.host;
const wsUrl = `${wsProtocol}//${wsHost}/api/ws`;

const socket = new WebSocket(wsUrl);
```

## 验证配置

配置完成后，您可以验证：

1. Nginx状态：
   ```bash
   sudo systemctl status nginx
   ```

2. 查看Nginx日志：
   ```bash
   sudo tail -f /var/log/nginx/access.log
   sudo tail -f /var/log/nginx/error.log
   ```

3. 测试API连接：
   ```bash
   # 生产环境
   curl -k https://agenticdao.net/beapi/health
   
   # 本地环境
   curl http://localhost:12000/health
   ```

4. 测试WebSocket连接:
   
   使用在线WebSocket测试工具(如websocket.org)连接到:
   - 生产环境: `wss://agenticdao.net/api/ws`
   - 本地环境: `ws://localhost:12000/api/ws`

5. 在浏览器中访问前端：
   - 生产环境：`https://agenticdao.net`
   - 本地环境：`http://localhost:3001`

## CORS配置

Nginx配置中已包含API服务和WebSocket的CORS设置，允许来自同一域名的请求。由于前端和API现在使用同一域名，理论上不再需要CORS设置，但为了兼容性和安全，仍保留了相关配置。

在本地开发模式下，前端访问API和WebSocket时会产生跨域请求，需要确保后端服务允许来自`localhost:3001`的跨域请求。

## 故障排除

### Nginx启动失败

检查配置语法：
```bash
sudo nginx -t
```

查看详细错误日志：
```bash
sudo tail -f /var/log/nginx/error.log
```

### 无法连接到服务

1. 确认前端和后端服务正在运行：
   ```bash
   netstat -tulpn | grep 3001
   netstat -tulpn | grep 12000
   ```

2. 检查前端API配置：
   - 在浏览器控制台中，查看是否显示了正确的API基础URL
   - 在本地环境中，应显示`http://localhost:12000`
   - 在生产环境中，应显示`https://agenticdao.net/beapi`

3. WebSocket连接问题:
   - 使用浏览器开发者工具检查WebSocket连接状态
   - 查看是否有协议升级错误
   - 确认WebSocket URL是否正确(ws://或wss://)
   - 检查认证参数是否正确传递

4. 本地环境CORS问题：
   - 如果在本地开发时遇到CORS错误，确保后端服务允许来自`localhost:3001`的跨域请求
   - 可以在后端添加以下CORS头：
     ```
     Access-Control-Allow-Origin: http://localhost:3001
     Access-Control-Allow-Methods: GET, POST, OPTIONS
     Access-Control-Allow-Headers: Content-Type, Authorization, X-Solana-PublicKey, X-Solana-Signature, X-Solana-Nonce
     ``` 
# A2A Nginx配置指南

本文档提供了使用Nginx为A2A前后端服务配置反向代理的说明。

## 概述

此配置将：
- 为前端和API设置HTTPS访问
- 配置SSL证书
- 将HTTPS请求反向代理到本地运行的服务
- 支持开发环境与生产环境的不同API访问方式

## 端口配置

- 前端服务: 本地端口 `3001`，通过 `https://agenticdao.net` 访问
- 后端API: 本地端口 `12000`，公网通过 `https://agenticdao.net/beapi/` 访问

## 本地开发与生产环境

本配置支持两种API访问模式：

1. **本地开发环境**: 
   - 前端可以直接访问 `http://localhost:12000` 的API接口
   - 无需修改API路径，保持与后端服务原有接口一致

2. **生产环境**: 
   - 前端通过 `https://agenticdao.net/beapi/` 访问API
   - 需在前端配置中设置正确的基础URL

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

## 前端服务配置

### 本地开发

在本地开发时，前端直接访问本地后端：

```javascript
// 前端API基础URL配置 - 本地开发环境
const apiBaseUrl = 'http://localhost:12000';
```

### 生产环境

部署到生产环境时，修改为：

```javascript
// 前端API基础URL配置 - 生产环境
const apiBaseUrl = 'https://agenticdao.net/beapi';
```

您可以使用环境变量来区分不同环境：

```javascript
// Vue.js环境变量配置示例
const apiBaseUrl = process.env.NODE_ENV === 'development' 
  ? 'http://localhost:12000' 
  : 'https://agenticdao.net/beapi';
```

## 后端服务

您需要自行确保后端服务运行在端口12000上：

```bash
cd ~/Documents/GitHub/a2aserver/server
# 启动后端服务
python main.py
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
   # 测试本地API
   curl http://localhost:12000/health
   
   # 测试公网API
   curl -k https://agenticdao.net/beapi/health
   ```

4. 在浏览器中访问前端：`https://agenticdao.net`

## CORS配置

Nginx配置中已设置CORS允许任何来源的请求（`Access-Control-Allow-Origin: *`），这样本地开发时也能直接访问生产API。在安全要求较高的环境中，您可以将其限制为特定域名。

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

### API路径问题

本地开发时：
- API请求应直接发送到 `http://localhost:12000/your-endpoint`

生产环境：
- API请求应发送到 `https://agenticdao.net/beapi/your-endpoint`

如果遇到404错误，请检查：
1. 前端是否使用了正确的API基础URL
2. Nginx日志中是否有请求转发记录
3. 后端服务是否正确响应请求 
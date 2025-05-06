# A2A Nginx配置指南

本文档提供了使用Nginx为A2A前后端服务配置反向代理的说明。

## 概述

此配置将：
- 为前端和API设置HTTPS访问
- 配置SSL证书
- 将HTTPS请求反向代理到本地运行的服务

## 端口配置

- 前端服务: 本地端口 `3000`，通过 `https://agenticdao.net` 访问
- 后端API: 本地端口 `12000`，通过 `https://api.agenticdao.net` 访问

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

3. 手动启动前端服务（端口3000）和后端服务（端口12000）

## 前端服务

您需要自行确保前端服务运行在端口3000上。例如，对于Vue.js项目，您可以：

```bash
cd ~/Documents/GitHub/a2aserver/server/vue-frontend
# 设置环境变量
export VUE_APP_API_URL=https://api.agenticdao.net
# 启动开发服务器
npm run serve -- --port 3000
# 或者构建并使用静态文件服务器
npm run build
npx serve -s dist -l 3000
```

## 后端服务

您需要自行确保后端服务运行在端口12000上。例如：

```bash
cd ~/Documents/GitHub/a2aserver/server
# 启动后端服务
python main.py
```

确保您的后端配置正确设置监听端口12000。

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
   curl -k https://api.agenticdao.net/health
   ```

4. 在浏览器中访问前端：`https://agenticdao.net`

## CORS配置

Nginx配置中已包含API服务的CORS设置，允许来自 `https://agenticdao.net` 的跨域请求。如果需要允许其他源，请修改Nginx配置中的 `Access-Control-Allow-Origin` 头。

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
   netstat -tulpn | grep 3000
   netstat -tulpn | grep 12000
   ```

2. 检查防火墙设置：
   ```bash
   sudo ufw status
   ```

3. 验证DNS设置是否正确指向服务器IP。 
# 生产环境部署指南

本文档提供了在生产环境中部署A2A应用的详细步骤，特别关注了解决"Invalid Host header"问题。

## 部署步骤

### 1. 配置Nginx

首先运行Nginx配置脚本：

```bash
chmod +x setup_nginx.sh
./setup_nginx.sh
```

这将设置Nginx反向代理，将请求从`https://agenticdao.net`转发到本地运行的前端服务（端口3001），将`https://agenticdao.net/beapi/`请求转发到API服务（端口12000）。

### 2. 构建并部署前端

#### 2.1 开发模式部署（调试用）

如果需要以开发模式运行前端（便于调试），请使用以下命令：

```bash
# 使用我们提供的脚本
chmod +x start_frontend_dev.sh
./start_frontend_dev.sh

# 或直接运行命令
cd ~/Documents/GitHub/a2aserver/server/vue-frontend
npm run serve -- --port 3001 --host 0.0.0.0 --public localhost --disable-host-check
```

#### 2.2 生产模式部署（推荐）

对于生产环境，应该构建前端并提供静态文件：

```bash
# 使用我们提供的脚本
chmod +x start_production_frontend.sh
./start_production_frontend.sh

# 或手动执行以下步骤
cd ~/Documents/GitHub/a2aserver/server/vue-frontend
npm run build
npx serve -s dist -l 3001
```

### 3. 启动后端API服务

确保后端API服务运行在端口12000上：

```bash
cd ~/Documents/GitHub/a2aserver/server
python main.py
```

## 解决Invalid Host header问题

我们已经在多个层面解决了"Invalid Host header"问题：

### 1. Nginx配置

Nginx配置已经修改为：
- 在反向代理到前端服务时设置`Host`头为`localhost`
- 添加了`X-Forwarded-Host`头传递原始主机名
- 增加了WebSocket支持
- 禁用了缓存以避免开发服务器问题

### 2. Vue配置

`vue.config.js`中添加了以下配置：
- `allowedHosts: 'all'`
- `disableHostCheck: true` 
- 设置了`historyApiFallback`支持
- 配置了CORS头允许所有来源

### 3. 环境变量

启动脚本中设置了关键环境变量：
- `HOST=0.0.0.0`
- `VUE_CLI_SERVICE_CONFIG_DISABLE_HOST_CHECK=true`

## 验证部署

配置完成后，您可以通过以下步骤验证部署是否成功：

1. 访问前端：`https://agenticdao.net`
2. 检查API连接：`https://agenticdao.net/beapi/health`
3. 检查控制台是否有错误

## 故障排除

### 仍然出现Invalid Host header错误

如果仍然出现此错误，可以尝试：

1. **使用纯静态文件服务**：
   ```bash
   cd ~/Documents/GitHub/a2aserver/server/vue-frontend
   npm run build
   npm install -g serve
   serve -s dist -l 3001
   ```

2. **检查浏览器请求**：
   - 使用开发者工具检查请求头
   - 确认请求是否正确转发到前端服务

3. **检查Nginx日志**：
   ```bash
   sudo tail -f /var/log/nginx/error.log
   sudo tail -f /var/log/nginx/access.log
   ```

### CORS问题

如果遇到CORS错误：

1. 确认API服务是否返回正确的CORS头
2. 检查前端请求中是否包含预期的来源
3. 确保Nginx配置中正确设置了`Access-Control-Allow-Origin`头

## 维护

### 重启服务

如果需要重启服务：

```bash
# 重启Nginx
sudo systemctl restart nginx

# 重启前端服务
pkill -f "serve -s dist"
./start_production_frontend.sh

# 重启后端API
# 取决于您的后端服务启动方式
```

### 更新部署

当代码有更新时：

```bash
cd ~/Documents/GitHub/a2aserver
git pull

# 重新构建并启动前端
cd server/vue-frontend
npm run build
./start_production_frontend.sh

# 重启后端API
cd ../
# 取决于您的后端服务启动方式
``` 
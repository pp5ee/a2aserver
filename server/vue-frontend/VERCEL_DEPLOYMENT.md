# Vercel部署指南

本文档说明如何将A2A前端部署到Vercel，同时保持与后端API的正确连接。

## 部署步骤

1. 在[Vercel](https://vercel.com)上创建一个账户（如果你还没有）

2. 通过GitHub连接你的仓库，或者使用Vercel CLI进行部署：
   ```bash
   npm install -g vercel
   cd server/vue-frontend
   vercel
   ```

3. 部署完成后，你会得到一个Vercel提供的域名（如`your-app.vercel.app`）

## 配置API连接

当应用部署到Vercel后，它无法直接使用开发环境中的代理设置。你有两种方式配置API连接：

### 方式1：通过界面配置（推荐）

应用首次加载时，会自动显示API配置面板（或点击页面顶部的"API配置"按钮），你需要：

1. 输入你的后端API的完整URL（如：`https://your-api-server.com`）
2. 点击"保存"按钮
3. 配置会保存在浏览器的localStorage中，下次访问时会自动使用

### 方式2：设置环境变量（适合团队）

在Vercel的项目设置中：

1. 进入项目设置 -> 环境变量
2. 添加环境变量`VUE_APP_API_URL`，值设为你的API服务器地址
3. 重新部署应用

## 后端API要求

确保你的后端API服务器：

1. 允许来自Vercel域名的跨域请求（CORS）
2. 使用HTTPS（Vercel默认使用HTTPS）
3. 公开可访问（或至少从Vercel服务器可访问）

## 开发与调试

如果你需要在本地测试Vercel环境的行为：

1. 在浏览器开发者控制台中执行：
   ```javascript
   window._debugVercelEnv = true;
   ```

2. 刷新页面，API配置界面将会显示

## 常见问题

- **API连接失败？**  
  确保你设置的API URL是完整的（包含https://），且API服务器允许CORS请求

- **配置后设置丢失？**  
  API设置保存在浏览器的localStorage中，清除浏览器数据会导致设置丢失

- **部署后找不到资源？**  
  确保你的应用使用相对路径引用资源，而不是绝对路径 
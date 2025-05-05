# A2A Vue 前端

这是A2A（Agent-to-Agent）系统的Vue前端实现版本，基于demo3的功能进行开发。

## 功能特点

- 对话管理：创建和管理与代理的对话
- 实时消息显示：支持文本、图像和JSON数据显示
- 代理管理：查看和注册远程代理
- 任务跟踪：查看和管理代理执行的任务
- 事件监控：查看系统事件
- 设置管理：配置API密钥和系统设置

## 技术栈

- Vue 3
- TypeScript
- Vuex 4（状态管理）
- Vue Router（路由管理）
- Axios（HTTP请求）

## 项目结构

```
vue-frontend/
│
├── src/                    # 源代码目录
│   ├── components/         # 通用组件
│   ├── views/              # 页面视图组件
│   ├── store/              # Vuex状态管理
│   ├── router/             # 路由配置
│   ├── App.vue             # 根组件
│   └── main.ts             # 入口文件
│
├── public/                 # 静态资源目录
└── package.json            # 项目配置文件
```

## 安装和使用

### 前提条件

- Node.js 14.x 或更高版本
- npm 或 yarn

### 安装依赖

```bash
cd vue-frontend
npm install
# 或
yarn install
```

### 开发环境启动

```bash
npm run serve
# 或
yarn serve
```

应用将运行在 http://localhost:8080

### 生产环境构建

```bash
npm run build
# 或
yarn build
```

## 环境变量配置

创建 `.env` 文件可以配置环境变量：

```
VUE_APP_SERVER_URL=http://localhost:12000
```

## 后端接口

Vue前端需要与A2A后端服务器通信。默认情况下，前端会尝试连接到 `http://localhost:12000`。您可以通过环境变量修改这一配置。

要启动后端服务器，请参考主项目的README文件。

## 多用户支持

本Vue前端实现为单用户设计，但可以进行扩展以支持多用户场景：

1. 添加用户认证系统
2. 修改API请求以包含用户标识符
3. 在后端服务中为每个用户创建独立的代理管理器

## 后端服务兼容性

该前端设计用于与demo3中的后端服务配合使用，它期望后端服务实现以下API端点：

- `/conversation/create` - 创建新对话
- `/conversation/list` - 列出所有对话
- `/message/send` - 发送消息
- `/message/list` - 列出对话中的消息
- `/message/pending` - 获取待处理消息
- `/task/list` - 列出任务
- `/agent/register` - 注册代理
- `/agent/list` - 列出代理
- `/api_key/update` - 更新API密钥

## 许可证

与主项目相同 
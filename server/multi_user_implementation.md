# A2A 多用户实现文档

## 功能概述

本实现为A2A（Agent-to-Agent）系统添加了多用户支持，使得每个用户都能拥有独立的代理环境。主要特点包括：

1. 使用Solana钱包地址作为用户标识
2. 每个用户有独立的代理列表和会话
3. 支持MySQL数据库持久化或内存模式运行
4. 无需修改现有前端代码即可使用多用户功能

## 技术实现

### 核心组件

1. **UserSessionManager**：
   - 单例模式，管理所有用户的会话
   - 为每个用户维护独立的ADKHostManager实例
   - 支持数据库模式和内存模式，自动切换

2. **ConversationServer**：
   - 修改所有API端点，根据请求头中的钱包地址分配对应的用户管理器
   - 保持API接口不变，确保前端无需修改

3. **运行模式**：
   - **数据库模式**：使用MySQL存储用户数据，实现持久化
   - **内存模式**：无需数据库，所有数据保存在内存中（服务器重启后丢失）

## 工作流程

1. 用户通过前端连接钱包
2. 前端在所有API请求中添加`X-Solana-PublicKey`头
3. 后端根据钱包地址获取或创建对应的ADKHostManager实例
4. 用户的操作仅影响自己的环境，不影响其他用户

## 配置说明

### 运行模式

系统会自动检测MySQL连接器是否可用：
- 如果可用且能连接数据库，使用数据库模式
- 如果不可用或连接出错，自动切换到内存模式

### 数据库配置

默认配置（仅在数据库模式下使用）：
- 主机：localhost
- 用户：root
- 密码：orangepi123
- 数据库：a2a

如需修改，请编辑`user_session_manager.py`中的连接参数。

### 多用户开关

在`ConversationServer`类初始化中设置`self.use_multi_user = True`来启用多用户功能。
设置为`False`将回退到单用户模式。

## 安装说明

### 基本安装

```bash
# 进入项目目录
cd demo3/ui

# 安装基本依赖
pip install -r requirements.txt

# 启动服务器（自动使用内存模式）
python main.py
```

### 数据库模式安装（可选）

如需使用MySQL进行持久化存储，请安装MySQL连接器：

```bash
# 安装MySQL连接器
pip install mysql-connector-python

# 确保MySQL服务已启动并创建了用户
# 默认使用 root/orangepi123 连接本地MySQL
```

## 测试方法

可以使用不同的钱包地址测试多用户隔离：

```bash
# 用户1注册代理
curl -H "X-Solana-PublicKey: wallet1" -X POST http://localhost:12000/agent/register -d '{"params": "http://agent1.example.com"}'

# 用户2注册代理
curl -H "X-Solana-PublicKey: wallet2" -X POST http://localhost:12000/agent/register -d '{"params": "http://agent2.example.com"}'

# 检查用户1代理列表
curl -H "X-Solana-PublicKey: wallet1" -X POST http://localhost:12000/agent/list

# 检查用户2代理列表
curl -H "X-Solana-PublicKey: wallet2" -X POST http://localhost:12000/agent/list
```

## 前端使用说明

现有前端代码已经在API请求拦截器中添加了钱包地址，不需要任何修改即可支持多用户：

```javascript
// 前端代码中已有的拦截器
apiClient.interceptors.request.use(
  config => {
    // 从localStorage获取Solana钱包信息
    const solanaWallet = JSON.parse(localStorage.getItem('solanaWallet') || '{}')
    
    // 添加Solana钱包信息到请求头
    if (solanaWallet && solanaWallet.publicKey) {
      config.headers['X-Solana-PublicKey'] = solanaWallet.publicKey
    }
    
    return config
  }
)
```

## 性能考虑

1. **内存优化**：
   - 系统会定期清理长时间不活跃的用户会话（默认60分钟）
   - 可以在`_run_cleanup_task`方法中调整清理间隔

2. **数据库连接**：
   - 使用连接池或重连机制确保长时间运行的稳定性
   - 数据库操作错误会自动切换到内存模式，不影响核心功能

3. **容错能力**：
   - 即使没有安装MySQL或数据库连接失败，系统也能在内存模式下正常运行
   - 所有错误都有适当的日志记录和处理

## 扩展建议

1. **用户认证**：
   - 目前仅使用钱包地址识别用户，可添加签名验证增强安全性

2. **资源限制**：
   - 可为每个用户设置资源限制，如最大代理数量、会话数等

3. **监控面板**：
   - 添加管理界面显示当前活跃用户数和资源使用情况

4. **持久化选项**：
   - 提供更多数据存储选项，如SQLite或Redis等 
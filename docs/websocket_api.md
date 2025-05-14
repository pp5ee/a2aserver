# WebSocket API 接口文档

本文档描述了应用程序的WebSocket接口，用于实时消息推送和任务状态更新。

## 连接

### 连接URL

根据环境使用不同的WebSocket连接URL：

**开发环境：**
```
ws://localhost:12000/api/ws
```

**生产环境：**
```
wss://agenticdao.net/api/ws
```

前端代码会根据当前域名自动选择正确的协议和URL：
```javascript
// 自动根据环境选择WebSocket URL
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const hostname = window.location.hostname;
const wsUrl = hostname === 'localhost' || hostname === '127.0.0.1' 
  ? `${protocol}//${hostname}:12000/api/ws`
  : `${protocol}//${window.location.host}/api/ws`;
```

### 连接参数

连接时需要提供以下URL参数:

| 参数名称 | 必填 | 描述 |
| ------- | --- | ---- |
| publicKey | 是 | 用户的钱包公钥地址 |
| nonce | 是 | 用于签名验证的随机字符串 |
| signature | 是 | 签名结果，用于验证身份 |

### 示例连接URL

```
wss://agenticdao.net/api/ws?publicKey=YOUR_WALLET_ADDRESS&nonce=NONCE_STRING&signature=SIGNATURE_STRING
```

## 部署配置

当部署到生产环境时，需要配置Nginx支持WebSocket连接：

1. 确保你的Nginx配置包含以下WebSocket专用配置:

```nginx
# WebSocket路径配置
location /api/ws {
    proxy_pass http://localhost:12000/api/ws;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    
    # 传递认证相关头
    proxy_set_header X-Solana-PublicKey $http_x_solana_publickey;
    proxy_set_header X-Solana-Signature $http_x_solana_signature;
    proxy_set_header X-Solana-Nonce $http_x_solana_nonce;
    
    # WebSocket特有配置
    proxy_read_timeout 300s;     # 增加读取超时
    proxy_connect_timeout 75s;   # 连接超时
    proxy_send_timeout 300s;     # 发送超时
}
```

2. 确保系统防火墙允许WebSocket流量通过

3. 如果使用SSL终止代理，确保它支持WebSocket协议升级

## 消息格式

所有消息均为JSON格式，包含一个`type`字段用于标识消息类型。

### 通用消息结构

```json
{
  "type": "消息类型",
  ... 其他字段 ...
}
```

## 消息类型

### 1. 连接确认消息 (connection_established)

当WebSocket连接成功建立后，服务器会发送此消息。

```json
{
  "type": "connection_established",
  "wallet_address": "用户钱包地址",
  "timestamp": "连接建立时间ISO格式"
}
```

### 2. 新消息 (new_message)

当会话中有新消息时，服务器会发送此消息。

```json
{
  "type": "new_message",
  "conversation_id": "会话ID",
  "message": {
    "id": "消息ID",
    "role": "消息角色，如'user'或'agent'",
    "content": [
      {
        "type": "文本类型，如'text'",
        "text": "消息内容"
      }
      // 可能包含多个内容部分
    ]
  }
}
```

### 3. 任务更新 (task_update)

当任务状态发生变化时，服务器会发送此消息。

```json
{
  "type": "task_update",
  "conversation_id": "会话ID",
  "message_id": "关联的消息ID",  // 与任务关联的消息ID，可用于UI关联
  "task": {
    "id": "任务ID",
    "sessionId": "会话ID",
    "status": {
      "state": "任务状态，如'submitted'、'working'、'completed'等",
      "message": "状态描述文本",
      "timestamp": "状态更新时间"
    },
    "history": [  // 可选，任务的历史消息
      {
        "role": "消息角色",
        "parts": [
          {
            "type": "部分类型",
            "text": "文本内容"
          }
        ]
      }
    ],
    "artifacts": [  // 可选，任务产生的产出物
      {
        "name": "产出物名称",
        "parts": [
          {
            "type": "部分类型",
            "text": "文本内容"
          }
        ]
      }
    ]
  }
}
```

### 4. 心跳消息 (ping/pong)

用于保持连接活跃的心跳机制。

客户端发送:
```json
{
  "type": "ping",
  "timestamp": "ISO格式的时间戳"
}
```

服务器响应:
```json
{
  "type": "pong",
  "timestamp": "ISO格式的时间戳"
}
```

## 错误处理

### 连接错误

如果连接出现问题，WebSocket可能会断开，客户端应实现自动重连机制。

### 消息处理错误

如果服务器处理消息时出错，可能会返回错误消息：

```json
{
  "type": "error",
  "code": "错误代码",
  "message": "错误描述"
}
```

## 客户端实现示例

以下是基本的JavaScript客户端实现示例：

```javascript
// 建立连接
function connectWebSocket(walletAddress, nonce, signature) {
  // 自动选择协议和主机
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const hostname = window.location.hostname;
  const host = hostname === 'localhost' || hostname === '127.0.0.1'
    ? `${hostname}:12000`
    : window.location.host;
  
  const wsUrl = `${protocol}//${host}/api/ws?publicKey=${encodeURIComponent(walletAddress)}&nonce=${encodeURIComponent(nonce)}&signature=${encodeURIComponent(signature)}`;
  
  const socket = new WebSocket(wsUrl);
  
  // 连接打开
  socket.onopen = () => {
    console.log('WebSocket连接已建立');
    startPingInterval(socket);
  };
  
  // 接收消息
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
      case 'connection_established':
        console.log('连接已确认:', data);
        break;
      case 'new_message':
        console.log('收到新消息:', data);
        handleNewMessage(data);
        break;
      case 'task_update':
        console.log('任务更新:', data);
        handleTaskUpdate(data);
        break;
      case 'pong':
        console.log('收到pong响应');
        break;
      default:
        console.log('未知消息类型:', data);
    }
  };
  
  // 连接关闭
  socket.onclose = () => {
    console.log('WebSocket连接已关闭');
    // 实现重连逻辑
    setTimeout(() => reconnect(), 5000);
  };
  
  // 连接错误
  socket.onerror = (error) => {
    console.error('WebSocket错误:', error);
  };
  
  return socket;
}

// 心跳机制
function startPingInterval(socket) {
  setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: 'ping',
        timestamp: new Date().toISOString()
      }));
    }
  }, 30000); // 每30秒发送一次ping
}
```

## 故障排除

### 连接问题

1. **无法建立WSS连接**:
   - 检查Nginx配置是否正确设置了WebSocket代理
   - 确认SSL证书有效
   - 检查浏览器控制台是否有连接或协议升级错误

2. **连接断开**:
   - 检查连接是否保持活跃（心跳机制）
   - 增加Nginx的超时设置
   - 检查服务器负载是否过高

3. **认证失败**:
   - 确保正确传递了钱包地址、nonce和签名参数
   - 检查签名是否过期
   - 验证服务器端接收到的认证信息

### 性能考虑

1. 限制每个用户的连接数
2. 实现消息队列缓冲机制
3. 对大型部署考虑使用专用WebSocket服务器

## 注意事项

1. WebSocket连接可能因网络问题而断开，客户端应实现重连机制
2. 建议实现指数退避重连策略，避免在服务器问题时频繁重连
3. 始终验证收到的消息格式和内容，防止处理错误的消息
4. 确保正确处理任务状态更新，特别是关注任务状态从"working"到"completed"的转变
5. message_id是将任务与原始消息关联的关键，确保在UI中正确处理这种关联 
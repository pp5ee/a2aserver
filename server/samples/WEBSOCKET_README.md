# WebSocket服务使用说明

本文档介绍了如何使用新增的WebSocket服务功能，该功能与现有的HTTP API并行工作，为客户端提供实时消息推送。

## 功能概述

WebSocket服务支持以下实时推送功能：

1. 新的会话消息推送
2. 任务状态更新推送
3. 任务历史记录推送
4. 任务产出物(artifacts)推送

这些功能使客户端可以实时接收更新，而不需要频繁轮询HTTP API。

## 连接WebSocket服务

WebSocket服务端点：`ws://your-server-domain/api/ws`

连接时需要在HTTP头中提供用户的钱包地址：

```
X-Solana-PublicKey: <wallet_address>
```

## 消息格式

### 连接成功消息

当WebSocket连接成功建立后，服务器会发送一条连接成功的消息：

```json
{
  "type": "connection_established",
  "message": "WebSocket连接已成功建立",
  "wallet_address": "<wallet_address>"
}
```

### 新消息推送

当会话中有新消息时，服务器会推送以下格式的消息：

```json
{
  "type": "new_message",
  "conversation_id": "<conversation_id>",
  "message": {
    "id": "<message_id>",
    "role": "<role>",
    "content": [
      {
        "type": "text",
        "text": "<message_content>"
      }
    ]
  }
}
```

### 任务状态更新推送

当任务状态更新时，服务器会推送以下格式的消息：

```json
{
  "type": "task_update",
  "conversation_id": "<conversation_id>",
  "task": {
    "id": "<task_id>",
    "sessionId": "<session_id>",
    "status": {
      "state": "<task_state>",
      "message": "<status_message>",
      "timestamp": "<timestamp>"
    },
    "history": [
      {
        "role": "<role>",
        "parts": [
          {
            "type": "text",
            "text": "<message_text>"
          }
        ]
      }
    ],
    "artifacts": [
      {
        "name": "<artifact_name>",
        "parts": [
          {
            "type": "text",
            "text": "<artifact_content>"
          }
        ]
      }
    ]
  }
}
```

### 心跳消息

客户端可以发送ping消息来保持连接活跃：

```json
{
  "type": "ping",
  "timestamp": "<current_timestamp>"
}
```

服务器会回复pong消息：

```json
{
  "type": "pong",
  "timestamp": "<same_timestamp_from_ping>"
}
```

## 示例客户端

在`samples/websocket_client_example.html`文件中提供了一个简单的WebSocket客户端示例，可以用来测试WebSocket连接和消息接收。

## 与HTTP API并行使用

WebSocket服务与现有的HTTP API是独立的，可以同时使用。客户端可以：

1. 使用HTTP API进行初始数据加载和操作
2. 使用WebSocket接收实时更新

这种方式结合了HTTP API的稳定性和WebSocket的实时性，提供了更好的用户体验。

## 错误处理

如果WebSocket连接中断，客户端应该实现重连逻辑。建议使用指数退避算法进行重连尝试，以避免服务器过载。

## 安全注意事项

WebSocket连接使用与HTTP API相同的认证机制，通过请求头中的钱包地址识别用户。客户端应确保在连接建立时提供正确的钱包地址。

## API信息端点

可以通过以下HTTP端点获取有关WebSocket服务的更多信息：

```
GET /api/websocket-info
```

该端点返回WebSocket服务的配置信息、支持的消息类型和当前活跃连接数。 
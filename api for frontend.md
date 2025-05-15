# A2A Server API文档

## 目录
1. [认证方式](#认证方式)
2. [HTTP API接口](#http-api接口)
3. [WebSocket接口](#websocket接口)

## 认证方式

所有API请求需要在HTTP头中包含以下认证信息：
- `X-Solana-PublicKey`: 用户钱包地址
- `X-Solana-Nonce`: 签名时间戳
- `X-Solana-Signature`: 签名

## HTTP API接口

所有HTTP接口遵循JSON-RPC 2.0规范，请求和响应格式如下：

### 请求格式
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "method": "方法名",
  "params": 参数内容
}
```

### 响应格式
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": 结果内容,
  "error": 错误信息或null
}
```

### 1. 创建会话
- **路径**: `/conversation/create`
- **方法**: POST
- **请求**: 无需参数
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": {
    "conversation_id": "会话ID",
    "is_active": true,
    "name": "",
    "task_ids": [],
    "messages": [],
    "message_count": 0
  },
  "error": null
}
```

### 2. 获取会话列表
- **路径**: `/conversation/list`
- **方法**: POST
- **请求**: 无需参数
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": [
    {
      "conversation_id": "会话ID",
      "is_active": true,
      "name": "会话名称",
      "task_ids": ["任务ID"],
      "messages": [
        {
          "id": "消息ID",
          "role": "用户角色",
          "content": [
            {
              "type": "text",
              "text": "消息内容"
            }
          ]
        }
      ],
      "message_count": 2
    }
  ],
  "error": null
}
```

### 3. 删除会话
- **路径**: `/conversation/delete`
- **方法**: POST
- **请求**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "method": "conversation/delete",
  "params": {
    "conversation_id": "要删除的会话ID"
  }
}
```
- **响应**: 
```json
{
  "status": "success",
  "message": "Conversation {conversation_id} has been successfully deleted"
}
```

### 4. 发送消息
- **路径**: `/message/send`
- **方法**: POST
- **请求**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "method": "message/send",
  "params": {
    "role": "user",
    "parts": [
      {
        "type": "text",
        "text": "消息内容"
      }
    ],
    "metadata": {
      "conversation_id": "会话ID"
    }
  }
}
```
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": {
    "message_id": "消息ID",
    "conversation_id": "会话ID"
  },
  "error": null
}
```

### 5. 获取消息列表
- **路径**: `/message/list`
- **方法**: POST
- **请求**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "method": "message/list",
  "params": "会话ID"
}
```
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": [
    {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "用户消息"
        }
      ],
      "metadata": {
        "message_id": "消息ID",
        "conversation_id": "会话ID",
        "tasks": [
          {
            "id": "任务ID",
            "sessionId": "会话ID",
            "status": {
              "state": "completed",
              "timestamp": "2023-08-01T12:00:00Z"
            },
            "artifacts": [...],
            "history": [...]
          }
        ]
      }
    }
  ],
  "error": null
}
```

### 6. 查询待处理消息
- **路径**: `/message/pending`
- **方法**: POST
- **请求**: 无需参数
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": [
    ["消息ID", "处理状态"]
  ],
  "error": null
}
```

### 7. 获取事件列表
- **路径**: `/events/get`
- **方法**: POST
- **请求**: 无需参数
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": [
    {
      "id": "事件ID",
      "actor": "事件发起者",
      "content": {消息对象},
      "timestamp": 1691580000.123
    }
  ],
  "error": null
}
```

### 8. 获取任务列表
- **路径**: `/task/list`
- **方法**: POST
- **请求**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "method": "task/list",
  "params": {
    "conversation_id": "会话ID" // 可选参数
  }
}
```
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": [
    {
      "id": "任务ID",
      "sessionId": "会话ID",
      "status": {
        "state": "completed",
        "message": {消息对象},
        "timestamp": "2023-08-01T12:00:00Z"
      },
      "artifacts": [
        {
          "name": "制品名称",
          "description": "制品描述",
          "parts": [
            {
              "type": "text",
              "text": "制品内容"
            }
          ],
          "metadata": {...},
          "index": 0,
          "append": null,
          "lastChunk": true
        }
      ],
      "history": [消息对象数组],
      "metadata": {...}
    }
  ],
  "error": null
}
```

### 9. 获取代理列表
- **路径**: `/agent/list`
- **方法**: POST
- **请求**: 无需参数
- **响应**: 
```json
{
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": [
    {
      "name": "代理名称",
      "description": "代理描述",
      "url": "代理URL",
      "provider": "提供商",
      "version": "1.0.0",
      "documentationUrl": "文档URL",
      "capabilities": {
        "streaming": true,
        "pushNotifications": false,
        "stateTransitionHistory": false
      },
      "authentication": {...},
      "defaultInputModes": ["text", "text/plain"],
      "defaultOutputModes": ["text", "text/plain"],
      "skills": [],
      "is_online": "yes",
      "expire_at": "2023-08-31T23:59:59Z",
      "nft_mint_id": "NFT ID"
    }
  ],
  "error": null
}
```

### 10. 获取文件内容
- **路径**: `/message/file/{file_id}`
- **方法**: GET
- **响应**: 文件内容(二进制)

### 11. 获取历史会话
- **路径**: `/history/conversations`
- **方法**: GET
- **响应**: 
```json
{
  "result": [
    {
      "conversation_id": "会话ID",
      "name": "会话名称",
      "is_active": true,
      "created_at": "2023-08-01T12:00:00Z",
      "updated_at": "2023-08-01T12:30:00Z"
    }
  ]
}
```

### 12. 获取历史消息
- **路径**: `/history/messages/{conversation_id}`
- **方法**: GET
- **响应**: 
```json
{
  "result": [
    {
      "message_id": "消息ID",
      "role": "user",
      "content": {
        "parts": [
          {
            "type": "text",
            "text": "消息内容"
          }
        ]
      },
      "created_at": "2023-08-01T12:00:00Z"
    }
  ]
}
```

## WebSocket接口

### 连接
- **URL**: `/api/ws`
- **认证参数**:
  - 可通过HTTP头: `X-Solana-PublicKey`, `X-Solana-Nonce`, `X-Solana-Signature`
  - 或URL参数: `publicKey`, `nonce`, `signature`

### 消息类型

#### 1. 连接成功
```json
{
  "type": "connection_established",
  "message": "WebSocket连接已成功建立",
  "wallet_address": "用户钱包地址"
}
```

#### 2. 心跳请求(客户端发送)
```json
{
  "type": "ping",
  "timestamp": 1691580000123
}
```

#### 3. 心跳响应(服务器回复)
```json
{
  "type": "pong",
  "timestamp": 1691580000123
}
```

#### 4. 新消息通知
```json
{
  "type": "new_message",
  "conversation_id": "会话ID",
  "message": {
    "id": "消息ID",
    "role": "agent",
    "content": [
      {
        "type": "text",
        "text": "消息内容"
      }
    ]
  }
}
```

#### 5. 任务更新
```json
{
  "type": "task_update",
  "conversation_id": "会话ID",
  "jsonrpc": "2.0",
  "id": "请求ID",
  "result": [
    {
      "id": "任务ID",
      "sessionId": "会话ID",
      "status": {
        "state": "completed",
        "message": {消息对象},
        "timestamp": "2023-08-01T12:00:00Z"
      },
      "artifacts": [...],
      "history": [...],
      "metadata": {...}
    }
  ],
  "error": null
}
``` 
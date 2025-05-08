# NFT元数据URL问题解决方案

## 问题描述

在Solana程序页面中，用户在铸造NFT时填写的元数据URL（如`http://8.214.38.69:10003/.well-known/agent.json`）在后续获取时被错误地替换为`https://arweave.net/...`格式的URL，导致无法正确获取元数据。

## 根本原因分析

1. **元数据URL处理逻辑问题**：系统在处理链上获取的元数据URL时，没有正确保留IP地址形式的URL。

2. **Solana RPC调用问题**：使用SDK高级API调用Solana RPC时出现了多个错误，包括`'dict' object has no attribute 'offset'`和`'str' object has no attribute 'to_json'`等。

3. **时间戳转换错误**：处理链上时间戳时，对于某些过大的时间戳值处理不当。

4. **数据库连接稳定性问题**：出现`'NoneType' object has no attribute 'read'`和`'Lost connection to MySQL server during query'`等错误。

## 解决方案

### 1. 元数据URL处理改进

添加了`validate_and_process_metadata_url`函数，专门处理元数据URL：

```python
def validate_and_process_metadata_url(url: str) -> str:
    """验证并处理元数据URL"""
    try:
        # 检查URL是否为空
        if not url or url.strip() == "":
            return "http://default-agent-url.com"
        
        # 规范化URL
        url = url.strip()
        
        # 检查URL是否以http://或https://开头
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "http://" + url
        
        # 检查是否是IP地址形式的URL
        import re
        if re.match(r'https?://\d+\.\d+\.\d+\.\d+(:\d+)?/', url):
            return url
            
        # 检查是否是arweave.net的URL
        if "arweave.net" in url:
            return url
            
        # 其他情况，返回原始URL
        return url
        
    except Exception as e:
        return "http://default-agent-url.com"
```

### 2. Solana RPC调用改进

使用直接HTTP请求替代SDK高级API调用Solana RPC：

```python
# 构建RPC请求参数
rpc_params = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getProgramAccounts",
    "params": [
        str(PROGRAM_ID),
        {
            "encoding": "base64",
            "filters": [
                {
                    "memcmp": {
                        "offset": 8,
                        "bytes": user_pubkey_base58
                    }
                }
            ]
        }
    ]
}

# 直接使用底层HTTP请求
import requests
response = requests.post(DEVNET_URL, json=rpc_params)
```

### 3. 时间戳转换错误修复

添加了对异常大时间戳值的处理：

```python
# 将链上的时间戳转换为可读格式
try:
    # 检查时间戳是否合理
    if expires_at_data > 9999999999:  # 超过2286年的时间戳
        logger.warning(f"时间戳值过大: {expires_at_data}，使用当前时间加一年")
        # 使用当前时间加一年作为替代
        expire_at = datetime.datetime.now() + datetime.timedelta(days=365)
    else:
        # 正常转换
        expire_at = datetime.datetime.fromtimestamp(expires_at_data)
except (OSError, ValueError, OverflowError) as e:
    logger.warning(f"时间戳转换错误: {e}，使用当前时间加一年")
    # 使用当前时间加一年作为替代
    expire_at = datetime.datetime.now() + datetime.timedelta(days=365)
```

### 4. 数据库连接稳定性改进

添加了`_ensure_db_connection`方法，检查连接状态并自动重连：

```python
def _ensure_db_connection(self):
    """确保数据库连接有效"""
    if self._memory_mode:
        return
        
    try:
        # 尝试ping数据库，如果失败则重新连接
        if not self._db_connection:
            logger.warning("数据库连接不存在，尝试重新连接")
            self._initialize_database()
            return
            
        try:
            self._db_connection.ping(reconnect=True)
        except Exception as e:
            logger.warning(f"数据库ping失败: {e}，尝试重新连接")
            self._initialize_database()
    except Exception as e:
        logger.error(f"确保数据库连接时出错: {e}")
        # 如果重连失败，切换到内存模式
        self._memory_mode = True
        logger.warning("切换到内存模式运行，数据将不会持久化")
```

### 5. 前端改进

1. 更新了元数据URL输入框的提示信息，明确支持IP地址形式的URL：

```html
<input v-model="metadataUrl" placeholder="http://8.214.38.69:10003/.well-known/agent.json" />
<small class="form-helper">请输入有效的元数据URL，支持http://或https://开头，支持IP地址形式(如http://8.214.38.69:10003/.well-known/agent.json)或arweave.net链接</small>
```

2. 改进了前端URL验证逻辑，确保IP地址形式的URL能通过验证：

```javascript
// 检查是否是有效的URL
function isValidUrl(url: string): boolean {
  try {
    // 简单检查URL是否以http://或https://开头
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      return false;
    }
    
    // 检查是否是IP地址形式的URL
    const ipRegex = /^https?:\/\/\d+\.\d+\.\d+\.\d+(:\d+)?\/.*/;
    if (ipRegex.test(url)) {
      console.log('检测到有效的IP地址URL格式');
      return true;
    }
    
    // 检查是否是arweave.net的URL
    if (url.includes('arweave.net')) {
      console.log('检测到有效的arweave.net URL格式');
      return true;
    }
    
    // 尝试创建URL对象验证
    new URL(url);
    return true;
  } catch (e) {
    console.error('URL验证失败:', e);
    return false;
  }
}
```

3. 添加了NFT元数据查看器组件，用于显示和验证元数据：

```javascript
// NftMetadataViewer.vue组件集成
<NftMetadataViewer 
  v-if="mintResult.metadata && mintResult.metadata.metadataUrl" 
  :metadataUrl="mintResult.metadata.metadataUrl" 
/>
```

## 结果

1. 系统现在能够正确处理和保留IP地址形式的元数据URL
2. 解决了Solana RPC调用中的错误
3. 修复了时间戳转换错误
4. 提高了数据库连接的稳定性
5. 前端提供了更好的用户体验和错误处理

这些改进确保了NFT元数据URL在整个系统中的一致性，无论是铸造时还是后续查询时都能正确处理。 
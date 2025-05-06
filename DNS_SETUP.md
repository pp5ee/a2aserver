# DNS配置指南

要将域名正确指向您的A2A服务器，请按照以下步骤配置DNS记录。

## 域名信息

- 前端域名: `agenticdao.net`
- API域名: `api.agenticdao.net`
- 服务器IP地址: `18.163.214.224`

## DNS记录配置

在您的域名注册商或DNS服务提供商处，添加以下DNS记录：

### A记录

| 主机记录 | 记录类型 | 值 | TTL |
|---------|--------|-----|-----|
| @ | A | 18.163.214.224 | 600 |
| api | A | 18.163.214.224 | 600 |

### CNAME记录 (可选，根据需要配置)

| 主机记录 | 记录类型 | 值 | TTL |
|---------|--------|-----|-----|
| www | CNAME | agenticdao.net | 600 |

### TXT记录 (用于域名验证，如有需要)

如果您的证书提供商要求验证域名所有权，您可能需要添加TXT记录。请按照证书提供商的具体指示操作。

## 验证DNS设置

配置DNS记录后，可以使用以下命令验证DNS解析是否正确：

```bash
# 检查主域名
dig agenticdao.net

# 检查API子域名
dig api.agenticdao.net
```

您应该看到A记录指向 `18.163.214.224`。

也可以使用在线DNS查询工具，如 [MxToolbox](https://mxtoolbox.com/DNSLookup.aspx) 或 [Google Admin Toolbox](https://toolbox.googleapps.com/apps/dig/).

## DNS传播

DNS更改可能需要一些时间才能在全球完全传播，通常需要几分钟到48小时不等。您可以使用 [whatsmydns.net](https://www.whatsmydns.net/) 检查DNS传播情况。

## 常见问题排查

### 域名无法解析

1. 确认DNS记录已正确添加
2. 检查TTL值，较小的TTL值可以加快DNS更新
3. 清除本地DNS缓存:
   - Windows: `ipconfig /flushdns`
   - macOS: `sudo killall -HUP mDNSResponder`
   - Linux: `sudo systemd-resolve --flush-caches` 或 `sudo service nscd restart`

### SSL证书问题

如果您遇到SSL证书错误，可能是因为证书的域名与实际访问的域名不匹配。确保：

1. 证书中包含了正确的域名（包括主域名和api子域名）
2. 证书未过期
3. 证书链完整

## 安全注意事项

为提高安全性，建议：

1. 启用DNSSEC，防止DNS欺骗攻击
2. 考虑使用DNS隐私保护服务
3. 确保域名注册商账户设置了强密码和两因素认证 
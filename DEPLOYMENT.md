# A2A服务部署指南

本文档提供了将A2A服务部署到生产环境的详细步骤，包括Nginx配置、SSL证书设置和前后端服务启动。

## 系统要求

- Ubuntu 20.04 LTS或更高版本
- Nginx 1.18或更高版本
- Python 3.8或更高版本
- Node.js 14或更高版本
- SSL证书文件

## 部署步骤

### 1. 准备工作

确保以下文件已经准备好：

- SSL证书文件:
  - `/home/ubuntu/agenticdao_ca.crt` (CA证书)
  - `/home/ubuntu/agenticdao.crt` (域名证书)
  - `/home/ubuntu/agenticdaonet.key` (私钥)

- A2A源代码:
  - 确保代码仓库已克隆到 `/home/ubuntu/Documents/GitHub/a2aserver` 目录

### 2. 运行部署脚本

按照以下步骤执行部署：

1. 下载部署脚本到服务器:
   ```
   wget -O setup_nginx.sh https://raw.githubusercontent.com/yourusername/a2aserver/main/setup_nginx.sh
   chmod +x setup_nginx.sh
   ```

2. 执行部署脚本:
   ```
   ./setup_nginx.sh
   ```

   此脚本会:
   - 安装并配置Nginx
   - 配置SSL证书
   - 创建前后端服务
   - 设置服务自启动

### 3. 构建和部署前端

执行以下命令构建并部署前端应用:
```
~/build_frontend.sh
```

### 4. 验证部署

完成上述步骤后，可以通过以下方式验证部署是否成功：

1. 访问前端应用: `https://agenticdao.net`
2. 检查后端服务状态: `sudo systemctl status a2a-backend.service`
3. 检查Nginx状态: `sudo systemctl status nginx`

## 配置文件说明

### Nginx配置

- 前端配置: `/etc/nginx/sites-available/agenticdao.net`
- 后端API配置: `/etc/nginx/sites-available/api.agenticdao.net`

### 后端服务配置

- 配置文件位置: `~/Documents/GitHub/a2aserver/server/config.json`
- 服务定义: `/etc/systemd/system/a2a-backend.service`

## 常见问题与解决方案

### 1. Nginx 启动失败

检查Nginx配置:
```
sudo nginx -t
```

查看Nginx错误日志:
```
sudo tail -f /var/log/nginx/error.log
```

### 2. 后端服务无法启动

检查服务状态和日志:
```
sudo systemctl status a2a-backend.service
sudo journalctl -u a2a-backend.service
```

### 3. 前端无法连接后端API

- 确认浏览器控制台中是否有CORS错误
- 检查前端构建时的API URL环境变量
- 确认Nginx CORS配置正确

### 4. SSL证书问题

使用以下命令检查证书有效性:
```
openssl verify -CAfile /home/ubuntu/agenticdao_ca.crt /home/ubuntu/agenticdao.crt
```

## 更新部署

### 更新前端

```
cd ~/Documents/GitHub/a2aserver
git pull
~/build_frontend.sh
```

### 更新后端

```
cd ~/Documents/GitHub/a2aserver
git pull
sudo systemctl restart a2a-backend.service
```

## 维护

### 查看日志

- Nginx 日志: 
  ```
  sudo tail -f /var/log/nginx/access.log
  sudo tail -f /var/log/nginx/error.log
  ```
  
- 后端服务日志:
  ```
  sudo journalctl -u a2a-backend.service -f
  ```

### 备份

建议定期备份以下内容:

- SSL证书
- 后端数据库 (如果适用)
- Nginx配置文件
- 前端构建文件 
#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}开始配置Nginx...${NC}"

# 安装必要的软件
echo -e "${YELLOW}安装必要软件...${NC}"
sudo apt-get update
sudo apt-get install -y nginx

# 创建Nginx配置文件
echo -e "${YELLOW}创建Nginx配置...${NC}"

# 创建主域名配置，包含前端和API路径
sudo cat > /etc/nginx/sites-available/agenticdao.net << 'EOF'
server {
    listen 80;
    server_name agenticdao.net;
    
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name agenticdao.net;

    ssl_certificate /home/ubuntu/agenticdao.crt;
    ssl_certificate_key /home/ubuntu/agenticdaonet.key;
    ssl_trusted_certificate /home/ubuntu/agenticdao_ca.crt;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-XSS-Protection "1; mode=block";
    
    # API反向代理配置 - 通过/beapi路径
    location /beapi/ {
        # 直接将请求转发到后端API，不修改路径
        proxy_pass http://localhost:12000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # CORS设置 - 允许来自任何源的请求（方便本地开发），生产环境中可以限制
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,X-Solana-PublicKey,X-Solana-Signature,X-Solana-Nonce' always;
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,X-Solana-PublicKey,X-Solana-Signature,X-Solana-Nonce' always;
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }
    }
    
    # 前端反向代理配置 - 使用固定端口3001
    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
    
    # 缓存静态资源
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://localhost:3001;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
EOF

# 启用站点配置
echo -e "${YELLOW}启用Nginx站点配置...${NC}"
sudo ln -sf /etc/nginx/sites-available/agenticdao.net /etc/nginx/sites-enabled/

# 移除可能存在的旧子域名配置
if [ -f /etc/nginx/sites-enabled/api.agenticdao.net ]; then
    echo -e "${YELLOW}移除旧的API子域名配置...${NC}"
    sudo rm /etc/nginx/sites-enabled/api.agenticdao.net
fi

# 检查Nginx配置
echo -e "${YELLOW}检查Nginx配置...${NC}"
sudo nginx -t

if [ $? -ne 0 ]; then
    echo -e "${RED}Nginx配置有误，请检查配置文件。${NC}"
    exit 1
fi

# 重启Nginx
echo -e "${YELLOW}重启Nginx...${NC}"
sudo systemctl restart nginx

echo -e "${GREEN}Nginx配置完成!${NC}"
echo -e "${GREEN}后端API服务应运行在: http://localhost:12000 (通过 https://agenticdao.net/beapi/ 访问)${NC}"
echo -e "${GREEN}前端服务应运行在: http://localhost:3001 (通过 https://agenticdao.net 访问)${NC}"
echo -e "${YELLOW}前端开发时可以直接使用 http://localhost:12000 访问API，生产环境使用 https://agenticdao.net/beapi/${NC}"
echo -e "${YELLOW}请确保手动启动前端和后端服务，并正确设置它们的端口。${NC}" 
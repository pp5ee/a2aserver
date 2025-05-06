#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}开始配置A2A服务...${NC}"

# 安装必要的软件
echo -e "${YELLOW}安装必要软件...${NC}"
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 创建Nginx配置文件
echo -e "${YELLOW}创建Nginx配置...${NC}"

# 创建API域名配置
sudo cat > /etc/nginx/sites-available/api.agenticdao.net << 'EOF'
server {
    listen 80;
    server_name api.agenticdao.net;
    
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name api.agenticdao.net;

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
    
    # API反向代理配置
    location / {
        proxy_pass http://localhost:12000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # CORS设置
        add_header 'Access-Control-Allow-Origin' 'https://agenticdao.net' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,X-Solana-PublicKey,X-Solana-Signature,X-Solana-Nonce' always;
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;
        
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' 'https://agenticdao.net' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,X-Solana-PublicKey,X-Solana-Signature,X-Solana-Nonce' always;
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }
    }
}
EOF

# 创建前端域名配置
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
    
    # 静态文件目录
    root /var/www/a2a-frontend;
    index index.html;
    
    # 前端路由处理
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # 缓存静态资源
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
EOF

# 启用站点配置
echo -e "${YELLOW}启用Nginx站点配置...${NC}"
sudo ln -sf /etc/nginx/sites-available/api.agenticdao.net /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/agenticdao.net /etc/nginx/sites-enabled/

# 创建静态文件目录
echo -e "${YELLOW}创建前端静态文件目录...${NC}"
sudo mkdir -p /var/www/a2a-frontend

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

# 复制后端配置文件
echo -e "${YELLOW}创建后端服务配置文件...${NC}"
cat > ~/server_config.json << 'EOF'
{
    "server": {
        "host": "0.0.0.0",
        "port": 12000,
        "debug": false,
        "allow_cors": true
    },
    "cors": {
        "allowed_origins": ["https://agenticdao.net"],
        "allowed_methods": ["GET", "POST", "OPTIONS"],
        "allowed_headers": [
            "Content-Type", 
            "Authorization", 
            "X-Solana-PublicKey", 
            "X-Solana-Signature", 
            "X-Solana-Nonce"
        ]
    },
    "api": {
        "base_url": "https://api.agenticdao.net"
    }
}
EOF

# 复制配置文件到后端目录
echo -e "${YELLOW}复制配置文件到后端目录...${NC}"
cp ~/server_config.json ~/Documents/GitHub/a2aserver/server/config.json

# 创建后端启动脚本
echo -e "${YELLOW}创建后端启动脚本...${NC}"
cat > ~/start_backend.sh << 'EOF'
#!/bin/bash

cd ~/Documents/GitHub/a2aserver/server
python3 main.py --config config.json
EOF

chmod +x ~/start_backend.sh

# 创建前端构建和部署脚本
echo -e "${YELLOW}创建前端构建和部署脚本...${NC}"
cat > ~/build_frontend.sh << 'EOF'
#!/bin/bash

# 切换到前端目录
cd ~/Documents/GitHub/a2aserver/server/vue-frontend

# 安装依赖
npm install

# 设置环境变量，确保API URL正确
export VUE_APP_API_URL=https://api.agenticdao.net

# 构建前端
npm run build

# 部署到Nginx目录
sudo cp -r dist/* /var/www/a2a-frontend/
sudo chown -R www-data:www-data /var/www/a2a-frontend/

echo "前端构建和部署完成!"
EOF

chmod +x ~/build_frontend.sh

# 创建服务自启动配置
echo -e "${YELLOW}创建系统服务配置...${NC}"

# 后端服务
sudo cat > /etc/systemd/system/a2a-backend.service << 'EOF'
[Unit]
Description=A2A Backend Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Documents/GitHub/a2aserver/server
ExecStart=/usr/bin/python3 /home/ubuntu/Documents/GitHub/a2aserver/server/main.py --config config.json
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

# 重载systemd配置
sudo systemctl daemon-reload

# 启用并启动服务
echo -e "${YELLOW}启用并启动后端服务...${NC}"
sudo systemctl enable a2a-backend.service
sudo systemctl start a2a-backend.service

echo -e "${GREEN}配置完成!${NC}"
echo -e "${GREEN}后端服务运行在: https://api.agenticdao.net${NC}"
echo -e "${GREEN}前端访问地址: https://agenticdao.net${NC}"
echo -e "${YELLOW}请运行 ~/build_frontend.sh 来构建并部署前端${NC}"
echo -e "${YELLOW}服务状态可以通过 'sudo systemctl status a2a-backend.service' 查看${NC}" 
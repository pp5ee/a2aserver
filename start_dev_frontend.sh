#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}启动前端开发服务器...${NC}"

# 切换到前端目录
cd ~/Documents/GitHub/a2aserver/server/vue-frontend
# 对于Ubuntu机器上的不同路径
if [ ! -d ~/Documents/GitHub/a2aserver/server/vue-frontend ]; then
    cd ~/repo_builder/a2aserver/server/vue-frontend
fi

# 设置环境变量
export HOST=0.0.0.0
export PORT=3001

# 创建临时的.env.development.local文件
echo -e "${YELLOW}创建临时环境配置文件...${NC}"
cat > .env.development.local << EOF
VUE_APP_HOST=0.0.0.0
VUE_APP_PORT=3001
VUE_APP_DISABLE_HOST_CHECK=true
EOF

echo -e "${YELLOW}开发服务器将在 http://0.0.0.0:3001 上启动${NC}"
echo -e "${YELLOW}可以通过 http://localhost:3001 或局域网IP访问${NC}"
echo -e "${YELLOW}API服务将自动连接到 http://localhost:12000${NC}"

# 启动开发服务器，使用兼容新版本的参数
echo -e "${GREEN}启动Vue开发服务器...${NC}"
npm run serve -- --port 3001 --host 0.0.0.0 
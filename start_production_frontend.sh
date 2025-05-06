#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}启动生产环境前端服务...${NC}"

# 切换到前端目录
cd ~/Documents/GitHub/a2aserver/server/vue-frontend

# 设置环境变量
export NODE_ENV=production
export HOST=0.0.0.0
export PORT=3001
# 禁用主机检查
export VUE_CLI_SERVICE_CONFIG_DISABLE_HOST_CHECK=true

# 检查是否有构建好的dist目录
if [ ! -d "dist" ]; then
    echo -e "${YELLOW}未检测到构建目录，正在构建前端...${NC}"
    # 构建前端
    npm run build
fi

echo -e "${YELLOW}前端服务将在 http://0.0.0.0:3001 上启动${NC}"
echo -e "${YELLOW}可以通过 https://agenticdao.net 访问${NC}"

# 使用serve工具启动静态文件服务
if ! command -v serve &> /dev/null; then
    echo -e "${YELLOW}安装serve工具...${NC}"
    npm install -g serve
fi

# 启动生产服务器
echo -e "${GREEN}启动静态文件服务器...${NC}"
serve -s dist -l 3001 --no-clipboard 
#!/bin/bash
set -e

# 安装依赖（优先使用pyproject.toml）
if [ -f "pyproject.toml" ]; then
    echo "检测到 pyproject.toml，使用 uv 安装依赖..."
    uv pip install -e .
elif [ -f "requirements.txt" ]; then
    echo "检测到 requirements.txt，使用 uv 安装依赖..."
    uv pip install -r requirements.txt
fi

# 启动项目
echo "正在启动项目..."
uv run main.py 
#!/bin/bash
# Telegram 监听器启动脚本

cd "$(dirname "$0")/stake" || exit 1

# 激活虚拟环境（如果使用）
if [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
fi

# 设置平台环境变量（Linux）
export STAKE_PLATFORM=linux

# 启动监听器
python listener.py

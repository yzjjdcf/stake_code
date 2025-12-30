#!/bin/bash
# Django 服务启动脚本

cd "$(dirname "$0")/stake" || exit 1

# 激活虚拟环境（如果使用）
if [ -f "../venv/bin/activate" ]; then
    source ../venv/bin/activate
fi

# 设置平台环境变量（Linux）
export STAKE_PLATFORM=linux

# 运行数据库迁移
python manage.py migrate

# 启动Django开发服务器
python manage.py runserver 0.0.0.0:8000

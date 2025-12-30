#!/bin/bash
# 添加所有有用文件到 git

# 核心配置文件
git add requirements.txt
git add .gitignore
git add config.py
git add manage.py

# Django 项目文件
git add manager/
git add serverbot/

# 核心脚本
git add listener.py
git add worker.py
git add check_config.py
git add cleanup_duplicates.py

# 启动脚本
git add start_django.sh
git add start_listener.sh

# 文档
git add README_LINUX.md
git add 推送记录功能完善说明.md
git add 修复迁移说明.md

echo "✅ 所有文件已添加！"
echo "现在可以运行: git commit -m '你的提交信息'"


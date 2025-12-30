#!/usr/bin/env python
"""
从 JSON 文件导入数据库
使用方法: python import_database.py [JSON文件路径]
"""
import os
import sys
import django

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

from django.core.management import call_command

if len(sys.argv) < 2:
    print("❌ 请指定要导入的 JSON 文件")
    print("   使用方法: python import_database.py database_backup.json")
    sys.exit(1)

input_file = sys.argv[1]

if not os.path.exists(input_file):
    print(f"❌ 文件不存在: {input_file}")
    sys.exit(1)

print(f"📥 开始从 {input_file} 导入数据库...")
print("⚠️  警告: 这将覆盖现有数据！")

# 确认
response = input("是否继续？(yes/no): ")
if response.lower() not in ['yes', 'y']:
    print("❌ 已取消导入")
    sys.exit(0)

try:
    # 先清空现有数据（可选）
    # call_command('flush', '--noinput')  # 取消注释以清空数据库
    
    # 导入数据
    with open(input_file, 'r', encoding='utf-8') as f:
        call_command('loaddata', input_file)
    
    print(f"✅ 导入成功！")
    print(f"   已从 {input_file} 恢复数据")
    
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


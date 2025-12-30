#!/usr/bin/env python
"""
导出数据库到 JSON 文件
使用方法: python export_database.py [输出文件名]
"""
import os
import sys
import django
from datetime import datetime

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

from django.core.management import call_command
from django.core.serializers import serialize

# 默认输出文件名
default_filename = f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

if len(sys.argv) > 1:
    output_file = sys.argv[1]
else:
    output_file = default_filename

print(f"📦 开始导出数据库到: {output_file}")

try:
    # 导出所有应用的数据
    with open(output_file, 'w', encoding='utf-8') as f:
        call_command('dumpdata', 
                    'serverbot',  # 只导出 serverbot 应用的数据
                    'auth.user',  # 导出用户数据（如果有）
                    'auth.group', # 导出用户组（如果有）
                    natural_foreign=True,
                    natural_primary=True,
                    indent=2,
                    stdout=f)
    
    file_size = os.path.getsize(output_file) / 1024  # KB
    print(f"✅ 导出成功！")
    print(f"   文件: {output_file}")
    print(f"   大小: {file_size:.2f} KB")
    print(f"\n💡 导入方法: python import_database.py {output_file}")
    
except Exception as e:
    print(f"❌ 导出失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


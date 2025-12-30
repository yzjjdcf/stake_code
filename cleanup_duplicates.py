#!/usr/bin/env python
"""
临时脚本：清理重复的 code 记录
在运行迁移之前执行此脚本
"""
import os
import sys
import django

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stake.settings')
django.setup()

from serverbot.models import CodeRecord, ClaimRecord
from django.db.models import Count

def cleanup_duplicates():
    """清理重复的 code 记录"""
    print("开始清理重复的 code 记录...")
    
    # 查找所有重复的 code
    duplicates = CodeRecord.objects.values('code').annotate(
        count=Count('id')
    ).filter(count__gt=1)
    
    total_duplicates = duplicates.count()
    print(f"找到 {total_duplicates} 个重复的 code")
    
    if total_duplicates == 0:
        print("✅ 没有重复记录，无需清理")
        return
    
    cleaned = 0
    for dup in duplicates:
        code = dup['code']
        # 获取所有相同 code 的记录，按创建时间排序
        records = list(CodeRecord.objects.filter(code=code).order_by('created_at'))
        
        if len(records) > 1:
            first_record = records[0]
            deleted_count = 0
            
            # 将其他记录的 ClaimRecord 关联到第一个记录
            updated_claims = 0
            for record in records[1:]:
                # 更新关联的 ClaimRecord
                updated = ClaimRecord.objects.filter(code_record=record).update(
                    code_record=first_record
                )
                updated_claims += updated
                # 删除重复记录
                record.delete()
            
            print(f"✅ 清理代码: {code} - 保留 ID={first_record.id}, 删除 {len(records)-1} 条记录, 更新 {updated_claims} 条 ClaimRecord")
            cleaned += 1
    
    print(f"\n✅ 清理完成！共清理 {cleaned} 个重复的 code")

if __name__ == '__main__':
    try:
        cleanup_duplicates()
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


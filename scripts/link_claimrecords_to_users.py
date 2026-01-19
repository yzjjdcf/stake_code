#!/usr/bin/env python
"""
关联 ClaimRecord 到用户脚本
- 老数据：通过 user_flag 匹配 UserProfile.user_flag，关联到 User
- 新数据：后续可以在 ClaimRecord 中添加 user 字段直接关联
"""
import os
import sys
import django

# 添加项目路径（参考 manage.py 的逻辑）
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
core_dir = os.path.join(project_root, 'core')

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if core_dir not in sys.path:
    sys.path.insert(0, core_dir)

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manager.settings')
django.setup()

from serverbot.models import ClaimRecord
from frontend.models import UserProfile
from django.contrib.auth.models import User
from django.db import transaction


def link_claimrecords_to_users():
    """通过 user_flag 将 ClaimRecord 关联到 User"""
    
    # 获取所有有 user_flag 的 ClaimRecord（老数据）
    records_with_flag = ClaimRecord.objects.filter(user_flag__isnull=False).exclude(user_flag='')
    
    print(f"找到 {records_with_flag.count()} 条有 user_flag 的记录")
    print()
    
    # 统计信息
    matched_count = 0
    unmatched_count = 0
    unmatched_flags = set()
    
    # 创建 user_flag -> User 的映射（通过 UserProfile）
    user_flag_to_user = {}
    profiles = UserProfile.objects.filter(user_flag__isnull=False).exclude(user_flag='')
    for profile in profiles:
        if profile.user_flag:
            user_flag_to_user[profile.user_flag] = profile.user
            print(f"✓ 找到用户映射: user_flag='{profile.user_flag}' -> User '{profile.user.username}' (ID: {profile.user.id})")
    
    if not user_flag_to_user:
        print("⚠ 警告: 没有找到任何 UserProfile 记录，请先为用户设置 user_flag")
        return
    
    print()
    print(f"共找到 {len(user_flag_to_user)} 个用户映射")
    print("=" * 60)
    print()
    
    # 显示未匹配的记录
    unmatched_records = []
    
    for record in records_with_flag:
        user_flag = record.user_flag
        if user_flag in user_flag_to_user:
            matched_count += 1
        else:
            unmatched_count += 1
            unmatched_flags.add(user_flag)
            unmatched_records.append(record)
    
    print(f"匹配统计:")
    print(f"  - 可匹配: {matched_count} 条")
    print(f"  - 未匹配: {unmatched_count} 条")
    print()
    
    if unmatched_count > 0:
        print(f"未匹配的 user_flag 值 ({len(unmatched_flags)} 个):")
        for flag in sorted(unmatched_flags):
            count = ClaimRecord.objects.filter(user_flag=flag).count()
            print(f"  - '{flag}': {count} 条记录")
        print()
    
    # 确认是否继续
    if matched_count == 0:
        print("没有可匹配的记录，退出")
        return
    
    # 检查 ClaimRecord 是否有 user 字段
    has_user_field = hasattr(ClaimRecord, 'user')
    
    if not has_user_field:
        print("=" * 60)
        print("⚠ 注意: ClaimRecord 模型中没有 user 字段")
        print("需要先在模型中添加 user 字段，然后运行迁移，再运行此脚本")
        print("=" * 60)
        return
    
    # 显示匹配预览
    print("匹配预览（前10条）:")
    preview_count = 0
    for record in records_with_flag[:10]:
        user_flag = record.user_flag
        if user_flag in user_flag_to_user:
            user = user_flag_to_user[user_flag]
            current_user = record.user.username if record.user else '(未关联)'
            print(f"  ClaimRecord ID {record.id}: user_flag='{user_flag}' -> User '{user.username}' (当前: {current_user})")
            preview_count += 1
            if preview_count >= 10:
                break
    
    print()
    
    # 确认是否执行关联
    print(f"将关联 {matched_count} 条记录")
    if unmatched_count > 0:
        print(f"（{unmatched_count} 条记录无法匹配，将保持 user=None）")
    print()
    
    # 执行关联
    updated_count = 0
    with transaction.atomic():
        for record in records_with_flag:
            user_flag = record.user_flag
            if user_flag in user_flag_to_user:
                user = user_flag_to_user[user_flag]
                # 只有当 user 字段为空或需要更新时才更新
                if record.user != user:
                    record.user = user
                    record.save(update_fields=['user'])
                    updated_count += 1
    
    print(f"✅ 成功关联 {updated_count} 条记录")
    
    # 显示关联后的统计
    print()
    print("关联后统计:")
    for user_flag, user in user_flag_to_user.items():
        linked_count = ClaimRecord.objects.filter(user=user).count()
        print(f"  User '{user.username}' (user_flag='{user_flag}'): {linked_count} 条记录")


if __name__ == '__main__':
    print("=" * 60)
    print("关联 ClaimRecord 到用户脚本")
    print("=" * 60)
    print()
    
    link_claimrecords_to_users()


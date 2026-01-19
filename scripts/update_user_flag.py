#!/usr/bin/env python
"""
更新用户标识脚本
将指定用户的 StakeAccount 记录的 user_flag 设置为指定值
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

from frontend.models import UserProfile
from django.contrib.auth.models import User


def update_user_flag(username, user_flag):
    """
    更新指定用户的 user_flag（在 UserProfile 中）
    
    Args:
        username: Django User 的 username
        user_flag: 要设置的 user_flag 值
    """
    try:
        # 查找用户
        user = User.objects.get(username=username)
        print(f"✓ 找到用户: {user.username} (ID: {user.id})")
        
        # 获取或创建 UserProfile
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        if created:
            print(f"✓ 为用户创建了 UserProfile 记录")
        else:
            print(f"✓ 找到用户的 UserProfile 记录")
            print(f"  更新前的 user_flag: {profile.user_flag or '(空)'}")
        
        # 更新 user_flag
        profile.user_flag = user_flag
        profile.save()
        
        print(f"\n✓ 成功更新 user_flag")
        print(f"  更新后的 user_flag: {profile.user_flag}")
        print(f"\n✅ 完成！用户 {username} 的 user_flag 已设置为: {user_flag}")
        
    except User.DoesNotExist:
        print(f"❌ 错误: 用户 '{username}' 不存在")
        print("\n可用的用户列表:")
        users = User.objects.all()
        for u in users:
            print(f"  - {u.username}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    # 设置要更新的用户名和 user_flag
    username = 'user_yzjjdcf'
    user_flag = 'yzjjdcf'
    
    print("=" * 60)
    print("更新用户标识脚本")
    print("=" * 60)
    print(f"用户名: {username}")
    print(f"用户标识: {user_flag}")
    print("=" * 60)
    print()
    
    update_user_flag(username, user_flag)


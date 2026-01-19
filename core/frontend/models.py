from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """用户扩展信息（关联到 Django User 表）"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="用户", related_name='profile')
    user_flag = models.CharField(max_length=100, null=True, blank=True, verbose_name="用户标识", help_text="用于关联老数据的用户标识（对应 ClaimRecord.user_flag）")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    
    class Meta:
        verbose_name = "用户扩展信息"
        verbose_name_plural = "用户扩展信息"
    
    def __str__(self):
        return f"{self.user.username}'s Profile (user_flag: {self.user_flag or '未设置'})"


class StakeAccount(models.Model):
    """Stake 账号模型（用户在前台创建的账号）"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="用户", related_name='stake_accounts')
    stake_account_id = models.CharField(max_length=100, verbose_name="Stake 账号ID", help_text="用户输入的 Stake 账号用户名或ID")
    is_active = models.BooleanField(default=True, verbose_name="是否激活", help_text="激活的账号才会被脚本使用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    
    class Meta:
        verbose_name = "Stake账号"
        verbose_name_plural = "Stake账号"
        ordering = ['-created_at']
        unique_together = [['user', 'stake_account_id']]  # 同一用户不能添加重复的账号ID
    
    def __str__(self):
        return f"{self.user.username} - {self.stake_account_id} ({'激活' if self.is_active else '停用'})"

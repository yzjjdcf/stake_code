from django.db import models


class ClaimRecord(models.Model):
    """记录每个账号的抢码结果"""
    user_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="用户标识", help_text="用户唯一标识符，用于区分不同使用者（一个用户可以有多个 Stake 账号）", db_index=True)
    username = models.CharField(max_length=100, null=True, blank=True, verbose_name="用户名", help_text="Stake 账号用户名字符串，用于 WebSocket 领取记录")
    code = models.CharField(max_length=100, verbose_name="红包代码", db_index=True)
    
    # 状态：领取接口返回的所有状态
    STATUS_CHOICES = [
        ('claim_success', '✅ 领取成功'),
        ('claim_failure', '❌ 领取失败'),
        ('inactive', '⌛ 次数领取完'),
        ('not_found', '❌ 找不到'),
        ('session_expired', '⚠️ 会话已过期'),
        ('already_claimed', '🔁 已领过'),
        ('weekly_wager_requirement', '📋 流水不够'),
        ('drop_unavailable', '⏰ 7天内不能领代码'),
        ('error_403', '⚠️ 403错误'),
        ('error', '❓ 其他错误'),
    ]
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, verbose_name="状态")
    
    bonus_value = models.CharField(max_length=50, null=True, blank=True, verbose_name="奖金金额（显示用）", help_text="格式：金额 货币，如 '1.5 USDT'")
    bonus_amount = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, verbose_name="奖金数值", help_text="纯数字，便于计算")
    bonus_currency = models.CharField(max_length=10, null=True, blank=True, verbose_name="货币类型", help_text="如：USDT, BTC, ETH")
    response_time_ms = models.IntegerField(null=True, verbose_name="响应时间(ms)")
    is_retry = models.BooleanField(default=False, verbose_name="是否重试")
    error_message = models.TextField(null=True, blank=True, verbose_name="错误信息")
    query_response_body = models.TextField(null=True, blank=True, verbose_name="查询接口响应体", help_text="记录查询代码是否可用的API响应内容（第一步接口）")
    claim_response_body = models.TextField(null=True, blank=True, verbose_name="领取接口响应体", help_text="记录领取代码的API响应内容（第二步接口，仅当代码可用时才有）")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    
    class Meta:
        verbose_name = "领取明细"
        verbose_name_plural = "领取明细"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['user_id', 'created_at']),  # 用于按用户查询
        ]
    
    def __str__(self):
        status_display = dict(self.STATUS_CHOICES).get(self.status, self.status)
        user_display = self.username or "未知用户"
        return f"{user_display} - {self.code} ({status_display})"

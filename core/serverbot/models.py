from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
import threading



class ProxyPool(models.Model):
    address = models.CharField("代理地址", max_length=255)
    is_active = models.BooleanField("是否可用", default=True)
    location = models.CharField(max_length=100, null=True, blank=True)  # 新增：存储归属地
    def __str__(self):
        return self.address


class StakeAccount(models.Model):
    # 自动生成的 ID
    id = models.AutoField(primary_key=True)
    username = models.CharField("Stake用户名", max_length=100, default='')
    token = models.TextField("Stake令牌", default='')

    # 关联代理池
    proxy = models.ForeignKey(
        ProxyPool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="关联代理"
    )

    cookies_json = models.TextField("Cookies 数据", blank=True, null=True)
    user_agent = models.TextField("User-Agent", blank=True, null=True)
    # 修改这里：去掉 auto_now=True，增加 null=True 和 blank=True
    # 1. 触发过盾的时间 (脚本准备开始过盾)
    bypass_trigger_time = models.DateTimeField(
        "触发过盾时间",
        null=True,
        blank=True,
        help_text="脚本开始尝试过盾的时间点"
    )

    # 2. 写入过盾的时间 (过盾成功并成功保存 Cookie)
    bypass_success_time = models.DateTimeField(
        "写入过盾时间",
        null=True,
        blank=True,
        help_text="过盾成功且数据写入数据库的时间点"
    )
    # 添加此行：默认值为 True (激活)
    is_active = models.BooleanField(default=True, verbose_name="是否激活")

    def __str__(self):
        return f"{self.username} (ID: {self.id})"


@receiver(post_save, sender=StakeAccount)
def trigger_warmup_on_new_user(sender, instance, created, **kwargs):
    """创建用户时：优先分配空闲代理，若无空闲则复用已有代理"""
    if created:
        # 1. 这里使用 Django 默认的反向查询字段名 'stakeaccount'
        proxy = ProxyPool.objects.filter(is_active=True, stakeaccount__isnull=True).first()
        is_reuse = False

        # 2. 如果没找到，则随机选一个
        if not proxy:
            proxy = ProxyPool.objects.filter(is_active=True).order_by('?').first()
            is_reuse = True

        if proxy:
            # 使用 update 避免递归触发 save 信号
            StakeAccount.objects.filter(pk=instance.pk).update(proxy=proxy)

            # 记录日志
            mode_str = "(复用模式)" if is_reuse else "(独占模式)"
            print(f"[{instance.username}] 分配代理: {proxy.address} {mode_str}")

            # 为了让后续线程拿到最新的 proxy 对象
            instance.proxy = proxy
        else:
            print(f"[{instance.username}] 错误：代理池完全为空")

        # 3. 开启后台线程
        from .utils import run_pre_logic
        import threading
        threading.Thread(target=run_pre_logic, args=(instance,), daemon=True).start()


class CodeRecord(models.Model):
    """记录推送到全员的代码"""
    code = models.CharField(max_length=100, verbose_name="红包代码", unique=True, db_index=True)
    
    # 代码状态
    STATUS_CHOICES = [
        ('unknown', '未知'),
        ('valid', '有效'),
        ('invalid', '无效'),
        ('expired', '已过期'),
        ('claimed', '已领取完'),
    ]
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='unknown',
        verbose_name="代码状态"
    )
    
    # 实际价值（由第一个成功获取的账号回填）
    actual_value = models.CharField(max_length=50, null=True, blank=True, verbose_name="实际价值")
    
    # 统计信息
    total_attempts = models.IntegerField(default=0, verbose_name="总尝试次数")
    success_count = models.IntegerField(default=0, verbose_name="成功次数")
    failure_count = models.IntegerField(default=0, verbose_name="失败次数")
    error_403_count = models.IntegerField(default=0, verbose_name="403错误次数")
    
    is_timeout_trigger = models.BooleanField(default=False, verbose_name="是否超时盲冲")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    
    class Meta:
        verbose_name = "推送记录"
        verbose_name_plural = "推送记录"
        ordering = ['-created_at']
    
    def __str__(self):
        status_display = dict(self.STATUS_CHOICES).get(self.status, self.status)
        value_str = f" - {self.actual_value}" if self.actual_value else ""
        return f"{self.code} ({status_display}){value_str}"

class ClaimRecord(models.Model):
    """记录每个账号的抢码结果"""
    account = models.ForeignKey(StakeAccount, on_delete=models.CASCADE, verbose_name="账号")
    code_record = models.ForeignKey(CodeRecord, on_delete=models.SET_NULL, null=True, related_name='claim_records', verbose_name="代码记录")
    code = models.CharField(max_length=100, verbose_name="红包代码", db_index=True)
    
    # 状态：success(成功), failure(失败), error_403(403错误), not_found(找不到), inactive(限额已满), already_claimed(已领过)
    STATUS_CHOICES = [
        ('success', '✅ 成功'),
        ('failure', '❌ 失败'),
        ('error_403', '⚠️ 403错误'),
        ('not_found', '❌ 找不到'),
        ('inactive', '⌛ 限额已满'),
        ('already_claimed', '🔁 已领过'),
        ('error', '❓ 其他错误'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="状态")
    
    bonus_value = models.CharField(max_length=50, null=True, blank=True, verbose_name="奖金金额")
    response_time_ms = models.IntegerField(null=True, verbose_name="响应时间(ms)")
    is_retry = models.BooleanField(default=False, verbose_name="是否重试")
    error_message = models.TextField(null=True, blank=True, verbose_name="错误信息")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    
    class Meta:
        verbose_name = "领取明细"
        verbose_name_plural = "领取明细"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        status_display = dict(self.STATUS_CHOICES).get(self.status, self.status)
        return f"{self.account.username} - {self.code} ({status_display})"

# Generated manually for updating CodeRecord and ClaimRecord models

from django.db import migrations, models


def cleanup_duplicate_codes(apps, schema_editor):
    """清理重复的 code 记录，保留最早的记录"""
    CodeRecord = apps.get_model('serverbot', 'CodeRecord')
    ClaimRecord = apps.get_model('serverbot', 'ClaimRecord')
    
    # 查找所有重复的 code
    from django.db.models import Count
    duplicates = CodeRecord.objects.values('code').annotate(
        count=Count('id')
    ).filter(count__gt=1)
    
    for dup in duplicates:
        code = dup['code']
        # 获取所有相同 code 的记录，按创建时间排序
        records = list(CodeRecord.objects.filter(code=code).order_by('created_at'))
        
        # 保留第一个（最早的），删除其他的
        if len(records) > 1:
            first_record = records[0]
            
            # 将其他记录的 ClaimRecord 关联到第一个记录
            for record in records[1:]:
                # 更新关联的 ClaimRecord
                ClaimRecord.objects.filter(code_record_id=record.id).update(
                    code_record_id=first_record.id
                )
                # 删除重复记录
                record.delete()
            
            print(f"清理重复代码: {code}, 保留最早记录 ID={first_record.id}")


def reverse_cleanup(apps, schema_editor):
    """反向操作：无法恢复已删除的记录"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('serverbot', '0007_remove_stakeaccount_last_updated_and_more'),
    ]

    operations = [
        # 第一步：清理重复数据
        migrations.RunPython(cleanup_duplicate_codes, reverse_cleanup),
        # 第二步：添加字段和约束
        # 更新 CodeRecord 模型
        migrations.AddField(
            model_name='coderecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('unknown', '未知'),
                    ('valid', '有效'),
                    ('invalid', '无效'),
                    ('expired', '已过期'),
                    ('claimed', '已领取完'),
                ],
                default='unknown',
                max_length=20,
                verbose_name='代码状态'
            ),
        ),
        migrations.AddField(
            model_name='coderecord',
            name='total_attempts',
            field=models.IntegerField(default=0, verbose_name='总尝试次数'),
        ),
        migrations.AddField(
            model_name='coderecord',
            name='success_count',
            field=models.IntegerField(default=0, verbose_name='成功次数'),
        ),
        migrations.AddField(
            model_name='coderecord',
            name='failure_count',
            field=models.IntegerField(default=0, verbose_name='失败次数'),
        ),
        migrations.AddField(
            model_name='coderecord',
            name='error_403_count',
            field=models.IntegerField(default=0, verbose_name='403错误次数'),
        ),
        migrations.AddField(
            model_name='coderecord',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='更新时间'),
        ),
        migrations.AlterField(
            model_name='coderecord',
            name='code',
            field=models.CharField(db_index=True, max_length=100, unique=True, verbose_name='红包代码'),
        ),
        migrations.AlterField(
            model_name='coderecord',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='创建时间'),
        ),
        
        # 更新 ClaimRecord 模型
        migrations.AlterField(
            model_name='claimrecord',
            name='code',
            field=models.CharField(db_index=True, max_length=100, verbose_name='红包代码'),
        ),
        migrations.AlterField(
            model_name='claimrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('success', '✅ 成功'),
                    ('failure', '❌ 失败'),
                    ('error_403', '⚠️ 403错误'),
                    ('not_found', '❌ 找不到'),
                    ('inactive', '⌛ 限额已满'),
                    ('already_claimed', '🔁 已领过'),
                    ('error', '❓ 其他错误'),
                ],
                max_length=20,
                verbose_name='状态'
            ),
        ),
        migrations.AlterField(
            model_name='claimrecord',
            name='bonus_value',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='奖金金额'),
        ),
        migrations.AlterField(
            model_name='claimrecord',
            name='response_time_ms',
            field=models.IntegerField(null=True, verbose_name='响应时间(ms)'),
        ),
        migrations.AlterField(
            model_name='claimrecord',
            name='is_retry',
            field=models.BooleanField(default=False, verbose_name='是否重试'),
        ),
        migrations.AlterField(
            model_name='claimrecord',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='创建时间'),
        ),
        migrations.AddField(
            model_name='claimrecord',
            name='error_message',
            field=models.TextField(blank=True, null=True, verbose_name='错误信息'),
        ),
        migrations.AlterField(
            model_name='claimrecord',
            name='account',
            field=models.ForeignKey(on_delete=models.CASCADE, to='serverbot.stakeaccount', verbose_name='账号'),
        ),
        migrations.AlterField(
            model_name='claimrecord',
            name='code_record',
            field=models.ForeignKey(
                null=True,
                on_delete=models.SET_NULL,
                related_name='claim_records',
                to='serverbot.coderecord',
                verbose_name='代码记录'
            ),
        ),
        # 添加索引（Django会自动生成索引名称）
        migrations.AddIndex(
            model_name='claimrecord',
            index=models.Index(fields=['code', 'status'], name='serverbot_claim_code_status_idx'),
        ),
        migrations.AddIndex(
            model_name='claimrecord',
            index=models.Index(fields=['created_at'], name='serverbot_claim_created_idx'),
        ),
    ]


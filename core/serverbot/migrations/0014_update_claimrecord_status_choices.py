# Generated manually on 2026-01-06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('serverbot', '0013_add_separate_response_body_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='claimrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('claim_success', '✅ 领取成功'),
                    ('claim_failure', '❌ 领取失败'),
                    ('inactive', '⌛ 次数领取完'),
                    ('not_found', '❌ 找不到'),
                    ('session_expired', '⚠️ 会话已过期'),
                    ('already_claimed', '🔁 已领过'),
                    ('weekly_wager_requirement', '📋 流水不够'),
                    ('error_403', '⚠️ 403错误'),
                    ('error', '❓ 其他错误'),
                ],
                max_length=30,
                verbose_name='状态'
            ),
        ),
    ]


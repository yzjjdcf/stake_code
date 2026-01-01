# Generated manually on 2026-01-01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('serverbot', '0011_add_response_body_to_claimrecord'),
    ]

    operations = [
        migrations.AlterField(
            model_name='claimrecord',
            name='status',
            field=models.CharField(choices=[('success', '✅ 成功'), ('failure', '❌ 失败'), ('error_403', '⚠️ 403错误'), ('not_found', '❌ 找不到'), ('inactive', '⌛ code次数用尽'), ('weekly_wager_requirement', '📋 需要周投注要求'), ('already_claimed', '🔁 已领过'), ('error', '❓ 其他错误')], max_length=30, verbose_name='状态'),
        ),
    ]


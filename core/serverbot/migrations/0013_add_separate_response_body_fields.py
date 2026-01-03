# Generated manually on 2026-01-01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('serverbot', '0012_update_claimrecord_status_max_length'),
    ]

    operations = [
        # 添加新字段
        migrations.AddField(
            model_name='claimrecord',
            name='query_response_body',
            field=models.TextField(blank=True, help_text='记录查询代码是否可用的API响应内容（第一步接口）', null=True, verbose_name='查询接口响应体'),
        ),
        migrations.AddField(
            model_name='claimrecord',
            name='claim_response_body',
            field=models.TextField(blank=True, help_text='记录领取代码的API响应内容（第二步接口，仅当代码可用时才有）', null=True, verbose_name='领取接口响应体'),
        ),
        # 保留旧字段 response_body 用于兼容（可选：如果确定不需要，可以删除）
        # 如果需要删除旧字段，可以添加：
        # migrations.RemoveField(
        #     model_name='claimrecord',
        #     name='response_body',
        # ),
    ]


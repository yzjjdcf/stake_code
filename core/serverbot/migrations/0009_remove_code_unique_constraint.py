# Generated manually for removing unique constraint on CodeRecord.code
# 允许相同代码多次推送，每次推送都是唯一记录（以时间先后为准）

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('serverbot', '0008_update_code_record_fields'),
    ]

    operations = [
        # 移除 code 字段的 unique 约束
        migrations.AlterField(
            model_name='coderecord',
            name='code',
            field=models.CharField(max_length=100, verbose_name='红包代码', db_index=True),
        ),
    ]


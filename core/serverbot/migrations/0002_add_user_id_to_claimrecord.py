# Generated migration: Add user_id field to ClaimRecord
# 注意：如果这是第一次迁移，请先运行 python manage.py makemigrations
# 然后运行 python manage.py migrate

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('serverbot', '0001_initial'),  # 依赖于初始迁移
    ]

    operations = [
        migrations.AddField(
            model_name='claimrecord',
            name='user_id',
            field=models.CharField(blank=True, db_index=True, help_text='用户唯一标识符，用于区分不同使用者（一个用户可以有多个 Stake 账号）', max_length=100, null=True, verbose_name='用户标识'),
        ),
        migrations.AddIndex(
            model_name='claimrecord',
            index=models.Index(fields=['user_id', 'created_at'], name='serverbot_c_user_id_created_idx'),
        ),
    ]


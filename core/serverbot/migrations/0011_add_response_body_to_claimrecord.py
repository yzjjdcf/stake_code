# Generated manually for adding response_body field to ClaimRecord

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('serverbot', '0010_add_created_by_to_stakeaccount'),
    ]

    operations = [
        migrations.AddField(
            model_name='claimrecord',
            name='response_body',
            field=models.TextField(
                blank=True,
                help_text='记录完整的API响应内容',
                null=True,
                verbose_name='响应体'
            ),
        ),
    ]


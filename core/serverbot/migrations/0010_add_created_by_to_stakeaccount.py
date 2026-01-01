# Generated manually for adding created_by field to StakeAccount

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('serverbot', '0009_remove_code_unique_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='stakeaccount',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                help_text='记录创建此账号的用户',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_accounts',
                to=settings.AUTH_USER_MODEL,
                verbose_name='创建者'
            ),
        ),
    ]


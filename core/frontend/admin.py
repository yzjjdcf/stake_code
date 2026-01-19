from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, StakeAccount


class UserProfileInline(admin.StackedInline):
    """在 User 的 Admin 页面中内联显示 UserProfile"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = '用户扩展信息'
    fields = ('user_flag', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


# 扩展 User Admin，添加 UserProfile 内联
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


# 取消原有 User 的注册，使用扩展后的 UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(StakeAccount)
class StakeAccountAdmin(admin.ModelAdmin):
    """Stake账号管理"""
    list_display = ('id', 'user', 'stake_account_id', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__username', 'stake_account_id')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active',)
    
    fieldsets = (
        ('基本信息', {
            'fields': ('user', 'stake_account_id', 'is_active')
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at')
        }),
    )

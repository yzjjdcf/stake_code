from django.contrib import admin
from django.utils.html import format_html
from .models import WinnaClaimRecord


@admin.register(WinnaClaimRecord)
class WinnaClaimRecordAdmin(admin.ModelAdmin):
    list_display = [
        'get_code_display',
        'get_user_id_display',
        'get_username_display',
        'get_status_display_colored',
        'get_bonus_display',
        'get_error_display',
        'get_response_time_display',
        'created_at'
    ]
    
    list_filter = ['status', 'created_at', 'user_id']
    search_fields = ['code', 'username', 'user_id', 'error_message']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('基本信息', {
            'fields': ('user_id', 'username', 'code', 'status', 'created_at')
        }),
        ('奖金信息', {
            'fields': ('bonus_value', 'bonus_amount', 'bonus_currency')
        }),
        ('性能信息', {
            'fields': ('response_time_ms', 'is_retry')
        }),
        ('详细信息', {
            'fields': ('error_message', 'query_response_body', 'claim_response_body'),
            'classes': ('collapse',)
        }),
    )
    
    def get_code_display(self, obj):
        """显示代码，使用等宽字体和蓝色"""
        return format_html(
            '<span style="font-family: monospace; color: #4a9eff;">{}</span>',
            obj.code
        )
    get_code_display.short_description = '代码'
    
    def get_user_id_display(self, obj):
        """显示用户标识"""
        if obj.user_id:
            return format_html('<span style="color: #888;">{}</span>', obj.user_id)
        return '-'
    get_user_id_display.short_description = '用户标识'
    
    def get_username_display(self, obj):
        """显示账号"""
        if obj.username:
            return format_html('<span style="color: #666;">{}</span>', obj.username)
        return '-'
    get_username_display.short_description = '账号'
    
    def get_status_display_colored(self, obj):
        """带颜色的状态显示"""
        colors = {
            'claim_success': '#28a745',
            'claim_failure': '#dc3545',
            'inactive': '#ffc107',
            'not_found': '#dc3545',
            'session_expired': '#ffc107',
            'already_claimed': '#17a2b8',
            'weekly_wager_requirement': '#ffc107',
            'error_403': '#dc3545',
            'error': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        status_display = obj.get_status_display()
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, status_display
        )
    get_status_display_colored.short_description = '状态'
    
    def get_bonus_display(self, obj):
        """合并显示奖金信息，格式化为两位小数"""
        if obj.bonus_amount is not None:
            amount = float(obj.bonus_amount)
            currency = obj.bonus_currency or 'USDT'
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">{:.2f} {}</span>',
                amount, currency
            )
        elif obj.bonus_value:
            # 如果没有 bonus_amount，尝试从 bonus_value 解析
            try:
                parts = obj.bonus_value.split()
                if len(parts) >= 2:
                    amount = float(parts[0])
                    currency = parts[1]
                    return format_html(
                        '<span style="color: #28a745; font-weight: bold;">{:.2f} {}</span>',
                        amount, currency
                    )
            except:
                pass
            return format_html('<span style="color: #888;">{}</span>', obj.bonus_value)
        return '-'
    get_bonus_display.short_description = '奖金金额'
    
    def get_error_display(self, obj):
        """显示错误信息，如果太长则截断"""
        if obj.error_message:
            if len(obj.error_message) > 50:
                return format_html(
                    '<span style="color: #dc3545;" title="{}">{}...</span>',
                    obj.error_message, obj.error_message[:50]
                )
            return format_html('<span style="color: #dc3545;">{}</span>', obj.error_message)
        return '-'
    get_error_display.short_description = '错误信息'
    
    def get_response_time_display(self, obj):
        """显示响应时间，带颜色"""
        if obj.response_time_ms is None:
            return '-'
        if obj.response_time_ms < 300:
            color = '#28a745'
        elif obj.response_time_ms < 500:
            color = '#ffc107'
        else:
            color = '#dc3545'
        return format_html(
            '<span style="color: {};">{}ms</span>',
            color, obj.response_time_ms
        )
    get_response_time_display.short_description = '响应时间'
    
    class Media:
        css = {
            'all': ('admin/css/custom_winna_claimrecord.css',)
        }


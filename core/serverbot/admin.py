import json
from django.contrib import admin
from django.contrib.admin import SimpleListFilter, DateFieldListFilter
from django.db.models import Q
from django.utils.safestring import mark_safe
import re

from .models import ClaimRecord


# 自定义筛选器：按用户名筛选
class UsernameFilter(SimpleListFilter):
    title = '用户名'
    parameter_name = 'username'

    def lookups(self, request, model_admin):
        # 获取所有不同的用户名
        usernames = ClaimRecord.objects.values_list('username', flat=True).distinct()
        usernames = [u for u in usernames if u]  # 过滤掉 None
        return [(u, u) for u in sorted(usernames)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(username=self.value())
        return queryset


# 自定义筛选器：按奖金金额筛选
class BonusValueFilter(SimpleListFilter):
    title = '奖金金额'
    parameter_name = 'bonus'

    def lookups(self, request, model_admin):
        return [
            ('has_bonus', '有奖金'),
            ('no_bonus', '无奖金'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'has_bonus':
            return queryset.filter(bonus_value__isnull=False).exclude(bonus_value='')
        elif self.value() == 'no_bonus':
            return queryset.filter(Q(bonus_value__isnull=True) | Q(bonus_value=''))
        return queryset


@admin.register(ClaimRecord)
class ClaimRecordAdmin(admin.ModelAdmin):
    # 使用自定义模板显示统计信息
    change_list_template = 'admin/claimrecord_change_list.html'
    
    list_display = (
        'code',
        'username',
        'get_status_display_colored',
        'bonus_value',
        'bonus_amount',
        'bonus_currency',
        'response_time_ms',
        'error_message',
        'get_response_body_preview',
        'created_at'
    )
    
    list_filter = [
        'status',
        UsernameFilter,
        BonusValueFilter,
        ('created_at', DateFieldListFilter),
    ]
    
    search_fields = ['code', 'username']
    
    readonly_fields = ('created_at', 'get_response_json_formatted')
    
    fieldsets = (
        ('基本信息', {
            'fields': ('code', 'username', 'status', 'created_at')
        }),
        ('奖金信息', {
            'fields': ('bonus_value', 'bonus_amount', 'bonus_currency'),
            'description': '奖金金额信息（bonus_value 用于显示，bonus_amount 和 bonus_currency 用于计算）'
        }),
        ('响应信息', {
            'fields': ('response_time_ms', 'is_retry', 'error_message', 'get_response_json_formatted'),
            'description': '响应时间和错误信息，以及完整的 API 响应 JSON'
        }),
    )
    
    def changelist_view(self, request, extra_context=None):
        """重写 changelist_view 以计算统计信息"""
        # 调用父类方法获取响应
        response = super().changelist_view(request, extra_context=extra_context)
        
        # 检查 response 是否是 TemplateResponse
        if not response or not hasattr(response, 'context_data'):
            return response
        
        # 从 context_data 中获取已筛选的 queryset（包含所有筛选条件）
        cl_obj = response.context_data.get('cl')
        if cl_obj and hasattr(cl_obj, 'queryset'):
            filtered_qs = cl_obj.queryset
        else:
            # 如果无法获取，使用 get_queryset
            filtered_qs = self.get_queryset(request)
        
        # 计算统计：使用 bonus_amount 字段（Decimal）进行精确计算
        from django.db.models import Sum, Count
        stats = filtered_qs.filter(status='claim_success').aggregate(
            total_amount=Sum('bonus_amount'),
            success_count=Count('id')
        )
        
        total_amount = stats['total_amount'] or 0
        success_count = stats['success_count'] or 0
        total_records = filtered_qs.count()
        
        # 添加到响应上下文
        response.context_data['total_amount'] = float(total_amount)
        response.context_data['success_count'] = success_count
        response.context_data['total_records'] = total_records
        
        return response
    
    def get_status_display_colored(self, obj):
        """带颜色的状态显示"""
        colors = {
            'claim_success': '#28a745',        # 绿色
            'claim_failure': '#dc3545',        # 红色
            'error_403': '#ffc107',            # 黄色
            'not_found': '#6c757d',            # 灰色
            'inactive': '#17a2b8',             # 蓝色
            'session_expired': '#ff9800',      # 橙色
            'already_claimed': '#6f42c1',     # 紫色
            'weekly_wager_requirement': '#17a2b8', # 蓝色
            'error': '#dc3545',                # 红色
        }
        status_display = obj.get_status_display()
        color = colors.get(obj.status, '#000')
        return mark_safe(
            f'<span style="color: {color}; font-weight: bold;">{status_display}</span>'
        )
    get_status_display_colored.short_description = '状态'
    
    def get_response_body_preview(self, obj):
        """在列表页显示响应体预览"""
        # 优先显示领取接口的响应体（如果有），否则显示查询接口的响应体
        response_body = obj.claim_response_body if obj.claim_response_body else obj.query_response_body
        if not response_body:
            return mark_safe('<span style="color: #999;">无响应体</span>')
        
        # 截取前100个字符作为预览
        preview = response_body[:100]
        if len(response_body) > 100:
            preview += '...'
        
        # 转义 HTML 特殊字符
        import html
        preview = html.escape(preview)
        
        # 显示来源标识
        source = "领取接口" if obj.claim_response_body else "查询接口"
        
        return mark_safe(
            f'<span style="font-family: monospace; font-size: 11px; color: #666;" '
            f'title="点击详情页查看完整内容">[{source}] {preview}</span>'
        )
    get_response_body_preview.short_description = '响应体预览'
    
    def get_response_json_formatted(self, obj):
        """在详情页格式化显示完整的 API 响应 JSON（优先显示 claim_response_body）"""
        # 优先显示 claim_response_body，如果没有则显示 query_response_body
        response_body = obj.claim_response_body if obj.claim_response_body else obj.query_response_body
        source = "领取接口" if obj.claim_response_body else ("查询接口" if obj.query_response_body else None)
        
        if not response_body:
            return mark_safe('<span style="color: #999;">无响应数据</span>')
        
        try:
            # 尝试解析为 JSON 并格式化
            response_data = json.loads(response_body)
            formatted_json = json.dumps(response_data, ensure_ascii=False, indent=2)
            # 转义 HTML 特殊字符
            import html
            formatted_json = html.escape(formatted_json)
            
            # 添加来源标识
            source_label = f'<div style="margin-bottom: 8px; font-size: 11px; color: #666; font-weight: 600;">来源: {source}</div>' if source else ''
            
            return mark_safe(
                f'{source_label}'
                f'<pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; '
                f'overflow-x: auto; font-size: 12px; line-height: 1.5; max-height: 500px; '
                f'overflow-y: auto; margin: 0;">{formatted_json}</pre>'
            )
        except (json.JSONDecodeError, TypeError):
            # 如果不是 JSON，直接显示文本
            import html
            escaped_text = html.escape(response_body)
            source_label = f'<div style="margin-bottom: 8px; font-size: 11px; color: #666; font-weight: 600;">来源: {source}</div>' if source else ''
            return mark_safe(
                f'{source_label}'
                f'<pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; '
                f'overflow-x: auto; font-size: 12px; line-height: 1.5; max-height: 500px; '
                f'overflow-y: auto; white-space: pre-wrap; margin: 0;">{escaped_text}</pre>'
            )
    get_response_json_formatted.short_description = 'API 响应 JSON'

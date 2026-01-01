import csv
import json
import threading  # 必须导入，否则 re_warmup 会报错
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import admin, messages

from . import models
from .models import StakeAccount, ProxyPool, CodeRecord, ClaimRecord
from .forms import ProxyImportForm
from .bypass import run_pre_logic_capsolver  # 使用 Capsolver 过盾逻辑
from django.utils.safestring import mark_safe
import urllib.parse  # 必须写全，才能直接使用 urllib.parse.urlparse

# 1. 代理池管理：只管理代理地址和导入功能
@admin.register(ProxyPool)
class ProxyPoolAdmin(admin.ModelAdmin):
    # 修正点：ProxyPool 表里只有 address 和 is_active
    list_display = ('address', 'is_active')

    # 指定自定义的列表页模板 (用于显示批量导入按钮)
    change_list_template = "admin/proxy_pool_change_list.html"

    # 注册自定义 URL 用于导入代理
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-proxies/', self.admin_site.admin_view(self.import_proxies), name='import_proxies'),
        ]
        return custom_urls + urls

    # 处理导入逻辑 (保持你的原始代码逻辑不动)
    def import_proxies(self, request):
        if request.method == "POST":
            form = ProxyImportForm(request.POST, request.FILES)
            if form.is_valid():
                raw_proxies = []
                text_data = form.cleaned_data['proxy_text']
                if text_data:
                    raw_proxies.extend(text_data.splitlines())

                file_data = request.FILES.get('proxy_file')
                if file_data:
                    file_content = file_data.read().decode('utf-8').splitlines()
                    raw_proxies.extend(file_content)

                count = 0
                for line in raw_proxies:
                    line = line.strip()
                    if line and line.startswith('http'):
                        ProxyPool.objects.get_or_create(address=line)
                        count += 1

                messages.success(request, f"成功导入 {count} 个代理地址！")
                return redirect("..")
        else:
            form = ProxyImportForm()
        return render(request, "admin/proxy_import.html", {"form": form, "title": "批量导入代理"})


@admin.register(StakeAccount)
class StakeAccountAdmin(admin.ModelAdmin):
    # 1. 将 'update_cf_button' 加入列表显示
    # "cf_clearance",
    # 1. 更新 list_display，加入新增字段和耗时显示
    list_display = (
        'id',
        'username',
        'is_active',
        'get_proxy_full',
        'get_cf_clearance',
        'bypass_trigger_time',  # 显示触发时间
        'bypass_success_time',  # 显示成功时间
        'update_cf_button'
    )

    list_display_links = ('id', 'username')  # 建议把用户名也设为链接，方便点击

    # 2. 加入编辑页，让你能手动勾选/取消
    fields = ('username', 'token', 'proxy', 'is_active', 'cookies_json', 'user_agent')
    # 1. 展示完整的代理信息（协议、账号、密码、IP、端口全显）
    def get_proxy_full(self, obj):
        if obj.proxy and obj.proxy.address:
            # 使用 code 标签和 break-all 样式，确保长字符串在单元格内自动换行
            return mark_safe(
                f'<code style="word-break: break-all; font-size: 11px; color: #333;">'
                f'{obj.proxy.address}'
                f'</code>'
            )
        return mark_safe('<span style="color: gray;">未分配代理</span>')

    get_proxy_full.short_description = '代理地址'

    # 2. 只展示 cf_clearance 的前 1/3
    def get_cf_clearance(self, obj):
        if not obj.cookies_json:
            return mark_safe('<span style="color: gray;">未获取</span>')
        try:
            cookies = json.loads(obj.cookies_json)  # 解析 cookie 列表
            for cookie in cookies:
                if cookie.get('name') == 'cf_clearance':
                    full_value = cookie.get('value')  # 获取完整通行证
                    # 计算三分之一的长度
                    display_len = len(full_value) // 3
                    short_value = full_value[:display_len] + "..."
                    return mark_safe(
                        f'<code title="{full_value}" style="font-size: 11px; cursor: help;">{short_value}</code>')
        except Exception:
            pass
        return mark_safe('<span style="color: red;">无效数据</span>')

    get_cf_clearance.short_description = 'cf_clearance (1/3)'

    # 设置该列在后台显示的表头名称
    get_cf_clearance.short_description = 'cf_clearance'

    def update_cf_button(self, obj):
        return mark_safe(
            f'''
                    <div style="display: flex; gap: 5px;">
                        <button type="button" class="button" 
                            onclick="runWarmup({obj.id}, '{obj.username}')"
                            style="background-color: #28a745; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">
                            🔄 强制更新 CF
                        </button>
                        <button type="button" class="button" 
                            onclick="deleteCF({obj.id}, '{obj.username}')"
                            style="background-color: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">
                            🗑️ 删除 CF
                        </button>
                    </div>
                    <script>
                    if (typeof runWarmup === 'undefined') {{
                        window.runWarmup = function(id, name) {{
                            if (!confirm('确定要强制更新 ' + name + ' 的 CF 吗？')) {{
                                return;
                            }}
                            const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
                                             document.querySelector('input[name=csrfmiddlewaretoken]')?.value ||
                                             document.cookie.match(/csrftoken=([^;]+)/)?.[1];

                            fetch('/admin/serverbot/stakeaccount/' + id + '/run-warmup/', {{
                                method: 'POST',
                                headers: {{
                                    'X-CSRFToken': csrftoken,
                                    'Content-Type': 'application/json'
                                }}
                            }}).then(res => {{
                                if (res.ok) {{
                                    alert('🚀 ' + name + ' 过盾任务已提交，请观察控制台日志');
                                    setTimeout(() => location.reload(), 1000);
                                }} else {{
                                    alert('❌ 操作失败，请重试');
                                }}
                            }}).catch(err => {{
                                console.error('错误:', err);
                                alert('❌ 请求失败: ' + err.message);
                            }});
                        }};
                    }}
                    
                    if (typeof deleteCF === 'undefined') {{
                        window.deleteCF = function(id, name) {{
                            if (!confirm('确定要删除 ' + name + ' 的 CF Cookie 吗？\\n\\n这将清除 cookies_json 和 user_agent 数据。')) {{
                                return;
                            }}
                            const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
                                             document.querySelector('input[name=csrfmiddlewaretoken]')?.value ||
                                             document.cookie.match(/csrftoken=([^;]+)/)?.[1];

                            fetch('/admin/serverbot/stakeaccount/' + id + '/delete-cf/', {{
                                method: 'POST',
                                headers: {{
                                    'X-CSRFToken': csrftoken,
                                    'Content-Type': 'application/json'
                                }}
                            }}).then(res => {{
                                if (res.ok) {{
                                    alert('✅ ' + name + ' 的 CF Cookie 已删除');
                                    location.reload();
                                }} else {{
                                    alert('❌ 操作失败，请重试');
                                }}
                            }}).catch(err => {{
                                console.error('错误:', err);
                                alert('❌ 请求失败: ' + err.message);
                            }});
                        }};
                    }}
                    </script>
                    '''
        )
    update_cf_button.short_description = '快捷操作'
    # update_cf_button.allow_tags = True

    # 3. 注册按钮点击后的 URL 路径
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:account_id>/run-warmup/',
                self.admin_site.admin_view(self.run_warmup_view),
                name='stake-account-warmup',
            ),
            path(
                '<int:account_id>/delete-cf/',
                self.admin_site.admin_view(self.delete_cf_view),
                name='stake-account-delete-cf',
            ),
        ]
        return custom_urls + urls

    # 4. 强制更新 CF 的处理逻辑（使用 Capsolver，不使用浏览器）
    def run_warmup_view(self, request, account_id):
        if request.method != 'POST':
            messages.error(request, "无效的请求方法")
            return redirect('/admin/serverbot/stakeaccount/')
        
        account = self.get_object(request, account_id)
        if account:
            # 开启后台线程，执行 Capsolver 过盾逻辑（不使用浏览器）
            threading.Thread(target=run_pre_logic_capsolver, args=(account,), daemon=True).start()
            messages.success(request, f"🚀 账号 {account.username} 的 Capsolver 过盾任务已启动，请观察控制台日志。")
        else:
            messages.error(request, "账号不存在")
        return redirect('/admin/serverbot/stakeaccount/')
    
    # 5. 删除 CF 的处理逻辑
    def delete_cf_view(self, request, account_id):
        if request.method != 'POST':
            messages.error(request, "无效的请求方法")
            return redirect('/admin/serverbot/stakeaccount/')
        
        account = self.get_object(request, account_id)
        if account:
            # 清除 cookies_json 和 user_agent
            account.cookies_json = None
            account.user_agent = None
            account.bypass_trigger_time = None
            account.bypass_success_time = None
            account.save()
            messages.success(request, f"✅ 账号 {account.username} 的 CF Cookie 已删除。")
        else:
            messages.error(request, "账号不存在")
        return redirect('/admin/serverbot/stakeaccount/')


# 内联显示 ClaimRecord
class ClaimRecordInline(admin.TabularInline):
    """在 CodeRecord 详情页内联显示所有操作记录"""
    model = ClaimRecord
    extra = 0
    readonly_fields = ('account', 'code', 'get_status_display_colored', 'bonus_value', 'response_time_ms', 'error_message', 'created_at')
    fields = ('account', 'get_status_display_colored', 'bonus_value', 'response_time_ms', 'error_message', 'created_at')
    can_delete = False
    show_change_link = True
    ordering = ['-created_at']  # 按时间倒序显示
    
    def get_status_display_colored(self, obj):
        """带颜色的状态显示"""
        colors = {
            'success': '#28a745',
            'failure': '#dc3545',
            'error_403': '#ffc107',
            'not_found': '#6c757d',
            'inactive': '#17a2b8',
            'already_claimed': '#6f42c1',
            'error': '#e83e8c',
        }
        status_display = obj.get_status_display()
        color = colors.get(obj.status, '#000')
        return mark_safe(
            f'<span style="color: {color}; font-weight: bold;">{status_display}</span>'
        )
    get_status_display_colored.short_description = '状态'
    
    def has_add_permission(self, request, obj=None):
        return False  # 不允许在详情页添加新记录


@admin.register(CodeRecord)
class CodeRecordAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'get_status_display_colored',
        'actual_value',
        'get_statistics',
        'get_claim_details_link',
        'created_at',
        'updated_at'
    )
    list_filter = ('status', 'created_at', 'is_timeout_trigger')
    search_fields = ('code',)
    readonly_fields = ('total_attempts', 'success_count', 'failure_count', 'error_403_count', 'created_at', 'updated_at')
    
    # 添加内联显示
    inlines = [ClaimRecordInline]
    
    fieldsets = (
        ('基本信息', {
            'fields': ('code', 'status', 'actual_value', 'is_timeout_trigger')
        }),
        ('统计信息', {
            'fields': ('total_attempts', 'success_count', 'failure_count', 'error_403_count')
        }),
        ('操作历史', {
            'description': '下方显示所有账号的操作记录',
            'fields': ()  # 通过内联显示 ClaimRecord
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def get_status_display_colored(self, obj):
        """带颜色的状态显示"""
        colors = {
            'valid': '#28a745',      # 绿色
            'invalid': '#dc3545',     # 红色
            'expired': '#ffc107',     # 黄色
            'claimed': '#6c757d',    # 灰色
            'unknown': '#17a2b8',     # 蓝色
        }
        status_display = obj.get_status_display()
        color = colors.get(obj.status, '#000')
        return mark_safe(
            f'<span style="color: {color}; font-weight: bold;">{status_display}</span>'
        )
    get_status_display_colored.short_description = '状态'
    
    def get_statistics(self, obj):
        """显示统计信息"""
        if obj.total_attempts == 0:
            return mark_safe('<span style="color: gray;">暂无数据</span>')
        
        success_rate = (obj.success_count / obj.total_attempts * 100) if obj.total_attempts > 0 else 0
        return mark_safe(
            f'<div style="font-size: 11px;">'
            f'总尝试: <strong>{obj.total_attempts}</strong><br>'
            f'成功: <span style="color: #28a745;">{obj.success_count}</span> | '
            f'失败: <span style="color: #dc3545;">{obj.failure_count}</span> | '
            f'403: <span style="color: #ffc107;">{obj.error_403_count}</span><br>'
            f'成功率: <strong>{success_rate:.1f}%</strong>'
            f'</div>'
        )
    get_statistics.short_description = '统计信息'
    
    def get_claim_details_link(self, obj):
        """显示领取明细链接"""
        count = obj.claim_records.count()
        if count == 0:
            return mark_safe('<span style="color: gray;">无记录</span>')
        url = f'/admin/serverbot/claimrecord/?code_record__id__exact={obj.id}'
        return mark_safe(f'<a href="{url}">查看明细 ({count})</a>')
    get_claim_details_link.short_description = '领取明细'
    
    def get_queryset(self, request):
        """优化查询，预加载关联数据"""
        qs = super().get_queryset(request)
        return qs.prefetch_related('claim_records')


@admin.register(ClaimRecord)
class ClaimRecordAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'account',
        'get_status_display_colored',
        'bonus_value',
        'response_time_ms',
        'is_retry',
        'created_at'
    )
    list_filter = ('status', 'created_at', 'code_record')
    search_fields = ('code', 'account__username')
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('基本信息', {
            'fields': ('code_record', 'code', 'account', 'status')
        }),
        ('结果信息', {
            'fields': ('bonus_value', 'response_time_ms', 'is_retry', 'error_message')
        }),
        ('时间信息', {
            'fields': ('created_at',)
        }),
    )
    
    def get_status_display_colored(self, obj):
        """带颜色的状态显示"""
        colors = {
            'success': '#28a745',        # 绿色
            'failure': '#dc3545',         # 红色
            'error_403': '#ffc107',       # 黄色
            'not_found': '#6c757d',       # 灰色
            'inactive': '#17a2b8',        # 蓝色
            'already_claimed': '#6f42c1', # 紫色
            'error': '#dc3545',           # 红色
        }
        status_display = obj.get_status_display()
        color = colors.get(obj.status, '#000')
        return mark_safe(
            f'<span style="color: {color}; font-weight: bold;">{status_display}</span>'
        )
    get_status_display_colored.short_description = '状态'
    
    def get_queryset(self, request):
        """优化查询"""
        qs = super().get_queryset(request)
        return qs.select_related('account', 'code_record')
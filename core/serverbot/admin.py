import csv
import json
import threading  # 必须导入，否则 re_warmup 会报错
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter, DateFieldListFilter
from django.db.models import Q, Sum, DecimalField
from django.db.models.functions import Cast

from . import models
from .models import StakeAccount, ProxyPool, CodeRecord, ClaimRecord
from .forms import ProxyImportForm
from .bypass import run_pre_logic_capsolver  # 使用 Capsolver 过盾逻辑
from django.utils.safestring import mark_safe
import urllib.parse  # 必须写全，才能直接使用 urllib.parse.urlparse
import re

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

                # 获取所有现有代理的 host:port 集合（用于去重检查）
                from .utils import parse_proxy_address
                existing_proxies = ProxyPool.objects.all()
                existing_host_port_set = set()
                
                for existing_proxy in existing_proxies:
                    proxy_info = parse_proxy_address(existing_proxy.address)
                    if proxy_info:
                        host = proxy_info.get('host')
                        port = proxy_info.get('port')
                        if host and port:
                            existing_host_port_set.add((host, port))
                
                count = 0
                skipped_count = 0
                for line in raw_proxies:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 只支持新格式：host:port:username:password（至少4个冒号分隔的部分）
                    parts = line.split(':')
                    if len(parts) < 4:
                        # 格式不正确，跳过
                        continue
                    
                    # 验证端口是数字
                    try:
                        int(parts[1])
                    except (ValueError, IndexError):
                        # 端口不是数字，跳过
                        continue
                    
                    # 解析代理信息
                    proxy_info = parse_proxy_address(line)
                    
                    if proxy_info:
                        host = proxy_info.get('host')
                        port = proxy_info.get('port')
                        
                        # 检查 host 和 port 是否已存在
                        if host and port and (host, port) in existing_host_port_set:
                            skipped_count += 1
                            continue
                        
                        # 存入数据库
                        obj, created = ProxyPool.objects.get_or_create(address=line)
                        if created:
                            count += 1
                            # 添加到已存在集合，避免同批次重复
                            existing_host_port_set.add((host, port))
                
                message = f"成功导入 {count} 个代理地址！"
                if skipped_count > 0:
                    message += f" 跳过 {skipped_count} 个重复的 host:port 记录。"
                messages.success(request, message)

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
        'get_proxy_location',  # 显示代理归属地
        'get_token_preview',   # 显示API令牌
        'bypass_trigger_time',  # 显示触发时间
        'bypass_success_time',  # 显示成功时间
        'update_cf_button'
    )

    list_display_links = ('id', 'username')  # 建议把用户名也设为链接，方便点击

    # 2. 加入编辑页，让你能手动勾选/取消
    fields = ('username', 'token', 'proxy', 'is_active', 'cookies_json', 'user_agent', 'created_by')
    readonly_fields = ('created_by',)  # 创建者字段只读，自动设置
    
    # 权限控制：普通用户只能看到自己创建的账号
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            # 超级管理员可以看到所有账号
            return qs
        else:
            # 普通用户只能看到自己创建的账号（且 created_by_id 不为空）
            # 使用更严格的过滤：必须 created_by_id 等于当前用户 ID 且不为 NULL
            return qs.filter(
                created_by_id=request.user.id,
                created_by_id__isnull=False
            )
    
    # 保存时自动设置创建者
    def save_model(self, request, obj, form, change):
        if not change:  # 新建时
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
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

    # 2. 显示代理归属地
    def get_proxy_location(self, obj):
        if obj.proxy and obj.proxy.location:
            return obj.proxy.location
        elif obj.proxy:
            return mark_safe('<span style="color: gray;">未检测</span>')
        return mark_safe('<span style="color: gray;">未分配代理</span>')
    
    get_proxy_location.short_description = '代理区域'

    # 3. 显示API令牌（截断显示）
    def get_token_preview(self, obj):
        if obj.token:
            # 显示前20个字符，后面用...表示
            token_len = len(obj.token)
            if token_len > 20:
                preview = obj.token[:20] + "..."
                return mark_safe(
                    f'<code title="{obj.token}" style="font-size: 11px; cursor: help; word-break: break-all;">{preview}</code>'
                )
            else:
                return mark_safe(f'<code style="font-size: 11px;">{obj.token}</code>')
        return mark_safe('<span style="color: gray;">未填写</span>')
    
    get_token_preview.short_description = 'API令牌'

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
    # 权限控制：只有超级管理员可以访问
    def has_module_permission(self, request):
        return request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_add_permission(self, request):
        return request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    list_display = (
        'code',  # 红包代码
        'get_is_valid_status_display',  # 是否有效码（状态）
        'get_statistics',  # 统计信息
        'get_claim_details_link',  # 领取明细
        'created_at',  # 创建时间
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
    
    def get_is_valid_status_display(self, obj):
        """
        显示代码是否有效，以及有效的子状态
        有效：可用、次数领取完、流水不够
        无效：未找到、403错误、其他错误
        """
        # 获取所有相关的 ClaimRecord
        claim_records = obj.claim_records.all()
        
        if not claim_records.exists():
            # 没有记录，显示未知
            return mark_safe('<span style="color: #6c757d; font-weight: bold;">❓ 未知</span>')
        
        # 统计各种状态
        has_success = claim_records.filter(status='success').exists()
        has_inactive = claim_records.filter(status='inactive').exists()
        has_already_claimed = claim_records.filter(status='already_claimed').exists()
        has_weekly_wager = claim_records.filter(status='weekly_wager_requirement').exists()
        has_not_found = claim_records.filter(status='not_found').exists()
        has_error_403 = claim_records.filter(status='error_403').exists()
        has_error = claim_records.filter(status='error').exists()
        
        # 判断是否有效：只要有 success、inactive、already_claimed、weekly_wager_requirement 中的任意一个，就认为有效
        is_valid = has_success or has_inactive or has_already_claimed or has_weekly_wager
        
        if is_valid:
            # 有效，显示子状态
            sub_statuses = []
            if has_success:
                sub_statuses.append('<span style="color: #28a745;">✅ 可用</span>')
            if has_inactive or has_already_claimed:
                sub_statuses.append('<span style="color: #ffc107;">⌛ 次数领取完</span>')
            if has_weekly_wager:
                sub_statuses.append('<span style="color: #17a2b8;">📋 流水不够</span>')
            
            # 去重并组合显示
            unique_statuses = list(dict.fromkeys(sub_statuses))  # 保持顺序的去重
            status_html = ' | '.join(unique_statuses)
            
            return mark_safe(
                f'<div style="font-weight: bold;">'
                f'<span style="color: #28a745;">✅ 有效</span><br>'
                f'<span style="font-size: 11px; font-weight: normal;">{status_html}</span>'
                f'</div>'
            )
        else:
            # 无效
            return mark_safe('<span style="color: #dc3545; font-weight: bold;">❌ 无效</span>')
    
    get_is_valid_status_display.short_description = '是否有效码'
    
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


# 自定义筛选器：按账号筛选（带权限控制）
class AccountFilter(SimpleListFilter):
    title = '账号'
    parameter_name = 'account'

    def lookups(self, request, model_admin):
        # 获取当前用户有权限的账号列表
        qs = model_admin.get_queryset(request)
        # 获取所有不同的账号（已应用权限过滤）
        accounts = qs.values_list('account__id', 'account__username').distinct()
        
        # 返回选项
        return [(str(acc_id), username) for acc_id, username in accounts if acc_id and username]

    def queryset(self, request, queryset):
        if self.value():
            try:
                account_id = int(self.value())
                return queryset.filter(account__id=account_id)
            except (ValueError, TypeError):
                return queryset


# 自定义筛选器：按账号创建者筛选（仅超级管理员可见）
class AccountCreatorFilter(SimpleListFilter):
    title = '账号创建者'
    parameter_name = 'account_creator'

    def lookups(self, request, model_admin):
        # 只有超级管理员可以看到这个筛选器
        if not request.user.is_superuser:
            return []
        
        # 获取所有不同的账号创建者（去重）
        from django.contrib.auth.models import User
        qs = model_admin.get_queryset(request)
        # 使用 distinct() 并确保去重
        creator_ids = qs.values_list('account__created_by__id', 'account__created_by__username').distinct()
        
        # 使用字典去重（按 ID），确保每个用户只出现一次
        creators_dict = {}
        for uid, username in creator_ids:
            if uid and uid not in creators_dict:
                creators_dict[uid] = username or f'用户ID:{uid}'
        
        # 按用户名排序
        sorted_creators = sorted(creators_dict.items(), key=lambda x: x[1])
        
        # 返回选项
        return [(str(uid), username) for uid, username in sorted_creators]

    def queryset(self, request, queryset):
        if self.value() and request.user.is_superuser:
            try:
                creator_id = int(self.value())
                return queryset.filter(account__created_by_id=creator_id)
            except (ValueError, TypeError):
                return queryset
        return queryset


# 自定义筛选器：按奖金金额筛选（带权限控制）
class BonusValueFilter(SimpleListFilter):
    title = '奖金金额'
    parameter_name = 'bonus_value'

    def lookups(self, request, model_admin):
        # 获取所有不同的 bonus_value（只显示有值的，已应用权限过滤）
        qs = model_admin.get_queryset(request).filter(
            bonus_value__isnull=False
        ).exclude(bonus_value='').values_list('bonus_value', flat=True).distinct()
        
        # 提取金额并去重
        amounts = set()
        for value in qs:
            if value:
                # 尝试提取数字（支持 $12.50, 12.50, $50 等格式）
                match = re.search(r'[\d.]+', str(value))
                if match:
                    amounts.add(float(match.group()))
        
        # 按金额排序
        sorted_amounts = sorted(amounts, reverse=True)
        
        # 返回选项（最多显示20个）
        return [(str(amt), f'${amt:.2f}') for amt in sorted_amounts[:20]]

    def queryset(self, request, queryset):
        if self.value():
            try:
                target_amount = float(self.value())
                # 模糊匹配：查找包含该金额的记录
                return queryset.filter(bonus_value__icontains=str(target_amount))
            except ValueError:
                return queryset


@admin.register(ClaimRecord)
class ClaimRecordAdmin(admin.ModelAdmin):
    # 使用自定义模板显示总计
    change_list_template = 'admin/claimrecord_change_list.html'
    
    # 权限控制：普通用户只能看到与自己创建的账号相关的 ClaimRecord
    def get_queryset(self, request):
        """权限过滤 + 查询优化"""
        qs = super().get_queryset(request)
        # 优化查询，预加载关联数据
        qs = qs.select_related('account', 'code_record', 'account__created_by')
        
        if request.user.is_superuser:
            # 超级管理员可以看到所有记录
            return qs
        else:
            # 普通用户只能看到自己创建的账号的 ClaimRecord（且账号的 created_by_id 不为空）
            # 使用更严格的过滤：必须 created_by_id 等于当前用户 ID 且不为 NULL
            return qs.filter(
                account__created_by_id=request.user.id,
                account__created_by_id__isnull=False
            )
    
    def has_module_permission(self, request):
        # 所有用户都可以访问模块
        return True
    
    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj:
            # 检查是否是用户创建的账号的记录（且 created_by 不为空）
            return obj.account.created_by == request.user and obj.account.created_by is not None
        return True
    
    def has_add_permission(self, request):
        # 不允许手动添加（由系统自动创建）
        return False
    
    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj:
            # 检查是否是用户创建的账号的记录（且 created_by 不为空）
            return obj.account.created_by == request.user and obj.account.created_by is not None
        return False
    
    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj:
            # 检查是否是用户创建的账号的记录（且 created_by 不为空）
            return obj.account.created_by == request.user and obj.account.created_by is not None
        return False
    list_display = (
        'code',
        'account',
        'get_status_display_colored',
        'bonus_value',
        'response_time_ms',
        'get_response_body_preview',
        'created_at'
    )
    def get_list_filter(self, request):
        """根据用户权限返回不同的筛选器列表"""
        base_filters = [
            'status',
            AccountFilter,  # 按账号筛选（带权限控制）
            BonusValueFilter,  # 按奖金金额筛选（带权限控制）
            ('created_at', DateFieldListFilter),  # 按时间段筛选
            # 移除 code_record，改为使用搜索框
        ]
        
        # 超级管理员额外显示账号创建者筛选
        if request.user.is_superuser:
            base_filters.insert(2, AccountCreatorFilter)  # 插入到账号筛选之后
        
        return base_filters
    
    def get_search_fields(self, request):
        """禁用默认搜索框，使用自定义的多搜索框"""
        return []  # 返回空列表，禁用默认搜索框
    readonly_fields = ('created_at', 'get_query_response_body_formatted', 'get_claim_response_body_formatted')
    
    fieldsets = (
        ('基本信息', {
            'fields': ('code_record', 'code', 'account', 'status')
        }),
        ('结果信息', {
            'fields': ('bonus_value', 'response_time_ms', 'is_retry', 'error_message')
        }),
        ('查询接口响应', {
            'fields': ('get_query_response_body_formatted',),
            'description': '查询代码是否可用的API响应内容（第一步接口）'
        }),
        ('领取接口响应', {
            'fields': ('get_claim_response_body_formatted',),
            'description': '领取代码的API响应内容（第二步接口，仅当代码可用时才有）'
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
    
    def get_query_response_body_formatted(self, obj):
        """在详情页格式化显示查询接口响应体"""
        if not obj.query_response_body:
            return mark_safe('<span style="color: #999;">无查询接口响应体</span>')
        
        try:
            # 尝试解析为 JSON 并格式化
            response_data = json.loads(obj.query_response_body)
            formatted_json = json.dumps(response_data, ensure_ascii=False, indent=2)
            # 转义 HTML 特殊字符
            import html
            formatted_json = html.escape(formatted_json)
            return mark_safe(
                f'<pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; '
                f'overflow-x: auto; font-size: 12px; line-height: 1.5; max-height: 500px; '
                f'overflow-y: auto;">{formatted_json}</pre>'
            )
        except (json.JSONDecodeError, TypeError):
            # 如果不是 JSON，直接显示文本
            import html
            escaped_text = html.escape(obj.query_response_body)
            return mark_safe(
                f'<pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; '
                f'overflow-x: auto; font-size: 12px; line-height: 1.5; max-height: 500px; '
                f'overflow-y: auto; white-space: pre-wrap;">{escaped_text}</pre>'
            )
    get_query_response_body_formatted.short_description = '查询接口响应体'
    
    def get_claim_response_body_formatted(self, obj):
        """在详情页格式化显示领取接口响应体"""
        if not obj.claim_response_body:
            return mark_safe('<span style="color: #999;">无领取接口响应体（未走到第二步）</span>')
        
        try:
            # 尝试解析为 JSON 并格式化
            response_data = json.loads(obj.claim_response_body)
            formatted_json = json.dumps(response_data, ensure_ascii=False, indent=2)
            # 转义 HTML 特殊字符
            import html
            formatted_json = html.escape(formatted_json)
            return mark_safe(
                f'<pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; '
                f'overflow-x: auto; font-size: 12px; line-height: 1.5; max-height: 500px; '
                f'overflow-y: auto;">{formatted_json}</pre>'
            )
        except (json.JSONDecodeError, TypeError):
            # 如果不是 JSON，直接显示文本
            import html
            escaped_text = html.escape(obj.claim_response_body)
            return mark_safe(
                f'<pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; '
                f'overflow-x: auto; font-size: 12px; line-height: 1.5; max-height: 500px; '
                f'overflow-y: auto; white-space: pre-wrap;">{escaped_text}</pre>'
            )
    get_claim_response_body_formatted.short_description = '领取接口响应体'
    
    def changelist_view(self, request, extra_context=None):
        """重写 changelist_view 以处理自定义搜索和计算总计"""
        # 处理自定义搜索参数
        code_search = request.GET.get('code_search', '').strip()
        username_search = request.GET.get('username_search', '').strip()
        creator_search = request.GET.get('creator_search', '').strip()
        status_search = request.GET.get('status_search', '').strip()
        bonus_search = request.GET.get('bonus_search', '').strip()
        date_start = request.GET.get('date_start', '').strip()
        date_end = request.GET.get('date_end', '').strip()
        
        # 获取所有不同的状态值和金额值（用于下拉框）
        base_qs = self.get_queryset(request)
        # 直接使用模型定义的 STATUS_CHOICES，确保去重
        status_list = list(ClaimRecord.STATUS_CHOICES)
        
        # 获取所有不同的金额值（去重）
        bonus_values = base_qs.filter(
            bonus_value__isnull=False
        ).exclude(bonus_value='').values_list('bonus_value', flat=True).distinct()
        
        # 提取金额并去重
        amounts = set()
        for value in bonus_values:
            if value:
                # 尝试提取数字（支持 $12.50, 12.50, $50 等格式）
                match = re.search(r'[\d.]+', str(value))
                if match:
                    amounts.add(float(match.group()))
        
        # 按金额排序
        sorted_amounts = sorted(amounts, reverse=True)
        bonus_list = [(str(amt), f'${amt:.2f}') for amt in sorted_amounts[:50]]  # 最多显示50个
        
        # 保存原始 get_queryset 方法
        original_get_queryset = self.get_queryset
        
        # 创建包装的 get_queryset 方法，应用自定义搜索
        def custom_get_queryset(r):
            qs = original_get_queryset(r)
            # 应用自定义搜索
            if code_search:
                qs = qs.filter(Q(code__icontains=code_search) | Q(code_record__code__icontains=code_search))
            if username_search:
                qs = qs.filter(account__username__icontains=username_search)
            if creator_search and r.user.is_superuser:
                qs = qs.filter(account__created_by__username__icontains=creator_search)
            if status_search:
                qs = qs.filter(status=status_search)  # 精确匹配
            if bonus_search:
                qs = qs.filter(bonus_value__icontains=bonus_search)  # 模糊匹配金额
            # 时间区间搜索
            if date_start:
                from django.utils.dateparse import parse_date
                start_date = parse_date(date_start)
                if start_date:
                    qs = qs.filter(created_at__date__gte=start_date)
            if date_end:
                from django.utils.dateparse import parse_date
                end_date = parse_date(date_end)
                if end_date:
                    qs = qs.filter(created_at__date__lte=end_date)
            return qs
        
        # 临时替换 get_queryset 方法
        self.get_queryset = custom_get_queryset
        
        # 准备 extra_context
        if extra_context is None:
            extra_context = {}
        
        # 先添加搜索相关的上下文
        extra_context['code_search'] = code_search
        extra_context['username_search'] = username_search
        extra_context['creator_search'] = creator_search
        extra_context['status_search'] = status_search
        extra_context['bonus_search'] = bonus_search
        extra_context['date_start'] = date_start
        extra_context['date_end'] = date_end
        extra_context['status_list'] = status_list
        extra_context['bonus_list'] = bonus_list
        
        response = None
        try:
            # 调用父类方法获取响应
            response = super().changelist_view(request, extra_context=extra_context)
            
            # 使用 ChangeList 来获取筛选后的 queryset（包含所有筛选器）
            from django.contrib.admin.views.main import ChangeList
            
            # 创建 ChangeList 实例来应用所有筛选
            cl = ChangeList(
                request, 
                self.model, 
                self.list_display, 
                self.list_display_links,
                self.get_list_filter(request), 
                self.date_hierarchy, 
                [],
                self.list_select_related, 
                self.list_per_page, 
                self.list_max_show_all,
                self.list_editable, 
                self
            )
            
            # 获取筛选后的 queryset（不考虑分页）
            filtered_qs = cl.get_queryset(request)
            
            # 计算总计：只计算 success 状态且有 bonus_value 的记录
            total_amount = 0
            success_count = 0
            
            for record in filtered_qs.filter(status='success', bonus_value__isnull=False).exclude(bonus_value=''):
                if record.bonus_value:
                    # 提取金额（支持 $12.50, 12.50, $50 等格式）
                    match = re.search(r'[\d.]+', str(record.bonus_value))
                    if match:
                        try:
                            amount = float(match.group())
                            total_amount += amount
                            success_count += 1
                        except ValueError:
                            pass
            
            # 添加到响应上下文
            if response and hasattr(response, 'context_data'):
                response.context_data['total_amount'] = total_amount
                response.context_data['success_count'] = success_count
                response.context_data['total_records'] = filtered_qs.count()
        except Exception as e:
            # 如果出错，设置默认值
            import traceback
            traceback.print_exc()
            if response and hasattr(response, 'context_data'):
                response.context_data['total_amount'] = 0
                response.context_data['success_count'] = 0
                response.context_data['total_records'] = 0
            # 如果 response 还没有创建，重新调用父类方法
            if response is None:
                response = super().changelist_view(request, extra_context=extra_context)
        finally:
            # 恢复原始的 get_queryset 方法
            self.get_queryset = original_get_queryset
        
        return response
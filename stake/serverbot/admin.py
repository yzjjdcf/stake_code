import csv
import json
import threading  # 必须导入，否则 re_warmup 会报错
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from .models import StakeAccount, ProxyPool, CodeRecord, ClaimRecord
from .forms import ProxyImportForm
from .utils import run_pre_logic  # 确保导入了你的核心逻辑
from django.utils.safestring import mark_safe
import urllib.parse  # 必须写全，才能直接使用 urllib.parse.urlparse

# 1. 代理池管理：只管理代理地址和导入功能
@admin.register(ProxyPool)
class ProxyPoolAdmin(ModelAdmin):
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
class StakeAccountAdmin(ModelAdmin):
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
                    <button type="button" class="button" 
                        onclick="runWarmup({obj.id}, '{obj.username}')"
                        style="background-color: #28a745; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">
                        🔄 强制更新 CF
                    </button>
                    <script>
                    if (typeof runWarmup === 'undefined') {{
                        window.runWarmup = function(id, name) {{
                            // 这里删除了原来的 confirm 弹窗判断，直接发送请求
                            const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

                            fetch('/admin/serverbot/stakeaccount/' + id + '/run-warmup/', {{
                                method: 'POST',
                                headers: {{'X-CSRFToken': csrftoken}}
                            }}).then(res => {{
                                if (res.ok) {{
                                    // 依然保留一个简单的成功提示，让你知道任务已经后台启动了
                                    console.log('🚀 ' + name + ' 过盾任务已提交');
                                    location.reload(); 
                                }}
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
        ]
        return custom_urls + urls

    # 4. 按钮点击后的处理逻辑
    def run_warmup_view(self, request, account_id):
        account = self.get_object(request, account_id)
        if account:
            # 开启后台线程，执行 pre.py 的原始逻辑
            threading.Thread(target=run_pre_logic, args=(account,), daemon=True).start()
            self.message_user(request, f"🚀 账号 {account.username} 的过盾任务已启动，请观察控制台日志。")
        return redirect('/admin/serverbot/stakeaccount/')


@admin.register(CodeRecord)
class CodeRecordAdmin(admin.ModelAdmin):
    list_display = ('code', 'actual_value', 'is_timeout_trigger', 'created_at')

@admin.register(ClaimRecord)
class ClaimRecordAdmin(admin.ModelAdmin):
    list_display = ('account', 'code', 'status', 'bonus_value', 'response_time_ms', 'is_retry', 'created_at')
    list_filter = ('status', 'created_at')
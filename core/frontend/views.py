from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from urllib.parse import urlencode
from serverbot.models import ClaimRecord
from .models import StakeAccount


def index(request):
    """首页"""
    if request.user.is_authenticated:
        return redirect('frontend:account_list')
    return render(request, 'frontend/index.html')


def register(request):
    """用户注册"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        email = request.POST.get('email', '')
        
        if not username or not password:
            messages.error(request, '用户名和密码不能为空')
            return render(request, 'frontend/register.html')
        
        if password != password_confirm:
            messages.error(request, '两次输入的密码不一致')
            return render(request, 'frontend/register.html')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, '用户名已存在')
            return render(request, 'frontend/register.html')
        
        try:
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email
            )
            messages.success(request, '注册成功，请登录')
            return redirect('frontend:login')
        except Exception as e:
            messages.error(request, f'注册失败: {str(e)}')
            return render(request, 'frontend/register.html')
    
    return render(request, 'frontend/register.html')


def user_login(request):
    """用户登录"""
    if request.user.is_authenticated:
        return redirect('frontend:index')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if not username or not password:
            messages.error(request, '用户名和密码不能为空')
            return render(request, 'frontend/login.html')
        
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            messages.success(request, '登录成功')
            next_url = request.GET.get('next', 'frontend:index')
            return redirect(next_url)
        else:
            messages.error(request, '用户名或密码错误')
            return render(request, 'frontend/login.html')
    
    return render(request, 'frontend/login.html')


@login_required
def user_logout(request):
    """用户退出"""
    from django.contrib.auth import logout
    logout(request)
    messages.success(request, '已退出登录')
    return redirect('frontend:login')


@login_required
def account_list(request):
    """账号列表"""
    accounts = StakeAccount.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'accounts': accounts,
    }
    return render(request, 'frontend/account_list.html', context)


@login_required
@require_http_methods(["POST"])
def account_add(request):
    """添加账号（账号唯一性：同一账号只能属于一个用户，后添加的会删除旧记录）"""
    stake_account_id = request.POST.get('stake_account_id', '').strip()
    is_active = request.POST.get('is_active', 'on') == 'on'  # 默认激活
    
    if not stake_account_id:
        messages.error(request, '账号ID不能为空')
        return redirect('frontend:account_list')
    
    # 检查当前用户是否已存在该账号
    existing_account = StakeAccount.objects.filter(user=request.user, stake_account_id=stake_account_id).first()
    if existing_account:
        # 如果当前用户已有该账号，只更新激活状态
        old_is_active = existing_account.is_active
        existing_account.is_active = is_active
        existing_account.save()
        
        # 如果激活状态改变，断开该账号的所有连接
        if old_is_active != is_active:
            from core.listener_tdlib import disconnect_account_connections_sync
            disconnect_count = disconnect_account_connections_sync(
                stake_account_id,
                "账号激活状态已变更" if is_active else "账号已停用"
            )
            if disconnect_count > 0:
                messages.info(request, f'账号 {stake_account_id} 状态已更新，已断开 {disconnect_count} 个连接')
        
        messages.success(request, f'账号 {stake_account_id} 已存在，已更新激活状态')
        return redirect('frontend:account_list')
    
    # 检查其他用户是否已有该账号，如果有则删除（确保账号唯一性）
    other_accounts = StakeAccount.objects.filter(stake_account_id=stake_account_id).exclude(user=request.user)
    if other_accounts.exists():
        deleted_count = other_accounts.count()
        # 在删除前，先断开该账号的所有连接（因为账号归属已变更）
        from core.listener_tdlib import disconnect_account_connections_sync
        disconnect_count = disconnect_account_connections_sync(
            stake_account_id,
            "账号归属已变更"
        )
        other_accounts.delete()
        if disconnect_count > 0:
            messages.info(request, f'账号 {stake_account_id} 已从 {deleted_count} 个其他用户下移除，已断开 {disconnect_count} 个连接，现在归属于您')
        else:
            messages.info(request, f'账号 {stake_account_id} 已从 {deleted_count} 个其他用户下移除，现在归属于您')
    
    # 创建账号
    StakeAccount.objects.create(
        user=request.user,
        stake_account_id=stake_account_id,
        is_active=is_active
    )
    
    messages.success(request, f'账号 {stake_account_id} 添加成功')
    return redirect('frontend:account_list')


@login_required
@require_http_methods(["POST"])
def account_delete(request, account_id):
    """删除账号"""
    account = get_object_or_404(StakeAccount, id=account_id, user=request.user)
    stake_account_id = account.stake_account_id
    
    # 在删除前，先断开该账号的所有连接
    from core.listener_tdlib import disconnect_account_connections_sync
    disconnect_count = disconnect_account_connections_sync(
        stake_account_id,
        "账号已删除"
    )
    
    account.delete()
    
    if disconnect_count > 0:
        messages.success(request, f'账号 {stake_account_id} 已删除，已断开 {disconnect_count} 个连接')
    else:
        messages.success(request, f'账号 {stake_account_id} 已删除')
    return redirect('frontend:account_list')


@login_required
@require_http_methods(["POST"])
def account_toggle_active(request, account_id):
    """切换账号激活状态"""
    account = get_object_or_404(StakeAccount, id=account_id, user=request.user)
    old_is_active = account.is_active
    account.is_active = not account.is_active
    account.save()
    
    # 如果账号被停用，断开该账号的所有连接
    if not account.is_active:
        from core.listener_tdlib import disconnect_account_connections_sync
        disconnect_count = disconnect_account_connections_sync(
            account.stake_account_id,
            "账号已停用"
        )
        return JsonResponse({
            'success': True,
            'is_active': account.is_active,
            'disconnect_count': disconnect_count
        })
    
    return JsonResponse({'success': True, 'is_active': account.is_active})


@login_required
def balance(request):
    """余额查询"""
    # TODO: 第一阶段仅显示，后续添加余额模型和充值功能
    # 暂时显示提示信息
    context = {}
    return render(request, 'frontend/balance.html', context)


@login_required
@never_cache
def billing_list(request):
    """领取记录（只显示自己的）"""
    from django.db.models import Q, Sum, Count
    from datetime import datetime
    from django.utils import timezone
    
    # 筛选逻辑：优先通过 user_flag 关联老数据，同时也要包含新数据（通过 user 字段）
    user_flag = None
    if hasattr(request.user, 'profile') and request.user.profile.user_flag:
        user_flag = request.user.profile.user_flag
    
    # 构建基础查询条件：老数据通过 user_flag，新数据通过 user
    base_query = Q()
    if user_flag:
        base_query |= Q(user_flag=user_flag)  # 老数据
    base_query |= Q(user=request.user)  # 新数据
    
    # 获取所有记录（用于获取筛选选项）
    all_records = ClaimRecord.objects.filter(base_query)
    
    # 获取筛选参数
    filter_code = request.GET.get('code', '').strip()
    filter_username = request.GET.get('username', '').strip()
    filter_status = request.GET.get('status', '').strip()
    filter_bonus_amount = request.GET.get('bonus_amount', '').strip()
    filter_start_date = request.GET.get('start_date', '').strip()
    filter_end_date = request.GET.get('end_date', '').strip()
    
    # 应用筛选条件
    records = all_records
    if filter_code:
        records = records.filter(code__icontains=filter_code)
    if filter_username:
        records = records.filter(username__icontains=filter_username)
    if filter_status:
        records = records.filter(status=filter_status)
    if filter_bonus_amount:
        try:
            bonus_int = int(filter_bonus_amount)
            # 筛选奖金整数部分等于指定值
            records = records.filter(bonus_amount__gte=bonus_int, bonus_amount__lt=bonus_int+1)
        except ValueError:
            pass
    if filter_start_date:
        try:
            start_date = datetime.strptime(filter_start_date, '%Y-%m-%d').date()
            # USE_TZ = False，使用普通datetime（非时区感知）
            start_datetime = datetime.combine(start_date, datetime.min.time())
            records = records.filter(created_at__gte=start_datetime)
        except ValueError:
            pass
    if filter_end_date:
        try:
            end_date = datetime.strptime(filter_end_date, '%Y-%m-%d').date()
            # 结束日期包含当天的23:59:59，USE_TZ = False，使用普通datetime（非时区感知）
            end_datetime = datetime.combine(end_date, datetime.max.time())
            records = records.filter(created_at__lte=end_datetime)
        except ValueError:
            pass
    
    records = records.order_by('-created_at')
    
    # 获取筛选选项（去重）
    # 注意：all_records 已经通过 base_query 筛选，只包含当前用户的记录
    # （如果用户有 user_flag，则包含 user_flag 匹配的记录；同时包含 user 匹配的记录）
    
    # 代码列表（去重）- 只包含当前用户的代码
    code_list = sorted(set(
        all_records.exclude(code__isnull=True).exclude(code='').values_list('code', flat=True).distinct()
    ))
    
    # 账号列表（去重）- 只包含当前用户的账号（基于 user_flag 或 user 字段）
    username_list = sorted(set(
        all_records.exclude(username__isnull=True).exclude(username='').values_list('username', flat=True).distinct()
    ))
    
    # 状态选项（使用模型定义的状态）
    status_list = ClaimRecord.STATUS_CHOICES
    
    # 奖金整数列表（去重，取bonus_amount的整数部分）
    bonus_amount_list = sorted(set([
        int(bonus) for bonus in 
        all_records.exclude(bonus_amount__isnull=True).values_list('bonus_amount', flat=True).distinct()
        if bonus is not None
    ]), reverse=True)
    
    # 分页
    from django.core.paginator import Paginator
    paginator = Paginator(records, 50)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 计算页码范围（最多显示10个页码）
    num_pages = paginator.num_pages
    current_page = page_obj.number
    max_pages_to_show = 10
    
    if num_pages <= max_pages_to_show:
        # 如果总页数少于等于10，显示所有页码
        page_range = list(range(1, num_pages + 1))
    else:
        # 如果总页数大于10，显示当前页周围的页码
        if current_page <= 5:
            # 当前页在前5页，显示前10页
            page_range = list(range(1, max_pages_to_show + 1))
        elif current_page >= num_pages - 4:
            # 当前页在后5页，显示后10页
            page_range = list(range(num_pages - max_pages_to_show + 1, num_pages + 1))
        else:
            # 当前页在中间，显示当前页前后各5页（总共10页）
            page_range = list(range(current_page - 4, current_page + 6))
    
    # 构建筛选参数（用于分页链接）
    filter_params = {}
    if filter_code:
        filter_params['code'] = filter_code
    if filter_username:
        filter_params['username'] = filter_username
    if filter_status:
        filter_params['status'] = filter_status
    if filter_bonus_amount:
        filter_params['bonus_amount'] = filter_bonus_amount
    if filter_start_date:
        filter_params['start_date'] = filter_start_date
    if filter_end_date:
        filter_params['end_date'] = filter_end_date
    
    # 生成URL参数字符串（用于分页链接）
    filter_query_string = urlencode(filter_params) if filter_params else ''
    
    # 统计信息（基于筛选后的记录）
    stats = records.filter(status='claim_success').aggregate(
        total_amount=Sum('bonus_amount'),
        success_count=Count('id')
    )
    
    total_count = records.count()
    success_count = stats['success_count'] or 0
    total_amount = float(stats['total_amount'] or 0)
    
    context = {
        'page_obj': page_obj,
        'page_range': page_range,
        'filter_params': filter_params,
        'filter_query_string': filter_query_string,
        'filter_code': filter_code,
        'filter_username': filter_username,
        'filter_status': filter_status,
        'filter_bonus_amount': filter_bonus_amount,
        'filter_start_date': filter_start_date,
        'filter_end_date': filter_end_date,
        'code_list': code_list,
        'username_list': username_list,
        'status_list': status_list,
        'bonus_amount_list': bonus_amount_list,
        'total_count': total_count,
        'success_count': success_count,
        'total_amount': total_amount,
    }
    return render(request, 'frontend/billing_list.html', context)


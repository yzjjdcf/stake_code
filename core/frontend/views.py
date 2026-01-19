from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
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
    """添加账号"""
    stake_account_id = request.POST.get('stake_account_id', '').strip()
    is_active = request.POST.get('is_active', 'on') == 'on'  # 默认激活
    
    if not stake_account_id:
        messages.error(request, '账号ID不能为空')
        return redirect('frontend:account_list')
    
    # 检查是否已存在
    if StakeAccount.objects.filter(user=request.user, stake_account_id=stake_account_id).exists():
        messages.error(request, '该账号已存在')
        return redirect('frontend:account_list')
    
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
    account.delete()
    
    messages.success(request, f'账号 {stake_account_id} 已删除')
    return redirect('frontend:account_list')


@login_required
@require_http_methods(["POST"])
def account_toggle_active(request, account_id):
    """切换账号激活状态"""
    account = get_object_or_404(StakeAccount, id=account_id, user=request.user)
    account.is_active = not account.is_active
    account.save()
    
    return JsonResponse({'success': True, 'is_active': account.is_active})


@login_required
def balance(request):
    """余额查询"""
    # TODO: 第一阶段仅显示，后续添加余额模型和充值功能
    # 暂时显示提示信息
    context = {}
    return render(request, 'frontend/balance.html', context)


@login_required
def billing_list(request):
    """领取记录（只显示自己的）"""
    # 筛选逻辑：优先通过 user_flag 关联老数据，同时也要包含新数据（通过 user 字段）
    user_flag = None
    if hasattr(request.user, 'profile') and request.user.profile.user_flag:
        user_flag = request.user.profile.user_flag
    
    # 构建查询条件：老数据通过 user_flag，新数据通过 user
    from django.db.models import Q
    query = Q()
    if user_flag:
        query |= Q(user_flag=user_flag)  # 老数据
    query |= Q(user=request.user)  # 新数据
    
    records = ClaimRecord.objects.filter(query).order_by('-created_at')
    
    # 分页
    from django.core.paginator import Paginator
    paginator = Paginator(records, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 统计信息
    from django.db.models import Sum, Count
    stats = records.filter(status='claim_success').aggregate(
        total_amount=Sum('bonus_amount'),
        success_count=Count('id')
    )
    
    total_count = records.count()
    success_count = stats['success_count'] or 0
    total_amount = float(stats['total_amount'] or 0)
    
    context = {
        'page_obj': page_obj,
        'total_count': total_count,
        'success_count': success_count,
        'total_amount': total_amount,
    }
    return render(request, 'frontend/billing_list.html', context)


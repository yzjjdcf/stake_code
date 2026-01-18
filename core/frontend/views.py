from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from django.utils import timezone
from serverbot.models import ClaimRecord


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
    """账号列表（第一阶段：仅查看）"""
    # TODO: 第一阶段仅显示，后续添加账号管理功能
    # 暂时显示该用户的所有领取记录中的账号
    accounts = ClaimRecord.objects.filter(user_id=str(request.user.id)).values('username').distinct()
    
    context = {
        'accounts': accounts,
    }
    return render(request, 'frontend/account_list.html', context)


@login_required
def balance(request):
    """余额查询"""
    # TODO: 第一阶段仅显示，后续添加余额模型和充值功能
    # 暂时显示提示信息
    context = {}
    return render(request, 'frontend/balance.html', context)


@login_required
def billing_list(request):
    """账单查询（只显示自己的）"""
    user_id = str(request.user.id)
    records = ClaimRecord.objects.filter(user_id=user_id).order_by('-created_at')
    
    # 分页
    from django.core.paginator import Paginator
    paginator = Paginator(records, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 统计信息
    total_count = records.count()
    success_count = records.filter(status='claim_success').count()
    
    context = {
        'page_obj': page_obj,
        'total_count': total_count,
        'success_count': success_count,
    }
    return render(request, 'frontend/billing_list.html', context)


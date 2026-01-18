from django.urls import path
from . import views

app_name = 'frontend'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.user_login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.user_logout, name='logout'),
    path('accounts/', views.account_list, name='account_list'),
    path('balance/', views.balance, name='balance'),
    path('billing/', views.billing_list, name='billing_list'),
]


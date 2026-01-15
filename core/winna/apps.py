from django.apps import AppConfig


class WinnaConfig(AppConfig):
    name = 'winna'
    default_auto_field = 'django.db.models.BigAutoField'
    verbose_name = 'Winna 业务'
    
    def ready(self):
        """应用启动时调用"""
        import winna.models  # 确保信号被注册


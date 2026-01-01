from django.apps import AppConfig


class ServerbotConfig(AppConfig):
    name = 'serverbot'
    default_auto_field = 'django.db.models.BigAutoField'
    
    def ready(self):
        """应用启动时调用，确保信号被注册"""
        import serverbot.models  # 确保信号被注册

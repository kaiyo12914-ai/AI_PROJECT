# tts/apps.py
from django.apps import AppConfig

class TtsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'webapps.tts'  # 這裏必須與你的路徑匹配!
    label = "tts"
    def ready(self):
         pass
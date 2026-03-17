from django.apps import AppConfig

class DocConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webapps.doc"
    label = "doc"   # ✅ 固定 app label，migration 依賴用這個最穩

from django.urls import path
from . import views

urlpatterns = [
    path("", views.page, name="rag_oracle_page"),          # ✅ /rag/
    path("health/", views.health, name="rag_oracle_health"),# ✅ /rag/health/
    path("ask/", views.api_ask, name="rag_oracle_ask"),     # ✅ /rag/ask/
]

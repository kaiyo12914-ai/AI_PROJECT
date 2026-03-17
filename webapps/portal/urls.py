# webapps/portal/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    # =========================================================
    # Portal Home
    # =========================================================
    path("", views.index, name="home"),  # 供 include(namespace) 使用：portal:home

    # =========================================================
    # Who am I (debug)
    # - 用於反代 prefix / header / login 驗證
    # =========================================================
    path("whoami/", views.whoami, name="whoami"),

    # =========================================================
    # Usage logs
    # =========================================================
    path("usage/", views.usage_log_page, name="usage_page"),
    path("usage/whoami/", views.usage_whoami_page, name="usage_whoami"),
    path("usage/user_acl/", views.usage_user_acl_page, name="usage_user_acl"),

    # ✅ 建議帶尾斜線：避免在 /comment 前綴或相對路徑時組 URL 出現歧義
    # （前端也較容易用 {% url 'portal:usage_export_xlsx' %}）
    path("usage/export.xlsx/", views.usage_log_export_xlsx, name="usage_export_xlsx"),
]

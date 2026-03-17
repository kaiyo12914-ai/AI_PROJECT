# webapps/comment/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "comment"

urlpatterns = [
    # ============================================================
    # Pages
    # ============================================================
    path("", views.index, name="page_index"),

    # ============================================================
    # APIs (comment only)
    # - 規範：Django app 內 url 不得包含反代 prefix（/djangoai）
    # - 規範：也不得手動加 node 前綴（/comment）；node 前綴由專案總路由掛載負責
    # - 規範：API view 必須 @require_node("comment", api=True)
    # ============================================================
    path("api/generate_comment/", views.api_generate_comment, name="api_generate_comment"),
]

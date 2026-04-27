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
    # - 規範：Django app 内 url 不得包含反代 prefix（/djangoai）
    # - 規範：也不得手動加 node 前綴（/comment）；node 前綴由專案總路由掛載負責
    # ============================================================
    path("api/generate_comment/", views.api_generate_comment, name="api_generate_comment"),
    path("api/get_evaluations/", views.api_get_evaluations, name="api_get_evaluations"),
    path("api/delete_evaluation/<int:evaluation_id>/", views.api_delete_evaluation, name="api_delete_evaluation"),
]

# webapps/meetingreply/urls.py
from __future__ import annotations

from django.urls import path
from . import views

app_name = "meetingreply"

urlpatterns = [
    path("", views.index, name="page"),
    path("api/todo_list/", views.todo_list, name="todo_list"),
    path("api/rag_only/", views.rag_only, name="rag_only"),
    path("api/build_reply/", views.build_reply, name="build_reply"),
]

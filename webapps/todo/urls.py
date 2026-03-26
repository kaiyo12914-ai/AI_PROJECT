from django.urls import path

from . import views

urlpatterns = [
    path("", views.todo_page, name="todo_page"),
    path("fetch/", views.api_fetch_todos, name="todo_fetch"),
    path("plan/", views.api_plan_tasks, name="todo_plan"),
]


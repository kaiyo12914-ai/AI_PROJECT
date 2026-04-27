from django.urls import path

from . import views

app_name = "englishchat"

urlpatterns = [
    path("", views.index, name="page"),
    path("start/", views.api_start, name="start"),
    path("chat/", views.api_chat, name="chat"),
]


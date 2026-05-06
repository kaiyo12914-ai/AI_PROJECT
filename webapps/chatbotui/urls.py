from django.urls import path

from . import views

app_name = "chatbotui"

urlpatterns = [
    path("", views.index, name="page"),
    path("conversations/", views.api_conversations, name="conversations"),
    path("conversations/<str:conversation_id>/", views.api_conversation_detail, name="conversation_detail"),
    path("conversations/<str:conversation_id>/clear/", views.api_conversation_clear, name="conversation_clear"),
    path("chat/", views.api_chat, name="chat"),
]

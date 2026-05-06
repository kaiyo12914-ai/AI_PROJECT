from django.urls import path

from . import views

app_name = "chatbotui"

urlpatterns = [
    path("", views.index, name="page"),
    path("conversations/", views.api_conversations, name="conversations"),
    path("conversations/<str:conversation_id>/", views.api_conversation_detail, name="conversation_detail"),
    path("conversations/<str:conversation_id>/clear/", views.api_conversation_clear, name="conversation_clear"),
    path("conversations/<str:conversation_id>/rename/", views.api_conversation_rename, name="conversation_rename"),
    path("conversations/<str:conversation_id>/model/", views.api_conversation_model, name="conversation_model"),
    path("conversations/<str:conversation_id>/config/", views.api_conversation_config, name="conversation_config"),
    path("conversations/<str:conversation_id>/config/reset-profile/", views.api_conversation_config_reset_profile, name="conversation_config_reset_profile"),
    path("conversations/<str:conversation_id>/prompt-history/", views.api_conversation_prompt_history, name="conversation_prompt_history"),
    path("conversations/<str:conversation_id>/attachments/", views.api_conversation_attachments, name="conversation_attachments"),
    path("chat/", views.api_chat, name="chat"),
    path("chat/regenerate/", views.api_chat_regenerate, name="chat_regenerate"),
    path("chat/resend/", views.api_chat_resend, name="chat_resend"),
    path("ollama/tags/", views.api_ollama_tags, name="ollama_tags"),
]

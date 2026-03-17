# webapps/llm/urls.py
from django.urls import path
from webapps.llm.views import chat, translate

urlpatterns = [
    path("chat/", chat, name="chat"),
    path("translate/", translate, name="translate"),
]

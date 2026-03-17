# webapps/translator/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="translator_page"),
    path("parse/", views.api_parse_attachments, name="translator_parse"),
    path("templates/", views.api_templates, name="translator_templates"),
    path("generate/", views.api_generate_doc_prompt, name="translator_generate"),
    path("tts/", views.generate_comment_tts, name="translator_tts"),
]

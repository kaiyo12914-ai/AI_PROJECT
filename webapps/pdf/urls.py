from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="pdf_page"),
    path("extract/", views.api_extract_text),
    path("summary/", views.api_summary),
    path("download/txt/", views.api_download_txt),
    path("download/docx/", views.api_download_docx),
]

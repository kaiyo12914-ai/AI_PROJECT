from django.urls import path

from . import views

app_name = "document_formalize"

urlpatterns = [
    path("", views.page_index, name="page"),
    path("api/document/formalize/", views.api_formalize, name="api_formalize"),
    path("api/document/formalize/history/", views.api_history, name="api_history"),
    path("api/document/formalize/export/", views.api_export, name="api_export"),
    path("api/document/formalize/template-list/", views.api_template_list, name="api_template_list"),
]


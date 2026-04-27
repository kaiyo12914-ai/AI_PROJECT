from django.urls import path

from . import views

app_name = "projectnotes"

urlpatterns = [
    path("", views.index, name="page"),
    path("manage/", views.manage_page, name="manage"),
    path("audit_logs/", views.api_audit_logs, name="audit_logs"),
    path("metrics_api/", views.api_metrics, name="metrics_api"),
    path("projects/", views.api_projects, name="projects"),
    path("digests/", views.api_digests, name="digests"),
    path("sources/", views.api_sources, name="sources"),
    path("sources/<int:source_id>/", views.api_source_delete, name="source_delete"),
    path("sources/versions/", views.api_source_versions, name="source_versions"),
    path("sources/<int:source_id>/content/", views.api_source_content, name="source_content"),
    path("sources/<int:source_id>/toggle/", views.api_source_toggle, name="source_toggle"),
    path("sources/<int:source_id>/resync/", views.api_source_resync, name="source_resync"),
    path("conversations/", views.api_conversations, name="conversations"),
    path("chat/", views.api_chat, name="chat"),
    path("citation_click/", views.api_citation_click, name="citation_click"),
    path("citation/", views.api_citation_context, name="citation_context"),
    path("overview/", views.api_overview, name="overview"),
]

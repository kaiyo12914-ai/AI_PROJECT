from __future__ import annotations

from django.urls import path

from webapps.vanna import api
from webapps.vanna import views


app_name = "nl2sql"

urlpatterns = [
    path("", views.page_index, name="page"),
    path("api/status/", api.status_api, name="api_status"),
    path("api/schema/sync/", api.schema_sync_api, name="api_schema_sync"),
    path("api/vanna/sync-training/", api.training_sync_api, name="api_training_sync"),
    path("api/generate/", api.generate_api, name="api_generate"),
    path("api/execute/", api.execute_api, name="api_execute"),
]

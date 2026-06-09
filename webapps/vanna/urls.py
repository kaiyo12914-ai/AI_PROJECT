from __future__ import annotations

from django.urls import path

from webapps.vanna import api
from webapps.vanna import views


app_name = "nl2sql"

urlpatterns = [
    path("", views.page_index, name="page"),
    path("api/status/", api.status_api, name="api_status"),
    path("api/schema/sync/", api.schema_sync_api, name="api_schema_sync"),
    path("api/schema/search/", api.schema_search_api, name="api_schema_search"),
    path("api/vanna/sync-training/", api.training_sync_api, name="api_training_sync"),
    path("api/vanna/training-dataset/", api.training_dataset_api, name="api_training_dataset"),
    path("api/vanna/admin-sql-execute/", api.admin_sql_execute_api, name="api_admin_sql_execute"),
    path("api/generate/", api.generate_api, name="api_generate"),
    path("api/execute/", api.execute_api, name="api_execute"),
    path("api/query-logs/", api.query_logs_api, name="api_query_logs"),
    path("api/review/create/", api.review_create_api, name="api_review_create"),
]

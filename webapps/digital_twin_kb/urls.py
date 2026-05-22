from django.urls import include, path
from rest_framework.routers import DefaultRouter

from webapps.digital_twin_kb.views import (
    AskView,
    DigitalTwinCategoryViewSet,
    DirectIngestTextView,
    DocumentViewSet,
    IngestDocsView,
    IngestQALogView,
    IngestionJobViewSet,
    QALogViewSet,
    UploadDocumentView,
    health,
    page_index,
)

app_name = "digital_twin_kb"

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="documents")
router.register("categories", DigitalTwinCategoryViewSet, basename="categories")
router.register("qa-logs", QALogViewSet, basename="qa-logs")
router.register("ingestion-jobs", IngestionJobViewSet, basename="ingestion-jobs")

urlpatterns = [
    path("", page_index, name="page"),
    path("api/health/", health, name="health"),
    path("api/ingest/", IngestDocsView.as_view(), name="ingest"),
    path("api/ingest-qa-log/", IngestQALogView.as_view(), name="ingest-qa-log"),
    path("api/direct-ingest-text/", DirectIngestTextView.as_view(), name="direct-ingest-text"),
    path("api/upload/", UploadDocumentView.as_view(), name="upload"),
    path("api/ask/", AskView.as_view(), name="ask"),
    path("api/", include(router.urls)),
]

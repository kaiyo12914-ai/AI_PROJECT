import platform

from django.conf import settings
from django.utils.decorators import method_decorator
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from webapps.portal.decorators import require_node
from webapps.digital_twin_kb.models import DigitalTwinCategory, Document, IngestionJob, QALog
from webapps.digital_twin_kb.serializers import (
    DigitalTwinCategorySerializer,
    DocumentChunkSerializer,
    DocumentSerializer,
    IngestionJobSerializer,
    QALogSerializer,
)
from webapps.digital_twin_kb.services.ingestion_service import ingest_docs_folder, ingest_uploaded_file
from webapps.digital_twin_kb.services.rag_engine import ask


@api_view(["GET"])
@require_node("digital_twin_kb", api=True)
def health(request):
    return Response(
        {
            "status": "ok",
            "database": "configured",
            "vector_store": "pgvector",
            "framework": "Django REST Framework",
            "python_version": platform.python_version(),
            "embedding_model": settings.DIGITAL_TWIN_KB_EMBEDDING_MODEL,
        }
    )


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class IngestDocsView(APIView):
    def post(self, request):
        job = ingest_docs_folder(
            triggered_by=request.data.get("triggered_by", "system"),
            triggered_by_type=request.data.get("triggered_by_type", "system"),
            security_level=int(request.data.get("security_level", 1)),
        )
        return Response(IngestionJobSerializer(job).data)


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class UploadDocumentView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        document = ingest_uploaded_file(
            uploaded,
            uploaded_by=request.data.get("uploaded_by", ""),
            uploaded_by_type=request.data.get("uploaded_by_type", "user"),
            topic=request.data.get("topic", ""),
            security_level=int(request.data.get("security_level", 1)),
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class AskView(APIView):
    def post(self, request):
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        asker_id = request.data.get("asker_id", "")
        if not asker_id and request.user and request.user.is_authenticated:
            asker_id = request.user.username
        else:
            asker_id = asker_id or "anonymous"

        result = ask(
            question=question,
            asker_type=request.data.get("asker_type", "user"),
            asker_id=asker_id,
            top_k=request.data.get("top_k"),
            user_security_level=int(request.data.get("user_security_level", 1)),
            filters=request.data.get("filters") or {},
        )
        return Response(result)


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class DocumentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Document.objects.all().order_by("-created_at")
    serializer_class = DocumentSerializer
    lookup_field = "document_id"

    @action(detail=True, methods=["get"])
    def chunks(self, request, document_id=None):
        document = self.get_object()
        return Response(DocumentChunkSerializer(document.chunks.all(), many=True).data)


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class DigitalTwinCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DigitalTwinCategory.objects.all().order_by("twin_level")
    serializer_class = DigitalTwinCategorySerializer


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class QALogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = QALog.objects.all().order_by("-created_at")
    serializer_class = QALogSerializer


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class IngestionJobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionJob.objects.all().order_by("-created_at")
    serializer_class = IngestionJobSerializer


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class IngestQALogView(APIView):
    def post(self, request):
        query_id = request.data.get("query_id")
        if not query_id:
            return Response({"error": "query_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            log = QALog.objects.get(query_id=query_id)
            from webapps.digital_twin_kb.services.rag_engine import _save_ai_answer_to_kb
            _save_ai_answer_to_kb(log.user_question, log.answer)
            return Response({"status": "success", "message": "成功將對話紀錄手動回存至知識庫中！"})
        except QALog.DoesNotExist:
            return Response({"error": "對話紀錄不存在"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.shortcuts import render
from django.middleware.csrf import get_token

@require_node("digital_twin_kb")
def page_index(request):
    return render(
        request,
        "digital_twin_kb/index.html",
        {
            "csrf_token": get_token(request),
        },
    )

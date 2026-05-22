import platform

from django.conf import settings
from django.utils.decorators import method_decorator
from rest_framework import status, viewsets, mixins
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
class QALogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
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


@method_decorator(require_node("digital_twin_kb", api=True), name="dispatch")
class DirectIngestTextView(APIView):
    def post(self, request):
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from webapps.digital_twin_kb.models import Document, DocumentChunk
            from webapps.digital_twin_kb.services.embedding_service import embed_text
            from django.db.models import Max
            import logging
            logger = logging.getLogger("django")

            import hashlib
            # 計算這段文字的 MD5 作為唯一的 checksum，防重覆錄入，且讓每次不同的錄入在資產庫顯示為獨立一列
            text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
            checksum = f"user_direct_checksum_{text_hash}"
            display_name = text[:20].replace("\n", " ") + ("..." if len(text) > 20 else "")

            # 獲取或建立特殊的「使用者直接錄入」虛擬文件
            user_doc, _ = Document.objects.get_or_create(
                checksum=checksum,
                defaults={
                    "file_name": f"user_direct_{text_hash[:8]}.txt",
                    "original_file_name": f"手動錄入: {display_name}",
                    "file_type": "txt",
                    "file_path": "user_direct_kb",
                    "file_size": len(text),
                    "source": "USER_INPUT",
                    "uploaded_by": "user",
                    "uploaded_by_type": "user",
                    "topic": "User Direct Input",
                    "security_level": 1,
                }
            )

            # 取得下一個 chunk_index
            max_idx = user_doc.chunks.aggregate(Max("chunk_index"))["chunk_index__max"]
            chunk_index = (max_idx or 0) + 1

            # 組裝具有標記的內容
            content = f"使用者直接錄入知識：\n{text}"
            embedding = embed_text(content)

            DocumentChunk.objects.create(
                document=user_doc,
                chunk_index=chunk_index,
                content=content,
                page_number=1,
                section_title="User Direct Knowledge",
                twin_level="",
                isa95_level="",
                system_type="",
                topic="User Direct Input",
                security_level=1,
                embedding=embedding,
                token_count=len(content) // 4,
            )

            # 更新 Document 大小
            user_doc.file_size = len(content)
            user_doc.save()
            logger.info(f"[USER DIRECT INGEST] Successfully saved user chunk #{chunk_index} for doc checksum {checksum[:12]}")
            return Response({"status": "success", "message": "成功將輸入的文字直接作為知識存入 RAG 資料庫！"})
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

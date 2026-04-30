import json
import logging
import traceback
import threading
from django.db import ProgrammingError
from django.utils import timezone
from .models import ProcessingJob, Source, Document, DocumentVersion, DocumentChunk
from .text_processing import decode_text_bytes_best_effort, preprocess_rag_text, build_chunks
from .embedding_service import get_embedding

logger = logging.getLogger(__name__)

def process_source_upload_task(job_id: int, project_id: int, title: str, file_name: str, file_name_lower: str, file_content: bytes, uploader_username: str):
    """
    Background task to process file upload, extract text, chunk, and embed.
    """
    try:
        job = ProcessingJob.objects.get(id=job_id)
    except ProcessingJob.DoesNotExist:
        logger.error(f"ProcessingJob {job_id} not found.")
        return

    job.status = "processing"
    job.progress_info = "Extracting text..."
    job.save(update_fields=["status", "progress_info", "updated_at"])

    raw_text = ""
    detected_encoding = "utf-8"
    is_non_utf8 = False

    try:
        # NOTE: File extraction logic ported from views.py
        if file_name_lower.endswith(".pdf"):
            import io
            from webapps.pdf.views import _extract_pdf_text_auto
            # Fake upload file object
            class FakeUpload:
                def __init__(self, content):
                    self.content = content
                def read(self):
                    return self.content
                def seek(self, *args):
                    pass
            raw_text, _ = _extract_pdf_text_auto(FakeUpload(file_content))
            detected_encoding = "extracted"
        elif file_name_lower.endswith(".docx"):
            import docx
            import io
            d = docx.Document(io.BytesIO(file_content))
            raw_text = "\n".join([p.text for p in d.paragraphs])
            detected_encoding = "extracted"
        elif file_name_lower.endswith((".xlsx", ".xls")):
            import pandas as pd
            import io
            dfs = pd.read_excel(io.BytesIO(file_content), sheet_name=None)
            parts = []
            for sheet, df in dfs.items():
                parts.append(f"--- Sheet: {sheet} ---")
                parts.append(df.to_csv(index=False, sep='\t'))
            raw_text = "\n".join(parts)
            detected_encoding = "extracted"
        else:
            raw_text, detected_encoding = decode_text_bytes_best_effort(file_content)
            is_non_utf8 = detected_encoding not in ("utf-8", "utf-8-sig")

        # Ensure no NUL bytes before database insertion
        raw_text = raw_text.replace("\x00", "").replace("\u0000", "")
        cleaned_text = preprocess_rag_text(raw_text)

        if not cleaned_text:
            raise ValueError("Empty or unreadable content after preprocessing")

        job.progress_info = "Creating document records..."
        job.save(update_fields=["progress_info", "updated_at"])

        source = Source.objects.create(project_id=project_id, name=title, source_type="text")
        doc = Document.objects.create(source=source, title=title, path=file_name)
        doc_version = DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            raw_text=cleaned_text,
            uploaded_by=uploader_username,
        )
        job.target_id = source.id
        job.save(update_fields=["target_id", "updated_at"])

        job.progress_info = "Chunking text..."
        job.save(update_fields=["progress_info", "updated_at"])

        chunks_text = build_chunks(cleaned_text)
        total_chunks = len(chunks_text)
        
        job.progress_info = f"Generating embeddings for {total_chunks} chunks..."
        job.save(update_fields=["progress_info", "updated_at"])

        chunk_objs = []
        for i, text_seg in enumerate(chunks_text):
            emb = get_embedding(text_seg)
            chunk_objs.append(DocumentChunk(
                document_version=doc_version,
                chunk_index=i,
                token_count=len(text_seg),
                content=text_seg,
                embedding=emb
            ))
            
            # Periodically update progress
            if (i + 1) % 10 == 0:
                job.progress_info = f"Embedding {i+1}/{total_chunks} chunks..."
                job.save(update_fields=["progress_info", "updated_at"])

        DocumentChunk.objects.bulk_create(chunk_objs)
        
        from .views import _log_activity
        _log_activity(
            project_id=project_id,
            action="source_upload",
            user_id=uploader_username,
            target_type="source",
            target_id=source.id,
            detail={
                "source_title": getattr(source, "name", "") or title,
                "file_name": file_name,
                "chunk_count": total_chunks,
                "detected_encoding": detected_encoding,
                "is_non_utf8": is_non_utf8,
                "job_id": job.id,
            },
        )

        job.status = "completed"
        job.progress_info = "Completed"
        job.save(update_fields=["status", "progress_info", "updated_at"])

    except Exception as exc:
        logger.error(f"ProcessingJob {job_id} failed: {exc}\n{traceback.format_exc()}")
        job.status = "failed"
        job.error_message = str(exc)
        job.progress_info = "Failed"
        job.save(update_fields=["status", "error_message", "progress_info", "updated_at"])


def start_source_upload_task(project_id: int, title: str, file_name: str, file_name_lower: str, file_content: bytes, uploader_username: str) -> int:
    """Creates a ProcessingJob and starts a background thread."""
    job = ProcessingJob.objects.create(
        project_id=project_id,
        job_type="source_ingestion",
        status="pending",
        progress_info="Queued"
    )
    
    t = threading.Thread(
        target=process_source_upload_task,
        args=(job.id, project_id, title, file_name, file_name_lower, file_content, uploader_username)
    )
    t.daemon = True
    t.start()
    
    return job.id

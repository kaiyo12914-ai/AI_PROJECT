from pathlib import Path
import hashlib
import shutil

from django.conf import settings
from django.db import transaction

from webapps.digital_twin_kb.models import Document, DocumentChunk, IngestionJob
from webapps.digital_twin_kb.services.embedding_service import embed_texts
from webapps.digital_twin_kb.taxonomy.knowledge_schema import classify_text

from .document_loader import SUPPORTED_EXTENSIONS, load_document_text
from .text_cleaner import clean_text
from .text_splitter import split_text


def ingest_docs_folder(triggered_by: str, triggered_by_type: str, security_level: int):
    docs_dir = Path(settings.DIGITAL_TWIN_KB_DOCS_DIR)
    files = [p for p in docs_dir.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    job = IngestionJob.objects.create(
        source_type="docs_folder",
        source_path=str(docs_dir),
        triggered_by=triggered_by,
        triggered_by_type=triggered_by_type,
        status="running",
        total_files=len(files),
    )
    for path in files:
        try:
            ingest_file(path, triggered_by, triggered_by_type, security_level, source="docs_folder")
            job.processed_files += 1
        except Exception as exc:
            job.failed_files += 1
            job.error_message = f"{job.error_message}\n{path}: {exc}".strip()
        job.save(update_fields=["processed_files", "failed_files", "error_message", "updated_at"])
    job.status = "completed" if job.failed_files == 0 else "partial_failed"
    job.save(update_fields=["status", "updated_at"])
    return job


def ingest_uploaded_file(uploaded_file, uploaded_by: str, uploaded_by_type: str, topic: str, security_level: int):
    target_dir = Path(settings.DIGITAL_TWIN_KB_STORAGE_DIR) / "uploads"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / uploaded_file.name
    with target.open("wb") as fh:
        for chunk in uploaded_file.chunks():
            fh.write(chunk)
    return ingest_file(target, uploaded_by, uploaded_by_type, security_level, source="upload", topic=topic)


@transaction.atomic
def ingest_file(path: str | Path, uploaded_by: str, uploaded_by_type: str, security_level: int, source: str, topic: str = ""):
    src = Path(path)
    checksum = _sha256(src)
    stored = Path(settings.DIGITAL_TWIN_KB_STORAGE_DIR) / "documents" / checksum[:2] / src.name
    stored.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != stored.resolve():
        shutil.copy2(src, stored)

    raw_text, _page_meta = load_document_text(stored)
    cleaned = clean_text(raw_text)
    doc_meta = classify_text(cleaned[:4000])
    document, _created = Document.objects.update_or_create(
        checksum=checksum,
        defaults={
            "file_name": stored.name,
            "original_file_name": src.name,
            "file_type": src.suffix.lower().lstrip("."),
            "file_path": str(stored),
            "file_size": stored.stat().st_size,
            "source": source,
            "uploaded_by": uploaded_by,
            "uploaded_by_type": uploaded_by_type,
            "topic": topic or doc_meta["topic"],
            "security_level": security_level,
        },
    )
    document.chunks.all().delete()

    chunks = split_text(cleaned)
    embeddings = embed_texts([c["content"] for c in chunks]) if chunks else []
    objects = []
    for idx, item in enumerate(chunks):
        meta = classify_text(item["content"])
        objects.append(DocumentChunk(
            document=document,
            chunk_index=idx,
            content=item["content"],
            page_number=None,
            section_title=item["section_title"],
            twin_level=meta["twin_level"],
            isa95_level=meta["isa95_level"],
            system_type=meta["system_type"],
            topic=topic or meta["topic"],
            keywords=meta["keywords"],
            security_level=security_level,
            embedding=embeddings[idx],
            token_count=max(1, len(item["content"]) // 2),
        ))
    DocumentChunk.objects.bulk_create(objects)
    return document


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

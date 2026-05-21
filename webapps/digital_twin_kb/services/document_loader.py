from pathlib import Path

import pandas as pd
from docx import Document as DocxDocument
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".xlsx", ".xls"}


def load_document_text(path: str | Path) -> tuple[str, list[dict]]:
    file_path = Path(path)
    ext = file_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")
    if ext == ".pdf":
        return _load_pdf(file_path)
    if ext == ".docx":
        return _load_docx(file_path), []
    if ext in {".txt", ".md", ".markdown"}:
        return file_path.read_text(encoding="utf-8", errors="ignore"), []
    if ext == ".csv":
        return pd.read_csv(file_path).to_csv(index=False), []
    if ext in {".xlsx", ".xls"}:
        sheets = pd.read_excel(file_path, sheet_name=None)
        text = "\n\n".join(f"# {name}\n{df.to_csv(index=False)}" for name, df in sheets.items())
        return text, []
    raise ValueError(f"Unsupported file type: {ext}")


def _load_pdf(path: Path) -> tuple[str, list[dict]]:
    reader = PdfReader(str(path))
    pages = []
    meta = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(text)
        meta.append({"page_number": idx, "text": text})
    return "\n\n".join(pages), meta


def _load_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

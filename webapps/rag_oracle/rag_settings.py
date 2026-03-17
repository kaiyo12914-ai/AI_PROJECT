# webapps/rag_oracle/rag_settings.py
from __future__ import annotations

import logging
import os
import socket
from pathlib import Path

from django.conf import settings as DJ

logger = logging.getLogger("webapps.rag_oracle")


# ============================================================
# Oracle / 文件欄位設定
# ============================================================
DOC_TABLE = getattr(DJ, "RAG_DOC_TABLE", "KB_DOC")
DOC_ID = getattr(DJ, "RAG_DOC_ID_COL", "DOC_ID")
DOC_TYPE = getattr(DJ, "RAG_DOC_TYPE_COL", "DOC_TYPE")
TITLE = getattr(DJ, "RAG_TITLE_COL", "TITLE")
BODY = getattr(DJ, "RAG_BODY_COL", "BODY_CLOB")
UPDATED = getattr(DJ, "RAG_UPDATED_COL", "UPDATED_AT")

DEPT_COL = getattr(DJ, "RAG_DEPT_COL", "")
SEC_COL = getattr(DJ, "RAG_SEC_COL", "")

# ===== Chunk（若有用）=====
CHUNK_TABLE = getattr(DJ, "RAG_CHUNK_TABLE", "KB_CHUNK")
CHUNK_ID = getattr(DJ, "RAG_CHUNK_ID_COL", "CHUNK_ID")
CHUNK_DOC_ID = getattr(DJ, "RAG_CHUNK_DOC_ID_COL", "DOC_ID")
CHUNK_NO = getattr(DJ, "RAG_CHUNK_NO_COL", "CHUNK_NO")
CHUNK_TEXT = getattr(DJ, "RAG_CHUNK_TEXT_COL", "CHUNK_TEXT")
CHUNK_UPDATED = getattr(DJ, "RAG_CHUNK_UPDATED_COL", "UPDATED_AT")


# ============================================================
# helpers
# ============================================================
def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def _setting_str(name: str, default: str = "") -> str:
    v = getattr(DJ, name, default)
    return str(v or default).strip()


def _has_any_file(p: Path) -> bool:
    try:
        return any(p.glob("**/*"))
    except Exception:
        return False


# ============================================================
# Chroma（依規範：RAG 與其他子系統可分離，且不得 import-time 炸全站）
# ============================================================
BASE_DIR = Path(DJ.BASE_DIR)

# ✅ 優先使用 RAG_CHROMA_PERSIST_DIR（避免污染 llm/services.py 的 CHROMA_PERSIST_DIR）
# fallback 依序：CHROMA_PERSIST_DIR → BASE_DIR/chroma
RAG_CHROMA_PERSIST_DIR = _env("RAG_CHROMA_PERSIST_DIR", "")
CHROMA_PERSIST_DIR_ENV = _env("CHROMA_PERSIST_DIR", "")

CHROMA_PERSIST_DIR = Path(
    RAG_CHROMA_PERSIST_DIR
    or CHROMA_PERSIST_DIR_ENV
    or str(BASE_DIR / "chroma")
).resolve()

# ✅ collection：env 優先，否則喫 settings，再不然 default
CHROMA_COLLECTION = _env("CHROMA_COLLECTION", _setting_str("RAG_CHROMA_COLLECTION", "cm_qna"))

# ✅ RAG 設定檢核結果（不要 raise；改成可診斷的狀態，讓 RAG endpoint 自己 fail-close）
RAG_CONFIG_ERROR: str = ""

if not CHROMA_PERSIST_DIR.exists():
    RAG_CONFIG_ERROR = (
        f"[RAG CONFIG ERROR] CHROMA_DIR 不存在：{CHROMA_PERSIST_DIR} "
        f"(請檢查 .env 是否指到錯的磁碟/路徑，例如 H: / D:)"
    )
elif not _has_any_file(CHROMA_PERSIST_DIR):
    # 你原本的「空目錄」強防呆很合理，但不該害全站啟動失敗
    RAG_CONFIG_ERROR = (
        f"[RAG CONFIG ERROR] CHROMA_DIR 是空目錄：{CHROMA_PERSIST_DIR} "
        f"(高度懷疑 .env 指錯路徑或尚未建立索引)"
    )


# ============================================================
# RAG 查詢參數
# ============================================================
TOP_K = int(getattr(DJ, "RAG_TOP_K", _env_int("RAG_TOP_K", 10)) or 10)
if TOP_K <= 0:
    TOP_K = 10
TOP_K = min(TOP_K, 50)


# ============================================================
# Ollama / Embeddings（集中設定，禁止寫死）
# ============================================================
MODEL_TYPE = _env("MODEL_TYPE", _setting_str("MODEL_TYPE", "OLLAMA")).upper()

OLLAMA_BASE_URL = _env(
    "OLLAMA_BASE_URL",
    _setting_str("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
)

# chat model：env OLLAMA_MODEL/OLLAMA_CHAT_MODEL 優先 → settings OLLAMA_MODEL/MODEL_NAME → default
OLLAMA_CHAT_MODEL = _env(
    "OLLAMA_MODEL",
    _env(
        "OLLAMA_CHAT_MODEL",
        _setting_str("OLLAMA_MODEL", _setting_str("MODEL_NAME", "magistral-small")),
    ),
)

OLLAMA_EMBED_MODEL = _env(
    "OLLAMA_EMBED_MODEL",
    _setting_str("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
)


# ============================================================
# 啟動環境指紋（改用 logger；IIS/服務模式可追）
# ============================================================
_HOST = socket.gethostname()

logger.info(
    "[RAG] CHROMA_DIR=%s | COLLECTION=%s | TOP_K=%s | EMBED=%s | ERR=%r",
    str(CHROMA_PERSIST_DIR),
    CHROMA_COLLECTION,
    TOP_K,
    OLLAMA_EMBED_MODEL,
    RAG_CONFIG_ERROR,
)

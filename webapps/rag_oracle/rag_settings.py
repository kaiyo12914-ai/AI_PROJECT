from __future__ import annotations

import logging
import os

from django.conf import settings as DJ

logger = logging.getLogger("webapps.rag_oracle")


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


RAG_BACKEND = (_env("RAG_BACKEND", "postgres") or "postgres").strip().lower()
RAG_CONFIG_ERROR = "" if RAG_BACKEND == "postgres" else f"Unsupported RAG_BACKEND={RAG_BACKEND}; expected postgres"

TOP_K = int(getattr(DJ, "RAG_TOP_K", _env_int("RAG_TOP_K", 10)) or 10)
if TOP_K <= 0:
    TOP_K = 10
TOP_K = min(TOP_K, 50)

PG_RAG_TABLE = _env("RAG_PG_TABLE", getattr(DJ, "RAG_PG_TABLE", "public.meeting_records"))

logger.info(
    "[RAG] BACKEND=%s | SOURCE_TABLE=%s | TOP_K=%s | ERR=%r",
    RAG_BACKEND,
    PG_RAG_TABLE,
    TOP_K,
    RAG_CONFIG_ERROR,
)

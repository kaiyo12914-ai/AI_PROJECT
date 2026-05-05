from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Dict, List

from .question_catalog import QUESTION_TOPICS
from .question_bank_seed import build_seed_questions
from .repository import EnglishChatQuestionBankRepository


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_safe_text(item) for item in value if _safe_text(item)]


def _normalize_topic_key(topic: str) -> str:
    raw = _safe_text(topic).lower()
    if not raw:
        return ""
    for topic in QUESTION_TOPICS:
        if raw == topic["key"]:
            return raw
        labels = [str(item).strip().lower() for item in topic.get("labels", []) if str(item).strip()]
        if any(label and (label in raw or raw in label) for label in labels):
            return str(topic["key"])
    return raw.replace(" ", "_")


def get_db_question(topic: str, mode: str, level: str, exclude_ids: List[str] | None = None) -> Dict[str, Any] | None:
    topic_key = _normalize_topic_key(topic)
    if not topic_key:
        return None

    repo = EnglishChatQuestionBankRepository()
    rows = repo.fetch_questions(topic_key, mode, level)
    excluded = {str(item) for item in (exclude_ids or []) if str(item)}
    available = []
    for row in rows:
        question_id = _safe_text(row.get("question_id"))
        if question_id and question_id not in excluded:
            available.append(row)
    if available:
        return _row_to_payload(random.choice(available), mode)
    return None


def get_seed_question(topic: str, mode: str, level: str, exclude_ids: List[str] | None = None) -> Dict[str, Any] | None:
    topic_key = _normalize_topic_key(topic)
    if not topic_key:
        return None

    rows = [
        row
        for row in _seed_rows()
        if _safe_text(row.get("topic_key")) == topic_key
        and _safe_text(row.get("mode")) == mode
        and _safe_text(row.get("level")) == level
    ]
    excluded = {str(item) for item in (exclude_ids or []) if str(item)}
    available = []
    for row in rows:
        question_id = _safe_text(row.get("question_id"))
        if question_id and question_id not in excluded:
            available.append(row)
    if available:
        return _row_to_payload(random.choice(available), mode)
    return None


_SEED_ROWS_CACHE: List[Dict[str, Any]] | None = None


def _seed_rows() -> List[Dict[str, Any]]:
    global _SEED_ROWS_CACHE
    if _SEED_ROWS_CACHE is None:
        _SEED_ROWS_CACHE = build_seed_questions()
    return _SEED_ROWS_CACHE


def _row_to_payload(row: Dict[str, Any], mode: str) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "question_id": _safe_text(row.get("question_id")),
        "explanation_zh": _safe_text(row.get("explanation_zh")),
    }
    if mode == "fill_blank":
        item.update(
            {
                "question": _safe_text(row.get("prompt_text")),
                "choices": _normalize_list(row.get("choices_json")),
                "answer": _safe_text(row.get("answer_text")),
                "pattern": _safe_text(row.get("pattern_text")),
            }
        )
        return item
    if mode == "reorder":
        item.update(
            {
                "prompt": _safe_text(row.get("prompt_text")),
                "words": _normalize_list(row.get("words_json")),
                "answer": _safe_text(row.get("answer_text")),
                "pattern": _safe_text(row.get("pattern_text")),
            }
        )
        return item
    if mode == "translation":
        item.update(
            {
                "zh_prompt": _safe_text(row.get("zh_prompt")),
                "sample_answer": _safe_text(row.get("sample_answer")),
                "patterns": _normalize_list(row.get("patterns_json")),
            }
        )
        return item
    return deepcopy(item)

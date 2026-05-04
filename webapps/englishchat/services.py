from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .question_catalog import QUESTION_TOPICS
from .repository import EnglishChatQuestionBankRepository
from .topic_packs import TOPIC_PACKS


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
    if raw in TOPIC_PACKS:
        return raw
    for topic in QUESTION_TOPICS:
        if raw == topic["key"]:
            return raw
        labels = [str(item).strip().lower() for item in topic.get("labels", []) if str(item).strip()]
        if any(label and (label in raw or raw in label) for label in labels):
            return str(topic["key"])
    for topic_key, pack in TOPIC_PACKS.items():
        labels = [str(item).strip().lower() for item in pack.get("labels", []) if str(item).strip()]
        if any(label and (label in raw or raw in label) for label in labels):
            return topic_key
    return raw.replace(" ", "_")


def get_db_question(topic: str, mode: str, level: str, exclude_ids: List[str] | None = None) -> Dict[str, Any] | None:
    topic_key = _normalize_topic_key(topic)
    if not topic_key:
        return None

    repo = EnglishChatQuestionBankRepository()
    rows = repo.fetch_questions(topic_key, mode, level)
    excluded = {str(item) for item in (exclude_ids or []) if str(item)}
    for row in rows:
        question_id = _safe_text(row.get("question_id"))
        if question_id and question_id not in excluded:
            return _row_to_payload(row, mode)
    if rows:
        return _row_to_payload(rows[0], mode)
    return None


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

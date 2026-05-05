from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .question_catalog import QUESTION_TOPICS
from .question_bank_seed import build_seed_questions
from .repository import EnglishChatQuestionBankRepository


def safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [safe_text(item) for item in value if safe_text(item)]


def normalize_topic_key(topic: str) -> str:
    raw = safe_text(topic).lower()
    if not raw:
        return ""
    for item in QUESTION_TOPICS:
        if raw == item["key"]:
            return raw
        labels = [safe_text(label).lower() for label in item.get("labels", [])]
        if any(label and (label in raw or raw in label) for label in labels):
            return str(item["key"])
    return raw.replace(" ", "_")


def get_db_question(topic: str, mode: str, level: str, exclude_ids: List[str] | None = None) -> Dict[str, Any] | None:
    topic_key = normalize_topic_key(topic)
    if not topic_key:
        return None
    history = [safe_text(item) for item in (exclude_ids or []) if safe_text(item)]
    repo = EnglishChatQuestionBankRepository()
    row = repo.fetch_next_question(
        topic_key,
        mode,
        level,
        history,
        after_question_id=history[-1] if history else "",
    )
    if not row:
        return None
    return row_to_payload(row, mode)


def get_seed_question(topic: str, mode: str, level: str, exclude_ids: List[str] | None = None) -> Dict[str, Any] | None:
    topic_key = normalize_topic_key(topic)
    if not topic_key:
        return None
    history = [safe_text(item) for item in (exclude_ids or []) if safe_text(item)]
    excluded = set(history)
    rows = [
        row
        for row in seed_rows()
        if safe_text(row.get("topic_key")) == topic_key
        and safe_text(row.get("mode")) == mode
        and safe_text(row.get("level")) == level
    ]
    if not rows:
        return None
    start_index = 0
    if history:
        last_id = history[-1]
        for index, row in enumerate(rows):
            if safe_text(row.get("question_id")) == last_id:
                start_index = (index + 1) % len(rows)
                break
    for offset in range(len(rows)):
        row = rows[(start_index + offset) % len(rows)]
        question_id = safe_text(row.get("question_id"))
        if question_id and question_id not in excluded:
            return row_to_payload(row, mode)
    return None


_SEED_ROWS_CACHE: List[Dict[str, Any]] | None = None


def seed_rows() -> List[Dict[str, Any]]:
    global _SEED_ROWS_CACHE
    if _SEED_ROWS_CACHE is None:
        _SEED_ROWS_CACHE = build_seed_questions()
    return _SEED_ROWS_CACHE


def row_to_payload(row: Dict[str, Any], mode: str) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "question_id": safe_text(row.get("question_id")),
        "explanation_zh": safe_text(row.get("explanation_zh")),
    }
    if mode == "fill_blank":
        base.update(
            {
                "question": safe_text(row.get("prompt_text")),
                "choices": normalize_list(row.get("choices_json")),
                "answer": safe_text(row.get("answer_text")),
                "pattern": safe_text(row.get("pattern_text")),
            }
        )
        return base
    if mode == "reorder":
        base.update(
            {
                "prompt": safe_text(row.get("prompt_text")),
                "words": normalize_list(row.get("words_json")),
                "answer": safe_text(row.get("answer_text")),
                "pattern": safe_text(row.get("pattern_text")),
            }
        )
        return base
    if mode == "translation":
        base.update(
            {
                "zh_prompt": safe_text(row.get("zh_prompt")),
                "sample_answer": safe_text(row.get("sample_answer")),
                "patterns": normalize_list(row.get("patterns_json")),
            }
        )
        return base
    return deepcopy(base)

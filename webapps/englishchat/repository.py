from __future__ import annotations

import json
from typing import Any, Dict, List

from webapps.repositories.base import BaseRepository


class EnglishChatQuestionBankRepository(BaseRepository):
    COLUMNS = [
        "question_id",
        "topic_key",
        "mode",
        "level",
        "prompt_text",
        "choices_json",
        "words_json",
        "answer_text",
        "explanation_zh",
        "pattern_text",
        "zh_prompt",
        "sample_answer",
        "patterns_json",
        "sort_order",
    ]

    def __init__(self) -> None:
        super().__init__(db_type="postgresql")
        self.profile = "ENGLISHCHAT"

    def fetch_questions(self, topic_key: str, mode: str, level: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            question_id,
            topic_key,
            mode,
            level,
            prompt_text,
            choices_json,
            words_json,
            answer_text,
            explanation_zh,
            pattern_text,
            zh_prompt,
            sample_answer,
            patterns_json,
            sort_order
        FROM englishchat_question_bank
        WHERE is_active = TRUE
          AND topic_key = %s
          AND mode = %s
          AND level = %s
        ORDER BY sort_order ASC, question_id ASC
        """
        rows = self.query_all(sql, [topic_key, mode, level], profile=self.profile)
        return [self._row_to_dict(row) for row in rows]

    def upsert_question(self, item: Dict[str, Any]) -> int:
        sql = """
        INSERT INTO englishchat_question_bank (
            question_id,
            topic_key,
            mode,
            level,
            prompt_text,
            choices_json,
            words_json,
            answer_text,
            explanation_zh,
            pattern_text,
            zh_prompt,
            sample_answer,
            patterns_json,
            sort_order,
            is_active,
            updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb, %s, TRUE, NOW()
        )
        ON CONFLICT (question_id) DO UPDATE SET
            topic_key = EXCLUDED.topic_key,
            mode = EXCLUDED.mode,
            level = EXCLUDED.level,
            prompt_text = EXCLUDED.prompt_text,
            choices_json = EXCLUDED.choices_json,
            words_json = EXCLUDED.words_json,
            answer_text = EXCLUDED.answer_text,
            explanation_zh = EXCLUDED.explanation_zh,
            pattern_text = EXCLUDED.pattern_text,
            zh_prompt = EXCLUDED.zh_prompt,
            sample_answer = EXCLUDED.sample_answer,
            patterns_json = EXCLUDED.patterns_json,
            sort_order = EXCLUDED.sort_order,
            is_active = TRUE,
            updated_at = NOW()
        """
        params = [
            str(item.get("question_id") or ""),
            str(item.get("topic_key") or ""),
            str(item.get("mode") or ""),
            str(item.get("level") or ""),
            str(item.get("prompt_text") or ""),
            json.dumps(item.get("choices_json") or [], ensure_ascii=False),
            json.dumps(item.get("words_json") or [], ensure_ascii=False),
            str(item.get("answer_text") or ""),
            str(item.get("explanation_zh") or ""),
            str(item.get("pattern_text") or ""),
            str(item.get("zh_prompt") or ""),
            str(item.get("sample_answer") or ""),
            json.dumps(item.get("patterns_json") or [], ensure_ascii=False),
            int(item.get("sort_order") or 0),
        ]
        return self.execute(sql, params, profile=self.profile)

    def deactivate_generated_questions(
        self,
        topic_key: str,
        mode: str,
        level: str,
        keep_question_ids: List[str],
        generated_prefix: str,
    ) -> int:
        if keep_question_ids:
            placeholders = ", ".join(["%s"] * len(keep_question_ids))
            sql = f"""
            UPDATE englishchat_question_bank
            SET is_active = FALSE,
                updated_at = NOW()
            WHERE topic_key = %s
              AND mode = %s
              AND level = %s
              AND question_id LIKE %s
              AND question_id NOT IN ({placeholders})
            """
            params = [topic_key, mode, level, f"{generated_prefix}%"] + list(keep_question_ids)
        else:
            sql = """
            UPDATE englishchat_question_bank
            SET is_active = FALSE,
                updated_at = NOW()
            WHERE topic_key = %s
              AND mode = %s
              AND level = %s
              AND question_id LIKE %s
            """
            params = [topic_key, mode, level, f"{generated_prefix}%"]
        return self.execute(sql, params, profile=self.profile)

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        if isinstance(row, dict):
            return {key: row.get(key) for key in EnglishChatQuestionBankRepository.COLUMNS}
        if isinstance(row, (list, tuple)):
            out: Dict[str, Any] = {}
            for index, key in enumerate(EnglishChatQuestionBankRepository.COLUMNS):
                out[key] = row[index] if index < len(row) else None
            return out
        return {
            "question_id": getattr(row, "question_id", None),
            "topic_key": getattr(row, "topic_key", None),
            "mode": getattr(row, "mode", None),
            "level": getattr(row, "level", None),
            "prompt_text": getattr(row, "prompt_text", None),
            "choices_json": getattr(row, "choices_json", None),
            "words_json": getattr(row, "words_json", None),
            "answer_text": getattr(row, "answer_text", None),
            "explanation_zh": getattr(row, "explanation_zh", None),
            "pattern_text": getattr(row, "pattern_text", None),
            "zh_prompt": getattr(row, "zh_prompt", None),
            "sample_answer": getattr(row, "sample_answer", None),
            "patterns_json": getattr(row, "patterns_json", None),
            "sort_order": getattr(row, "sort_order", 0),
        }

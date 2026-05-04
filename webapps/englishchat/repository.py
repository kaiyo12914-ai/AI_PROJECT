from __future__ import annotations

from typing import Any, Dict, List

from webapps.repositories.base import BaseRepository


class EnglishChatQuestionBankRepository(BaseRepository):
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

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
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

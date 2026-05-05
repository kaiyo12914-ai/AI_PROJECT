from __future__ import annotations

import argparse
import json

from webapps.database.db_factory import db_connect
from webapps.englishchat.question_bank_seed import build_seed_questions


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS englishchat_question_bank (
    id BIGSERIAL PRIMARY KEY,
    question_id TEXT NOT NULL UNIQUE,
    topic_key TEXT NOT NULL,
    mode TEXT NOT NULL,
    level TEXT NOT NULL,
    prompt_text TEXT,
    choices_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    words_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    answer_text TEXT,
    explanation_zh TEXT,
    pattern_text TEXT,
    zh_prompt TEXT,
    sample_answer TEXT,
    patterns_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_englishchat_qb_topic_mode_level
    ON englishchat_question_bank (topic_key, mode, level, sort_order, question_id);
"""

UPSERT_SQL = """
INSERT INTO englishchat_question_bank (
    question_id, topic_key, mode, level, prompt_text, choices_json, words_json,
    answer_text, explanation_zh, pattern_text, zh_prompt, sample_answer, patterns_json, sort_order, is_active, updated_at
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize or refresh EnglishChat seed questions.")
    parser.add_argument("--deactivate-missing-seeds", action="store_true")
    parser.add_argument("--full-reset", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conn = db_connect("postgresql", profile="ENGLISHCHAT")
    cur = conn.cursor()
    try:
        cur.execute(CREATE_SQL)
        if args.full_reset:
            cur.execute("DELETE FROM englishchat_question_bank WHERE question_id LIKE 'seed-%'")

        seed_rows = build_seed_questions()
        seed_ids = []
        for item in seed_rows:
            seed_id = str(item.get("question_id") or "")
            seed_ids.append(seed_id)
            cur.execute(
                UPSERT_SQL,
                [
                    seed_id,
                    str(item.get("topic_key") or ""),
                    str(item.get("mode") or ""),
                    str(item.get("level") or "beginner"),
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
                ],
            )

        if args.deactivate_missing_seeds:
            placeholders = ", ".join(["%s"] * len(seed_ids))
            cur.execute(
                f"""
                UPDATE englishchat_question_bank
                SET is_active = FALSE, updated_at = NOW()
                WHERE question_id LIKE 'seed-%'
                  AND question_id NOT IN ({placeholders})
                """,
                seed_ids,
            )
        conn.commit()
        print(f"Upserted {len(seed_rows)} seed questions.")
    finally:
        try:
            cur.close()
        finally:
            conn.close()


if __name__ == "__main__":
    main()

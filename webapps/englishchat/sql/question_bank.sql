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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT englishchat_question_bank_mode_chk
        CHECK (mode IN ('fill_blank', 'reorder', 'translation')),
    CONSTRAINT englishchat_question_bank_level_chk
        CHECK (level IN ('beginner', 'intermediate', 'advanced'))
);

CREATE INDEX IF NOT EXISTS idx_englishchat_qb_topic_mode_level
    ON englishchat_question_bank (topic_key, mode, level, sort_order, question_id);

CREATE INDEX IF NOT EXISTS idx_englishchat_qb_active
    ON englishchat_question_bank (is_active);

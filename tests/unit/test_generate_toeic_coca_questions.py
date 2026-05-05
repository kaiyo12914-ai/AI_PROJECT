import types

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",
        DEBUG=True,
        DEFAULT_CHARSET="utf-8",
        ROOT_URLCONF="webproj.urls",
        INSTALLED_APPS=[],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    )
django.setup()

import pytest

from webapps.englishchat.generate_toeic_coca_questions import (
    GENERATED_PREFIX,
    QuestionGenerationError,
    dedupe_items,
    generate_combo_questions,
    validate_item,
)
from webapps.englishchat.repository import EnglishChatQuestionBankRepository


def test_validate_item_fill_blank_normalizes_and_generates_deterministic_id():
    item = validate_item(
        {
            "prompt_text": " We ____ the meeting tomorrow. ",
            "choices_json": ["schedule ", " cancel", "postpone"],
            "words_json": [],
            "answer_text": "schedule",
            "explanation_zh": "表示安排會議。",
            "pattern_text": "schedule + noun",
            "zh_prompt": "",
            "sample_answer": "",
            "patterns_json": [],
        },
        topic="meeting",
        mode="fill_blank",
        level="beginner",
        sort_order=100,
    )

    assert item["prompt_text"] == "We ____ the meeting tomorrow."
    assert item["choices_json"] == ["schedule", "cancel", "postpone"]
    assert item["question_id"].startswith(GENERATED_PREFIX)

    same = validate_item(
        {
            "prompt_text": "We ____ the meeting tomorrow.",
            "choices_json": ["schedule", "cancel", "postpone"],
            "words_json": [],
            "answer_text": "schedule",
            "explanation_zh": "表示安排會議。",
            "pattern_text": "schedule + noun",
            "zh_prompt": "",
            "sample_answer": "",
            "patterns_json": [],
        },
        topic="meeting",
        mode="fill_blank",
        level="beginner",
        sort_order=999,
    )
    assert same["question_id"] == item["question_id"]


def test_validate_item_rejects_invalid_mode_schema():
    with pytest.raises(QuestionGenerationError, match="choices_json must contain at least 3 choices"):
        validate_item(
            {
                "prompt_text": "We ____ the meeting tomorrow.",
                "choices_json": ["schedule"],
                "words_json": [],
                "answer_text": "schedule",
                "explanation_zh": "表示安排會議。",
                "pattern_text": "schedule + noun",
                "zh_prompt": "",
                "sample_answer": "",
                "patterns_json": [],
            },
            topic="meeting",
            mode="fill_blank",
            level="beginner",
            sort_order=100,
        )


def test_dedupe_items_skips_same_question_id():
    first = {
        "question_id": "ai-toeic-coca-1",
        "prompt_text": "A",
    }
    second = {
        "question_id": "ai-toeic-coca-1",
        "prompt_text": "B",
    }

    items, skipped = dedupe_items([first, second])

    assert items == [first]
    assert skipped == 1


def test_generate_combo_questions_rejects_non_unique_payload():
    class FakeLlm:
        def invoke(self, prompt):
            return types.SimpleNamespace(
                content="""
                [
                  {
                    "prompt_text": "We ____ the meeting tomorrow.",
                    "choices_json": ["schedule", "cancel", "postpone"],
                    "words_json": [],
                    "answer_text": "schedule",
                    "explanation_zh": "表示安排會議。",
                    "pattern_text": "schedule + noun",
                    "zh_prompt": "",
                    "sample_answer": "",
                    "patterns_json": []
                  },
                  {
                    "prompt_text": "We ____ the meeting tomorrow.",
                    "choices_json": ["schedule", "cancel", "postpone"],
                    "words_json": [],
                    "answer_text": "schedule",
                    "explanation_zh": "表示安排會議。",
                    "pattern_text": "schedule + noun",
                    "zh_prompt": "",
                    "sample_answer": "",
                    "patterns_json": []
                  }
                ]
                """
            )

    with pytest.raises(QuestionGenerationError, match="Expected 2 unique questions but received 1"):
        generate_combo_questions(FakeLlm(), "meeting", "fill_blank", "beginner", 2)


def test_repository_deactivate_generated_questions_builds_not_in_sql(monkeypatch):
    captured = {}

    def fake_execute(self, sql, params=None, db_type=None, profile=""):
        captured["sql"] = sql
        captured["params"] = params
        captured["profile"] = profile
        return 3

    monkeypatch.setattr("webapps.repositories.base.BaseRepository.execute", fake_execute)

    repo = EnglishChatQuestionBankRepository()
    affected = repo.deactivate_generated_questions(
        topic_key="travel",
        mode="translation",
        level="advanced",
        keep_question_ids=["ai-toeic-coca-a1", "ai-toeic-coca-a2"],
        generated_prefix=GENERATED_PREFIX,
    )

    assert affected == 3
    assert "question_id NOT IN" in captured["sql"]
    assert captured["params"] == [
        "travel",
        "translation",
        "advanced",
        f"{GENERATED_PREFIX}%",
        "ai-toeic-coca-a1",
        "ai-toeic-coca-a2",
    ]
    assert captured["profile"] == "ENGLISHCHAT"

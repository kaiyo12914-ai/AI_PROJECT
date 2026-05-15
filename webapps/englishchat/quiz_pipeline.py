from __future__ import annotations

import random
from typing import Any, Callable, Dict, List

from .llm_service import EnglishChatLLMError, invoke_json, safe_text
from .services import get_db_question

LEVEL_PROFILE = {
    "beginner": "Use short sentences, high-frequency words, and slower pacing.",
    "intermediate": "Use practical phrases and ask follow-up questions naturally.",
    "advanced": "Use nuanced expressions, idioms in moderation, and native-like flow.",
}


def normalize_level(raw: Any) -> str:
    level = safe_text(raw).lower() or "beginner"
    return level if level in LEVEL_PROFILE else "beginner"


def seen_question_ids(body: Dict[str, Any]) -> List[str]:
    raw = body.get("seen_question_ids") or []
    if not isinstance(raw, list):
        return []
    return [safe_text(item) for item in raw if safe_text(item)]


def normalize_plain_sentence(text: str) -> str:
    return " ".join((text or "").strip().rstrip(".!?").lower().split())


def fallback_fill_blank(level: str) -> Dict[str, Any]:
    mapping = {
        "beginner": {
            "question_id": "fallback-beginner-001",
            "question": "I usually ____ coffee in the morning.",
            "choices": ["drink", "drinks", "drinking"],
            "answer": "drink",
            "explanation_zh": "主詞是 I，所以動詞用原形 drink。",
            "pattern": "I usually + V ...",
        },
        "intermediate": {
            "question_id": "fallback-intermediate-001",
            "question": "I am looking forward to ____ from you.",
            "choices": ["hear", "hearing", "heard"],
            "answer": "hearing",
            "explanation_zh": "look forward to 後面接 V-ing。",
            "pattern": "look forward to + V-ing",
        },
        "advanced": {
            "question_id": "fallback-advanced-001",
            "question": "I would rather ____ the issue before the meeting.",
            "choices": ["address", "addressing", "to address"],
            "answer": "address",
            "explanation_zh": "would rather 後面接原形動詞。",
            "pattern": "would rather + V",
        },
    }
    return dict(mapping[level])


def fallback_reorder(level: str) -> Dict[str, Any]:
    mapping = {
        "beginner": {
            "question_id": "fallback-reorder-beginner-001",
            "prompt": "Put the words in the correct order.",
            "words": ["like", "I", "to", "travel"],
            "answer": "I like to travel.",
            "explanation_zh": "基本語序是主詞 + 動詞 + 不定詞片語。",
            "pattern": "I like to + V",
        },
        "intermediate": {
            "question_id": "fallback-reorder-intermediate-001",
            "prompt": "Put the words in the most natural order.",
            "words": ["looking", "I", "to", "hearing", "forward", "am", "from you"],
            "answer": "I am looking forward to hearing from you.",
            "explanation_zh": "look forward to 後面接 V-ing。",
            "pattern": "look forward to + V-ing",
        },
        "advanced": {
            "question_id": "fallback-reorder-advanced-001",
            "prompt": "Put the words in the most natural order.",
            "words": ["rather", "the", "address", "issue", "I", "would", "today"],
            "answer": "I would rather address the issue today.",
            "explanation_zh": "would rather 後面接原形動詞，時間副詞放句尾。",
            "pattern": "would rather + V",
        },
    }
    return dict(mapping[level])


def fallback_translation(level: str) -> Dict[str, Any]:
    mapping = {
        "beginner": {
            "question_id": "fallback-translate-beginner-001",
            "zh_prompt": "我喜歡旅遊。",
            "sample_answer": "I like to travel.",
            "explanation_zh": "可以用 I like to + 原形動詞 來表達喜歡做某事。",
            "patterns": ["I like to + V", "I enjoy + V-ing"],
        },
        "intermediate": {
            "question_id": "fallback-translate-intermediate-001",
            "zh_prompt": "我很期待收到你的消息。",
            "sample_answer": "I am looking forward to hearing from you.",
            "explanation_zh": "look forward to 後面接 V-ing。",
            "patterns": ["look forward to + V-ing", "hear from someone"],
        },
        "advanced": {
            "question_id": "fallback-translate-advanced-001",
            "zh_prompt": "我比較想今天就處理這個問題。",
            "sample_answer": "I would rather address this issue today.",
            "explanation_zh": "would rather 後面接原形動詞，address this issue 表示處理這個問題。",
            "patterns": ["would rather + V", "address an issue"],
        },
    }
    return dict(mapping[level])


def normalize_fill_blank_quiz(data: Dict[str, Any], level: str) -> Dict[str, Any]:
    fallback = fallback_fill_blank(level)
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    out_choices = [safe_text(item) for item in choices if safe_text(item)]
    if len(out_choices) < 3:
        out_choices = list(fallback["choices"])
    answer = safe_text(data.get("answer")) or fallback["answer"]
    if answer not in out_choices:
        out_choices.append(answer)
    random.shuffle(out_choices)
    return {
        "question_id": safe_text(data.get("question_id")) or fallback["question_id"],
        "question": safe_text(data.get("question")) or fallback["question"],
        "choices": out_choices,
        "answer": answer,
        "explanation_zh": safe_text(data.get("explanation_zh")) or fallback["explanation_zh"],
        "pattern": safe_text(data.get("pattern")) or fallback["pattern"],
    }


def normalize_reorder_quiz(data: Dict[str, Any], level: str) -> Dict[str, Any]:
    fallback = fallback_reorder(level)
    words = data.get("words") if isinstance(data.get("words"), list) else []
    out_words = [safe_text(item) for item in words if safe_text(item)]
    if len(out_words) < 3:
        out_words = list(fallback["words"])
    return {
        "question_id": safe_text(data.get("question_id")) or fallback["question_id"],
        "prompt": safe_text(data.get("prompt")) or fallback["prompt"],
        "words": out_words[:10],
        "answer": safe_text(data.get("answer")) or fallback["answer"],
        "explanation_zh": safe_text(data.get("explanation_zh")) or fallback["explanation_zh"],
        "pattern": safe_text(data.get("pattern")) or fallback["pattern"],
    }


def normalize_translation_quiz(data: Dict[str, Any], level: str) -> Dict[str, Any]:
    fallback = fallback_translation(level)
    patterns = data.get("patterns") if isinstance(data.get("patterns"), list) else []
    out_patterns = [safe_text(item) for item in patterns if safe_text(item)]
    if not out_patterns:
        out_patterns = list(fallback["patterns"])
    return {
        "question_id": safe_text(data.get("question_id")) or fallback["question_id"],
        "zh_prompt": safe_text(data.get("zh_prompt")) or fallback["zh_prompt"],
        "sample_answer": safe_text(data.get("sample_answer")) or fallback["sample_answer"],
        "explanation_zh": safe_text(data.get("explanation_zh")) or fallback["explanation_zh"],
        "patterns": out_patterns[:3],
    }


def fill_blank_prompt(topic: str, level: str) -> str:
    return f"""
You are an American-English quiz writer for Taiwanese learners.
Create one unique fill-in-the-blank quiz.
Topic: {topic}
Level: {level}
Level policy: {LEVEL_PROFILE[level]}
Output JSON only:
{{
  "question_id": "short stable id",
  "question": "one English sentence with exactly one ____ blank",
  "choices": ["3 short answer choices"],
  "answer": "the exact correct choice",
  "explanation_zh": "short Traditional Chinese explanation",
  "pattern": "reusable English sentence pattern"
}}
""".strip()


def reorder_prompt(topic: str, level: str) -> str:
    return f"""
You are an American-English quiz writer for Taiwanese learners.
Create one unique sentence reordering quiz.
Topic: {topic}
Level: {level}
Level policy: {LEVEL_PROFILE[level]}
Output JSON only:
{{
  "question_id": "short stable id",
  "prompt": "short instruction",
  "words": ["word chips in shuffled order"],
  "answer": "the full correct sentence",
  "explanation_zh": "short Traditional Chinese explanation",
  "pattern": "reusable English sentence pattern"
}}
""".strip()


def translation_prompt(topic: str, level: str) -> str:
    return f"""
You are an American-English practice writer for Taiwanese learners.
Create one Chinese-to-English translation exercise.
Topic: {topic}
Level: {level}
Level policy: {LEVEL_PROFILE[level]}
Output JSON only:
{{
  "question_id": "short stable id",
  "zh_prompt": "one Traditional Chinese sentence to translate",
  "sample_answer": "one natural American-English answer",
  "explanation_zh": "short Traditional Chinese explanation",
  "patterns": ["up to 3 reusable English patterns"]
}}
""".strip()


def translation_evaluation_prompt(zh_prompt: str, user_answer: str, sample_answer: str, level: str) -> str:
    return f"""
You are an American-English writing coach.
Evaluate the learner's translation.
Chinese prompt: {zh_prompt}
Learner answer: {user_answer}
Sample answer: {sample_answer}
Level: {level}
Output JSON only:
{{
  "score": 0,
  "corrected": "a natural corrected sentence",
  "feedback_zh": "short Traditional Chinese feedback",
  "suggestions": ["up to 3 reusable expressions"]
}}
""".strip()


def run_quiz_pipeline(
    *,
    topic: str,
    level: str,
    mode: str,
    exclude_ids: List[str],
    normalize: Callable[[Dict[str, Any], str], Dict[str, Any]],
    prompt_builder: Callable[[str, str], str],
) -> Dict[str, Any]:
    bank_notice = "題庫已用完改由 AI出題"
    db_item = get_db_question(topic, mode, level, exclude_ids)
    if db_item:
        quiz = normalize(db_item, level)
        quiz["source"] = "question_bank"
        quiz["bank_exhausted"] = False
        quiz["bank_notice"] = ""
        return quiz
    fallback_reason = ""
    try:
        data = invoke_json(prompt_builder(topic, level), purpose=f"{mode}_quiz")
        quiz = normalize(data, level)
        quiz["source"] = "llm"
    except EnglishChatLLMError as exc:
        quiz = normalize({}, level)
        quiz["source"] = "fallback"
        fallback_reason = str(exc)
    if fallback_reason:
        quiz["fallback_reason"] = fallback_reason
    quiz["bank_exhausted"] = True
    quiz["bank_notice"] = bank_notice
    return quiz

from __future__ import annotations

import json
from typing import Any, Dict, List

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .services import get_db_question
from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node
from .topic_packs import get_topic_pack_item


TOPIC_PRESETS = [
    "旅遊",
    "點餐",
    "購物",
    "面試",
    "交朋友",
    "校園",
    "工作",
    "日常生活",
]

LEVEL_PROFILE = {
    "beginner": "Use short sentences, high-frequency words, and slower pacing.",
    "intermediate": "Use practical phrases and ask follow-up questions naturally.",
    "advanced": "Use nuanced expressions, idioms in moderation, and native-like flow.",
}


@require_node("englishchat")
def index(request):
    return render(
        request,
        "englishchat/index.html",
        {"topic_presets": TOPIC_PRESETS},
    )


def _safe_text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _extract_json(raw: str) -> Dict[str, Any]:
    s = (raw or "").strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        pass
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(s[i : j + 1])
        except Exception:
            return {}
    return {}


def _invoke_llm(prompt: str) -> str:
    llm = get_chat_model(temperature=0.6, timeout=90)
    out = llm.invoke(prompt)
    if hasattr(out, "content"):
        return _safe_text(out.content)
    return _safe_text(out)


def _read_json_body(request) -> Dict[str, Any] | None:
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return None


def _normalize_level(raw: Any) -> str:
    level = _safe_text(raw).lower() or "beginner"
    return level if level in LEVEL_PROFILE else "beginner"


def _seen_question_ids(body: Dict[str, Any]) -> List[str]:
    raw = body.get("seen_question_ids") or []
    if not isinstance(raw, list):
        return []
    return [_safe_text(x) for x in raw if _safe_text(x)]


def _fallback_fill_blank(topic: str, level: str) -> Dict[str, Any]:
    if level == "advanced":
        return {
            "question_id": "fallback-advanced-001",
            "question": "I would rather ____ the issue before the meeting.",
            "choices": ["address", "addressing", "to address"],
            "answer": "address",
            "explanation_zh": "would rather 後面接原形動詞。",
            "pattern": "I would rather + V ...",
        }
    if level == "intermediate":
        return {
            "question_id": "fallback-intermediate-001",
            "question": "I am looking forward to ____ from you.",
            "choices": ["hear", "hearing", "heard"],
            "answer": "hearing",
            "explanation_zh": "look forward to 的 to 是介系詞，後面接 V-ing。",
            "pattern": "look forward to + V-ing",
        }
    return {
        "question_id": "fallback-beginner-001",
        "question": "I usually ____ coffee in the morning.",
        "choices": ["drink", "drinks", "drinking"],
        "answer": "drink",
        "explanation_zh": "主詞 I 搭配原形動詞。",
        "pattern": "I usually + V ...",
    }


def _normalize_fill_blank_quiz(data: Dict[str, Any], topic: str, level: str) -> Dict[str, Any]:
    fallback = _fallback_fill_blank(topic, level)
    question = _safe_text(data.get("question")) or fallback["question"]
    raw_choices = data.get("choices")
    choices = []
    if isinstance(raw_choices, list):
        choices = [_safe_text(x) for x in raw_choices if _safe_text(x)]
    if len(choices) < 2:
        choices = fallback["choices"]
    choices = choices[:4]
    answer = _safe_text(data.get("answer")) or fallback["answer"]
    if answer not in choices:
        answer = fallback["answer"] if fallback["answer"] in choices else choices[0]
    return {
        "question_id": _safe_text(data.get("question_id")) or fallback["question_id"],
        "question": question,
        "choices": choices,
        "answer": answer,
        "explanation_zh": _safe_text(data.get("explanation_zh")) or fallback["explanation_zh"],
        "pattern": _safe_text(data.get("pattern")) or fallback["pattern"],
    }


def _build_fill_blank_prompt(topic: str, level: str) -> str:
    return f"""
You are an American-English quiz writer for Taiwanese learners.
Create one fill-in-the-blank quiz.

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

Rules:
- Use practical American English.
- The answer must be one of the choices.
- Do not output markdown.
""".strip()


def _fallback_reorder(topic: str, level: str) -> Dict[str, Any]:
    if level == "advanced":
        return {
            "question_id": "fallback-reorder-advanced-001",
            "prompt": "Put the words in the most natural order.",
            "words": ["rather", "the", "address", "issue", "I", "would", "today"],
            "answer": "I would rather address the issue today.",
            "explanation_zh": "would rather 後面接原形動詞，時間副詞通常放句尾。",
            "pattern": "I would rather + V ...",
        }
    if level == "intermediate":
        return {
            "question_id": "fallback-reorder-intermediate-001",
            "prompt": "Put the words in the most natural order.",
            "words": ["looking", "I", "to", "hearing", "forward", "am", "from you"],
            "answer": "I am looking forward to hearing from you.",
            "explanation_zh": "look forward to 後面接 V-ing。",
            "pattern": "I am looking forward to + V-ing",
        }
    return {
        "question_id": "fallback-reorder-beginner-001",
        "prompt": "Put the words in the correct order.",
        "words": ["like", "I", "to", "travel"],
        "answer": "I like to travel.",
        "explanation_zh": "英文基本句型是主詞 + 動詞 + 受詞/補語。",
        "pattern": "I like to + V",
    }


def _normalize_reorder_quiz(data: Dict[str, Any], topic: str, level: str) -> Dict[str, Any]:
    fallback = _fallback_reorder(topic, level)
    raw_words = data.get("words")
    words = []
    if isinstance(raw_words, list):
        words = [_safe_text(x) for x in raw_words if _safe_text(x)]
    if len(words) < 3:
        words = fallback["words"]
    answer = _safe_text(data.get("answer")) or fallback["answer"]
    return {
        "question_id": _safe_text(data.get("question_id")) or fallback["question_id"],
        "prompt": _safe_text(data.get("prompt")) or fallback["prompt"],
        "words": words[:10],
        "answer": answer,
        "explanation_zh": _safe_text(data.get("explanation_zh")) or fallback["explanation_zh"],
        "pattern": _safe_text(data.get("pattern")) or fallback["pattern"],
    }


def _build_reorder_prompt(topic: str, level: str) -> str:
    return f"""
You are an American-English quiz writer for Taiwanese learners.
Create one sentence reordering quiz.

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

Rules:
- Use practical American English.
- Keep beginner sentences short.
- The answer must use all word chips.
- Do not output markdown.
""".strip()


def _fallback_translation(topic: str, level: str) -> Dict[str, Any]:
    if level == "advanced":
        return {
            "question_id": "fallback-translate-advanced-001",
            "zh_prompt": "我寧願今天先處理這個問題。",
            "sample_answer": "I would rather address this issue today.",
            "explanation_zh": "would rather 後面接原形動詞，address 可表示處理問題。",
            "patterns": ["I would rather + V ...", "address an issue"],
        }
    if level == "intermediate":
        return {
            "question_id": "fallback-translate-intermediate-001",
            "zh_prompt": "我期待收到你的回覆。",
            "sample_answer": "I am looking forward to hearing from you.",
            "explanation_zh": "look forward to 後面接 V-ing。",
            "patterns": ["I am looking forward to + V-ing", "hear from you"],
        }
    return {
        "question_id": "fallback-translate-beginner-001",
        "zh_prompt": "我喜歡旅行。",
        "sample_answer": "I like to travel.",
        "explanation_zh": "I like to + 原形動詞，是常用基本句型。",
        "patterns": ["I like to + V", "I enjoy + V-ing"],
    }


def _normalize_translation_quiz(data: Dict[str, Any], topic: str, level: str) -> Dict[str, Any]:
    fallback = _fallback_translation(topic, level)
    raw_patterns = data.get("patterns")
    patterns = []
    if isinstance(raw_patterns, list):
        patterns = [_safe_text(x) for x in raw_patterns if _safe_text(x)]
    if not patterns:
        patterns = fallback["patterns"]
    return {
        "question_id": _safe_text(data.get("question_id")) or fallback["question_id"],
        "zh_prompt": _safe_text(data.get("zh_prompt")) or fallback["zh_prompt"],
        "sample_answer": _safe_text(data.get("sample_answer")) or fallback["sample_answer"],
        "explanation_zh": _safe_text(data.get("explanation_zh")) or fallback["explanation_zh"],
        "patterns": patterns[:3],
    }


def _build_translation_prompt(topic: str, level: str) -> str:
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

Rules:
- Keep the sentence practical and conversational.
- Avoid rare vocabulary unless level is advanced.
- Do not output markdown.
""".strip()


def _build_translation_evaluation_prompt(zh_prompt: str, user_answer: str, sample_answer: str, level: str) -> str:
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

Rules:
- score is an integer from 0 to 100.
- Focus on natural American English, not literal translation.
- Do not output markdown.
""".strip()


def _normalize_plain_sentence(s: str) -> str:
    return " ".join((s or "").strip().rstrip(".!?").lower().split())


def _practice_summary(attempts: Any) -> Dict[str, Any]:
    rows = attempts if isinstance(attempts, list) else []
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mode = _safe_text(row.get("mode")) or "practice"
        pattern = _safe_text(row.get("pattern"))
        correct = bool(row.get("correct"))
        score_raw = row.get("score")
        try:
            score = int(score_raw) if score_raw is not None else (100 if correct else 0)
        except Exception:
            score = 100 if correct else 0
        cleaned.append(
            {
                "mode": mode,
                "correct": correct,
                "score": max(0, min(100, score)),
                "pattern": pattern,
            }
        )

    total = len(cleaned)
    correct_count = sum(1 for row in cleaned if row["correct"])
    average_score = round(sum(row["score"] for row in cleaned) / total) if total else 0
    accuracy = round((correct_count / total) * 100) if total else 0

    weak_modes: Dict[str, int] = {}
    weak_patterns: Dict[str, int] = {}
    for row in cleaned:
        if row["correct"] and row["score"] >= 80:
            continue
        weak_modes[row["mode"]] = weak_modes.get(row["mode"], 0) + 1
        if row["pattern"]:
            weak_patterns[row["pattern"]] = weak_patterns.get(row["pattern"], 0) + 1

    weak_mode_list = sorted(weak_modes, key=lambda k: (-weak_modes[k], k))[:3]
    weak_pattern_list = sorted(weak_patterns, key=lambda k: (-weak_patterns[k], k))[:3]

    recommendations = []
    if not total:
        recommendations.append("Start with one short fill-in-the-blank question.")
    if "fill_blank" in weak_modes:
        recommendations.append("Review the target grammar pattern, then try another fill-in-the-blank question.")
    if "reorder" in weak_modes:
        recommendations.append("Practice word order: subject + verb + object/complement.")
    if "translate" in weak_modes:
        recommendations.append("Compare your translation with the sample and reuse one pattern.")
    for pattern in weak_pattern_list:
        recommendations.append(f"Review: {pattern}")
    if total and not recommendations:
        recommendations.append("Good session. Try a harder level or switch to translation practice.")

    return {
        "total": total,
        "correct": correct_count,
        "accuracy": accuracy,
        "average_score": average_score,
        "weak_modes": weak_mode_list,
        "weak_patterns": weak_pattern_list,
        "recommendations": recommendations[:5],
    }


@csrf_exempt
@require_node("englishchat", api=True)
def api_start(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    topic = _safe_text(body.get("topic"))
    custom_topic = _safe_text(body.get("custom_topic"))
    level = _safe_text(body.get("level")).lower() or "beginner"
    final_topic = custom_topic or topic or "日常生活"
    if level not in LEVEL_PROFILE:
        level = "beginner"

    prompt = f"""
You are an American-English speaking partner.
Goal: start a friendly practice chat for a Taiwanese learner.

Topic: {final_topic}
Level: {level}
Level policy: {LEVEL_PROFILE[level]}

Output JSON only:
{{
  "opening": "one friendly opening message in American English",
  "zh_hint": "short Traditional Chinese hint, <= 22 chars",
  "starter_sentences": ["3 practical reply options in English"]
}}
No markdown.
""".strip()

    opening = "Hey! Great to chat with you. What would you like to talk about first?"
    zh_hint = "先用一句簡短英文回覆就好。"
    starters = [
        "I want to practice this topic.",
        "Can we start with an easy situation?",
        "Please correct my English while we chat.",
    ]

    try:
        data = _extract_json(_invoke_llm(prompt))
        opening = _safe_text(data.get("opening")) or opening
        zh_hint = _safe_text(data.get("zh_hint")) or zh_hint
        raw_starters = data.get("starter_sentences")
        if isinstance(raw_starters, list):
            parsed = [_safe_text(x) for x in raw_starters if _safe_text(x)]
            if parsed:
                starters = parsed[:3]
    except Exception:
        pass

    return JsonResponse(
        {
            "ok": True,
            "topic": final_topic,
            "level": level,
            "opening": opening,
            "zh_hint": zh_hint,
            "starter_sentences": starters,
        }
    )


@csrf_exempt
@require_node("englishchat", api=True)
def api_chat(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    topic = _safe_text(body.get("topic")) or "日常生活"
    level = _safe_text(body.get("level")).lower() or "beginner"
    if level not in LEVEL_PROFILE:
        level = "beginner"
    user_text = _safe_text(body.get("user_text"))
    if not user_text:
        return JsonResponse({"ok": False, "error": "user_text is required"}, status=400)

    history = body.get("messages") or []
    lines: List[str] = []
    if isinstance(history, list):
        for m in history[-10:]:
            if not isinstance(m, dict):
                continue
            role = _safe_text(m.get("role")).lower()
            text = _safe_text(m.get("text"))
            if not text:
                continue
            speaker = "User" if role == "user" else "Coach"
            lines.append(f"{speaker}: {text}")

    transcript = "\n".join(lines)
    prompt = f"""
You are an American-English conversation coach.
Keep the tone friendly, not exam-like.
Use natural spoken American English.
Topic: {topic}
Level: {level}
Level policy: {LEVEL_PROFILE[level]}

Recent chat:
{transcript}
User latest message: {user_text}

Output JSON only:
{{
  "ai_reply": "natural next message (1-3 sentences)",
  "correction": {{
    "original": "user sentence to improve",
    "improved": "more natural sentence",
    "why": "short reason in Traditional Chinese"
  }},
  "suggestions": ["up to 3 short sentence patterns the learner can reuse"],
  "zh_hint": "optional short Traditional Chinese hint, <= 26 chars"
}}

Rules:
- Keep it practical and conversational.
- If the user is mostly correct, keep correction brief and positive.
- Always include at least one suggestion.
- Do not output markdown.
""".strip()

    fallback = {
        "ai_reply": "Nice. Tell me one more detail so we can keep the conversation going.",
        "correction": {
            "original": user_text,
            "improved": user_text,
            "why": "句子可理解，可再補細節讓對話更自然。",
        },
        "suggestions": [
            "Can you tell me more about that?",
            "In my opinion, ...",
            "I usually ... because ...",
        ],
        "zh_hint": "可補充時間、地點、原因。",
    }

    try:
        data = _extract_json(_invoke_llm(prompt))
    except Exception:
        data = {}

    ai_reply = _safe_text(data.get("ai_reply")) or fallback["ai_reply"]
    correction = data.get("correction") if isinstance(data.get("correction"), dict) else {}
    correction_original = _safe_text(correction.get("original")) or user_text
    correction_improved = _safe_text(correction.get("improved")) or user_text
    correction_why = _safe_text(correction.get("why")) or fallback["correction"]["why"]

    suggestions_raw = data.get("suggestions")
    suggestions: List[str] = []
    if isinstance(suggestions_raw, list):
        suggestions = [_safe_text(x) for x in suggestions_raw if _safe_text(x)]
    if not suggestions:
        suggestions = fallback["suggestions"]

    zh_hint = _safe_text(data.get("zh_hint")) or fallback["zh_hint"]

    return JsonResponse(
        {
            "ok": True,
            "ai_reply": ai_reply,
            "correction": {
                "original": correction_original,
                "improved": correction_improved,
                "why": correction_why,
            },
            "suggestions": suggestions[:3],
            "zh_hint": zh_hint,
        }
    )


@csrf_exempt
@require_node("englishchat", api=True)
def api_practice_summary(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    summary = _practice_summary(body.get("attempts"))
    summary["ok"] = True
    return JsonResponse(summary)


@csrf_exempt
@require_node("englishchat", api=True)
def api_fill_blank_quiz(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    topic = _safe_text(body.get("custom_topic")) or _safe_text(body.get("topic")) or "daily life"
    level = _normalize_level(body.get("level"))
    db_item = get_db_question(topic, "fill_blank", level, _seen_question_ids(body))
    if db_item:
        quiz = _normalize_fill_blank_quiz(db_item, topic, level)
        quiz.update({"ok": True, "topic": topic, "level": level, "source": "question_bank"})
        return JsonResponse(quiz)
    pack_item = get_topic_pack_item(topic, "fill_blank", level, _seen_question_ids(body))
    if pack_item:
        quiz = _normalize_fill_blank_quiz(pack_item, topic, level)
        quiz.update({"ok": True, "topic": topic, "level": level, "source": "topic_pack"})
        return JsonResponse(quiz)

    prompt = _build_fill_blank_prompt(topic, level)

    try:
        data = _extract_json(_invoke_llm(prompt))
    except Exception:
        data = {}

    quiz = _normalize_fill_blank_quiz(data, topic, level)
    quiz.update({"ok": True, "topic": topic, "level": level, "source": "llm" if data else "fallback"})
    return JsonResponse(quiz)


@csrf_exempt
@require_node("englishchat", api=True)
def api_check_fill_blank(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    selected = _safe_text(body.get("selected"))
    answer = _safe_text(body.get("answer"))
    if not selected:
        return JsonResponse({"ok": False, "error": "selected is required"}, status=400)
    if not answer:
        return JsonResponse({"ok": False, "error": "answer is required"}, status=400)

    explanation = _safe_text(body.get("explanation_zh")) or "請確認句型與上下文。"
    pattern = _safe_text(body.get("pattern"))
    return JsonResponse(
        {
            "ok": True,
            "correct": selected.strip().lower() == answer.strip().lower(),
            "selected": selected,
            "answer": answer,
            "explanation_zh": explanation,
            "pattern": pattern,
        }
    )


@csrf_exempt
@require_node("englishchat", api=True)
def api_reorder_quiz(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    topic = _safe_text(body.get("custom_topic")) or _safe_text(body.get("topic")) or "daily life"
    level = _normalize_level(body.get("level"))
    db_item = get_db_question(topic, "reorder", level, _seen_question_ids(body))
    if db_item:
        quiz = _normalize_reorder_quiz(db_item, topic, level)
        quiz.update({"ok": True, "topic": topic, "level": level, "source": "question_bank"})
        return JsonResponse(quiz)
    pack_item = get_topic_pack_item(topic, "reorder", level, _seen_question_ids(body))
    if pack_item:
        quiz = _normalize_reorder_quiz(pack_item, topic, level)
        quiz.update({"ok": True, "topic": topic, "level": level, "source": "topic_pack"})
        return JsonResponse(quiz)

    prompt = _build_reorder_prompt(topic, level)

    try:
        data = _extract_json(_invoke_llm(prompt))
    except Exception:
        data = {}

    quiz = _normalize_reorder_quiz(data, topic, level)
    quiz.update({"ok": True, "topic": topic, "level": level, "source": "llm" if data else "fallback"})
    return JsonResponse(quiz)


@csrf_exempt
@require_node("englishchat", api=True)
def api_check_reorder(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    user_answer = _safe_text(body.get("user_answer"))
    answer = _safe_text(body.get("answer"))
    if not user_answer:
        return JsonResponse({"ok": False, "error": "user_answer is required"}, status=400)
    if not answer:
        return JsonResponse({"ok": False, "error": "answer is required"}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "correct": _normalize_plain_sentence(user_answer) == _normalize_plain_sentence(answer),
            "user_answer": user_answer,
            "answer": answer,
            "explanation_zh": _safe_text(body.get("explanation_zh")) or "請確認單字順序與句型。",
            "pattern": _safe_text(body.get("pattern")),
        }
    )


@csrf_exempt
@require_node("englishchat", api=True)
def api_translation_quiz(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    topic = _safe_text(body.get("custom_topic")) or _safe_text(body.get("topic")) or "daily life"
    level = _normalize_level(body.get("level"))
    db_item = get_db_question(topic, "translation", level, _seen_question_ids(body))
    if db_item:
        quiz = _normalize_translation_quiz(db_item, topic, level)
        quiz.update({"ok": True, "topic": topic, "level": level, "source": "question_bank"})
        return JsonResponse(quiz)
    pack_item = get_topic_pack_item(topic, "translation", level, _seen_question_ids(body))
    if pack_item:
        quiz = _normalize_translation_quiz(pack_item, topic, level)
        quiz.update({"ok": True, "topic": topic, "level": level, "source": "topic_pack"})
        return JsonResponse(quiz)

    prompt = _build_translation_prompt(topic, level)

    try:
        data = _extract_json(_invoke_llm(prompt))
    except Exception:
        data = {}

    quiz = _normalize_translation_quiz(data, topic, level)
    quiz.update({"ok": True, "topic": topic, "level": level, "source": "llm" if data else "fallback"})
    return JsonResponse(quiz)


@csrf_exempt
@require_node("englishchat", api=True)
def api_evaluate_translation(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    user_answer = _safe_text(body.get("user_answer"))
    if not user_answer:
        return JsonResponse({"ok": False, "error": "user_answer is required"}, status=400)

    zh_prompt = _safe_text(body.get("zh_prompt"))
    sample_answer = _safe_text(body.get("sample_answer"))
    level = _normalize_level(body.get("level"))
    prompt = _build_translation_evaluation_prompt(zh_prompt, user_answer, sample_answer, level)

    try:
        data = _extract_json(_invoke_llm(prompt))
    except Exception:
        data = {}

    try:
        score = int(data.get("score"))
    except Exception:
        score = 100 if _normalize_plain_sentence(user_answer) == _normalize_plain_sentence(sample_answer) else 70
    score = max(0, min(100, score))

    raw_suggestions = data.get("suggestions")
    suggestions = []
    if isinstance(raw_suggestions, list):
        suggestions = [_safe_text(x) for x in raw_suggestions if _safe_text(x)]
    if not suggestions:
        suggestions = ["Try to keep the sentence natural.", "Use the sample pattern again."]

    return JsonResponse(
        {
            "ok": True,
            "score": score,
            "corrected": _safe_text(data.get("corrected")) or sample_answer or user_answer,
            "feedback_zh": _safe_text(data.get("feedback_zh")) or "請比較你的句子與範例句，注意自然用法。",
            "suggestions": suggestions[:3],
            "sample_answer": sample_answer,
        }
    )


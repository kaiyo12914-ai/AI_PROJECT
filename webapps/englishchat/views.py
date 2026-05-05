from __future__ import annotations

import json
from typing import Any, Dict, List

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node

from .llm_service import EnglishChatLLMError, invoke_json, safe_text
from .quiz_pipeline import (
    LEVEL_PROFILE,
    fill_blank_prompt,
    normalize_fill_blank_quiz,
    normalize_level,
    normalize_plain_sentence,
    normalize_reorder_quiz,
    normalize_translation_quiz,
    reorder_prompt,
    run_quiz_pipeline,
    seen_question_ids,
    translation_evaluation_prompt,
    translation_prompt,
)

TOPIC_PRESETS = ["旅遊", "餐廳", "購物", "學校", "會議", "電話", "健身", "天氣"]


@require_node("englishchat")
def index(request):
    return render(
        request,
        "englishchat/index.html",
        {
            "topic_presets": TOPIC_PRESETS,
            "debug_mode": bool(getattr(settings, "DEBUG", False)),
        },
    )


def _read_json_body(request) -> Dict[str, Any] | None:
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return None


def _practice_summary(attempts: Any) -> Dict[str, Any]:
    rows = attempts if isinstance(attempts, list) else []
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mode = safe_text(row.get("mode")) or "practice"
        pattern = safe_text(row.get("pattern"))
        correct = bool(row.get("correct"))
        try:
            score = int(row.get("score")) if row.get("score") is not None else (100 if correct else 0)
        except Exception:
            score = 100 if correct else 0
        cleaned.append({"mode": mode, "correct": correct, "score": max(0, min(100, score)), "pattern": pattern})

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

    recommendations = []
    if not total:
        recommendations.append("Start with one short fill-in-the-blank question.")
    if "fill_blank" in weak_modes:
        recommendations.append("Review the grammar pattern, then try another fill-in-the-blank question.")
    if "reorder" in weak_modes:
        recommendations.append("Practice word order: subject + verb + object/complement.")
    if "translate" in weak_modes or "translation" in weak_modes:
        recommendations.append("Compare your translation with the sample answer and reuse one pattern.")
    for pattern in sorted(weak_patterns, key=lambda key: (-weak_patterns[key], key))[:3]:
        recommendations.append(f"Review: {pattern}")
    if total and not recommendations:
        recommendations.append("Good session. Try a harder level or switch to translation practice.")

    return {
        "total": total,
        "correct": correct_count,
        "accuracy": accuracy,
        "average_score": average_score,
        "weak_modes": sorted(weak_modes, key=lambda key: (-weak_modes[key], key))[:3],
        "weak_patterns": sorted(weak_patterns, key=lambda key: (-weak_patterns[key], key))[:3],
        "recommendations": recommendations[:5],
    }


@csrf_exempt
@require_node("englishchat", api=True)
def api_start(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    topic = safe_text(body.get("custom_topic")) or safe_text(body.get("topic")) or "daily life"
    level = normalize_level(body.get("level"))
    opening = "Hey! Great to chat with you. What would you like to talk about first?"
    zh_hint = "先用一兩句簡單英文開始。"
    starters = [
        "I want to practice this topic.",
        "Can we start with an easy situation?",
        "Please correct my English while we chat.",
    ]
    prompt = f"""
You are an American-English speaking partner.
Topic: {topic}
Level: {level}
Level policy: {LEVEL_PROFILE[level]}
Output JSON only:
{{
  "opening": "one friendly opening message in American English",
  "zh_hint": "short Traditional Chinese hint",
  "starter_sentences": ["3 practical reply options in English"]
}}
""".strip()
    try:
        data = invoke_json(prompt, purpose="start_chat")
        opening = safe_text(data.get("opening")) or opening
        zh_hint = safe_text(data.get("zh_hint")) or zh_hint
        if isinstance(data.get("starter_sentences"), list):
            parsed = [safe_text(item) for item in data["starter_sentences"] if safe_text(item)]
            if parsed:
                starters = parsed[:3]
    except EnglishChatLLMError:
        pass
    return JsonResponse({"ok": True, "topic": topic, "level": level, "opening": opening, "zh_hint": zh_hint, "starter_sentences": starters})


@csrf_exempt
@require_node("englishchat", api=True)
def api_chat(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    topic = safe_text(body.get("topic")) or "daily life"
    level = normalize_level(body.get("level"))
    user_text = safe_text(body.get("user_text"))
    if not user_text:
        return JsonResponse({"ok": False, "error": "user_text is required"}, status=400)

    transcript_lines: List[str] = []
    for item in (body.get("messages") or [])[-10:]:
        if not isinstance(item, dict):
            continue
        role = safe_text(item.get("role")).lower()
        text = safe_text(item.get("text"))
        if text:
            transcript_lines.append(f"{'User' if role == 'user' else 'Coach'}: {text}")

    prompt = f"""
You are an American-English conversation coach.
Topic: {topic}
Level: {level}
Level policy: {LEVEL_PROFILE[level]}
Recent chat:
{chr(10).join(transcript_lines)}
User latest message: {user_text}
Output JSON only:
{{
  "ai_reply": "natural next message",
  "correction": {{"original": "sentence", "improved": "better sentence", "why": "Traditional Chinese explanation"}},
  "suggestions": ["up to 3 short reusable patterns"],
  "zh_hint": "short Traditional Chinese hint"
}}
""".strip()
    fallback = {
        "ai_reply": "Nice. Tell me one more detail so we can keep the conversation going.",
        "correction": {"original": user_text, "improved": user_text, "why": "這句大致可以理解，接下來再調整語氣自然度。"},
        "suggestions": ["Can you tell me more about that?", "In my opinion, ...", "I usually ... because ..."],
        "zh_hint": "再補一個細節會更自然。",
    }
    try:
        data = invoke_json(prompt, purpose="chat_reply")
    except EnglishChatLLMError:
        data = {}
    correction = data.get("correction") if isinstance(data.get("correction"), dict) else {}
    suggestions = [safe_text(item) for item in data.get("suggestions", []) if safe_text(item)] if isinstance(data.get("suggestions"), list) else []
    return JsonResponse(
        {
            "ok": True,
            "ai_reply": safe_text(data.get("ai_reply")) or fallback["ai_reply"],
            "correction": {
                "original": safe_text(correction.get("original")) or fallback["correction"]["original"],
                "improved": safe_text(correction.get("improved")) or fallback["correction"]["improved"],
                "why": safe_text(correction.get("why")) or fallback["correction"]["why"],
            },
            "suggestions": (suggestions or fallback["suggestions"])[:3],
            "zh_hint": safe_text(data.get("zh_hint")) or fallback["zh_hint"],
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
    topic = safe_text(body.get("custom_topic")) or safe_text(body.get("topic")) or "daily life"
    level = normalize_level(body.get("level"))
    quiz = run_quiz_pipeline(
        topic=topic,
        level=level,
        mode="fill_blank",
        exclude_ids=seen_question_ids(body),
        normalize=normalize_fill_blank_quiz,
        prompt_builder=fill_blank_prompt,
    )
    quiz.update({"ok": True, "topic": topic, "level": level})
    return JsonResponse(quiz)


@csrf_exempt
@require_node("englishchat", api=True)
def api_check_fill_blank(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    selected = safe_text(body.get("selected"))
    answer = safe_text(body.get("answer"))
    if not selected:
        return JsonResponse({"ok": False, "error": "selected is required"}, status=400)
    if not answer:
        return JsonResponse({"ok": False, "error": "answer is required"}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "correct": selected.lower() == answer.lower(),
            "selected": selected,
            "answer": answer,
            "explanation_zh": safe_text(body.get("explanation_zh")) or "回想這個句型的動詞形式。",
            "pattern": safe_text(body.get("pattern")),
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
    topic = safe_text(body.get("custom_topic")) or safe_text(body.get("topic")) or "daily life"
    level = normalize_level(body.get("level"))
    quiz = run_quiz_pipeline(
        topic=topic,
        level=level,
        mode="reorder",
        exclude_ids=seen_question_ids(body),
        normalize=normalize_reorder_quiz,
        prompt_builder=reorder_prompt,
    )
    quiz.update({"ok": True, "topic": topic, "level": level})
    return JsonResponse(quiz)


@csrf_exempt
@require_node("englishchat", api=True)
def api_check_reorder(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    user_answer = safe_text(body.get("user_answer"))
    answer = safe_text(body.get("answer"))
    if not user_answer:
        return JsonResponse({"ok": False, "error": "user_answer is required"}, status=400)
    if not answer:
        return JsonResponse({"ok": False, "error": "answer is required"}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "correct": normalize_plain_sentence(user_answer) == normalize_plain_sentence(answer),
            "user_answer": user_answer,
            "answer": answer,
            "explanation_zh": safe_text(body.get("explanation_zh")) or "注意英文自然語序。",
            "pattern": safe_text(body.get("pattern")),
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
    topic = safe_text(body.get("custom_topic")) or safe_text(body.get("topic")) or "daily life"
    level = normalize_level(body.get("level"))
    quiz = run_quiz_pipeline(
        topic=topic,
        level=level,
        mode="translation",
        exclude_ids=seen_question_ids(body),
        normalize=normalize_translation_quiz,
        prompt_builder=translation_prompt,
    )
    quiz.update({"ok": True, "topic": topic, "level": level})
    return JsonResponse(quiz)


@csrf_exempt
@require_node("englishchat", api=True)
def api_evaluate_translation(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    user_answer = safe_text(body.get("user_answer"))
    if not user_answer:
        return JsonResponse({"ok": False, "error": "user_answer is required"}, status=400)
    zh_prompt = safe_text(body.get("zh_prompt"))
    sample_answer = safe_text(body.get("sample_answer"))
    level = normalize_level(body.get("level"))
    try:
        data = invoke_json(
            translation_evaluation_prompt(zh_prompt, user_answer, sample_answer, level),
            purpose="translation_evaluation",
        )
    except EnglishChatLLMError:
        data = {}
    try:
        score = int(data.get("score"))
    except Exception:
        score = 100 if normalize_plain_sentence(user_answer) == normalize_plain_sentence(sample_answer) else 70
    suggestions = [safe_text(item) for item in data.get("suggestions", []) if safe_text(item)] if isinstance(data.get("suggestions"), list) else []
    if not suggestions:
        suggestions = ["Try to keep the sentence natural.", "Reuse the sample pattern once more."]
    return JsonResponse(
        {
            "ok": True,
            "score": max(0, min(100, score)),
            "corrected": safe_text(data.get("corrected")) or sample_answer or user_answer,
            "feedback_zh": safe_text(data.get("feedback_zh")) or "先確認句意正確，再調整成更自然的英文。",
            "suggestions": suggestions[:3],
            "sample_answer": sample_answer,
        }
    )

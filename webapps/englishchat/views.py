from __future__ import annotations

import json
from typing import Any, Dict, List

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node


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


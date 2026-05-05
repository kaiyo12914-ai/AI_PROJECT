from __future__ import annotations

from typing import Any, Dict, List

from .question_catalog import LEVEL_SETTINGS, QUESTION_TOPICS


def build_seed_questions() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for topic in QUESTION_TOPICS:
        for level, setting in LEVEL_SETTINGS.items():
            rows.extend(_build_fill_blank(topic, level, setting))
            rows.extend(_build_reorder(topic, level, setting))
            rows.extend(_build_translation(topic, level, setting))
    return rows


def _build_fill_blank(topic: Dict[str, Any], level: str, setting: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, pattern in enumerate(setting["patterns"], start=1):
        v = _variant(topic, level, setting, index - 1)
        answer = _format(pattern["en"], v)
        rows.append(
            _row(
                topic,
                level,
                "fill_blank",
                index,
                prompt_text=_blank_answer(answer, v["verb"]),
                choices_json=_choices(level, v["verb"]),
                answer_text=v["verb"],
                explanation_zh=f"{setting['zh_label']}句型：{pattern['zh']}",
                pattern_text=answer,
            )
        )
    return rows


def _build_reorder(topic: Dict[str, Any], level: str, setting: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, pattern in enumerate(setting["patterns"], start=1):
        v = _variant(topic, level, setting, index - 1)
        answer = _format(pattern["en"], v)
        rows.append(
            _row(
                topic,
                level,
                "reorder",
                index,
                prompt_text="Put the words in the correct order.",
                words_json=_word_bank(answer),
                answer_text=answer,
                explanation_zh=f"{setting['zh_label']}句型重組。",
                pattern_text=answer,
            )
        )
    return rows


def _build_translation(topic: Dict[str, Any], level: str, setting: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, pattern in enumerate(setting["patterns"], start=1):
        v = _variant(topic, level, setting, index - 1)
        rows.append(
            _row(
                topic,
                level,
                "translation",
                index,
                zh_prompt=_format(pattern["zh"], v),
                sample_answer=_format(pattern["en"], v),
                explanation_zh=f"{setting['zh_label']}翻譯句型。",
                patterns_json=[_pattern_hint(pattern["en"], v)],
            )
        )
    return rows


def _variant(topic: Dict[str, Any], level: str, setting: Dict[str, Any], offset: int) -> Dict[str, str]:
    items = topic.get("items_by_level", {}).get(level) or topic["items"]
    item = items[offset % len(items)]
    place = topic["places"][offset % len(topic["places"])]
    reason = topic["reasons"][offset % len(topic["reasons"])]
    modal_cap, closer_zh, closer = setting["modals"][0]
    adverb, adverb_zh = setting["adverbs"][0]
    time_phrase, time_phrase_zh = setting["time_phrases"][0]
    subject = str(topic["subject"])
    return {
        "subject": subject if subject == "I" else subject.lower(),
        "subject_cap": subject.capitalize(),
        "subject_zh": "我" if subject == "I" else "我們",
        "wondering_clause": "I was wondering if I could" if subject == "I" else "We were wondering if we could",
        "verb": str(topic["verb"][level]),
        "verb_zh": str(topic["verb_zh"]),
        "item": str(item["en"]),
        "item_zh": str(item["zh"]),
        "place": str(place["en"]),
        "place_zh": str(place["zh"]),
        "reason": str(reason[0]),
        "reason_zh": str(reason[1]),
        "modal_cap": modal_cap,
        "closer": closer,
        "closer_zh": closer_zh,
        "adverb": adverb,
        "adverb_zh": adverb_zh,
        "time_phrase": time_phrase,
        "time_phrase_zh": time_phrase_zh,
    }


def _blank_answer(sentence: str, verb: str) -> str:
    return sentence.replace(f" {verb} ", " ____ ", 1)


def _choices(level: str, verb: str) -> List[str]:
    if level == "beginner":
        return [verb, f"{verb}s", f"{verb}ing"]
    if level == "intermediate":
        return [verb, f"to {verb}", f"{verb}ed"]
    return [verb, f"{verb}ing", f"to {verb}"]


def _word_bank(answer: str) -> List[str]:
    sentence = answer.rstrip(".?")
    words = sentence.split()
    if len(words) >= 4:
        return words[1:] + words[:1]
    return list(reversed(words))


def _pattern_hint(pattern: str, values: Dict[str, str]) -> str:
    hint = pattern
    for key in ("subject", "subject_cap", "item", "place", "reason", "closer", "time_phrase", "adverb", "wondering_clause"):
        hint = hint.replace("{" + key + "}", "...")
    return hint


def _format(template: str, values: Dict[str, str]) -> str:
    return template.format(**values)


def _row(topic: Dict[str, Any], level: str, mode: str, sort_order: int, **kwargs: Any) -> Dict[str, Any]:
    row = {
        "question_id": f"seed-{topic['key']}-{mode}-{level}-{sort_order:03d}",
        "topic_key": topic["key"],
        "mode": mode,
        "level": level,
        "prompt_text": "",
        "choices_json": [],
        "words_json": [],
        "answer_text": "",
        "explanation_zh": "",
        "pattern_text": "",
        "zh_prompt": "",
        "sample_answer": "",
        "patterns_json": [],
        "sort_order": sort_order,
    }
    row.update(kwargs)
    return row

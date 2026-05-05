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
        values = _variant(topic, level, index - 1)
        answer_sentence = pattern["en"].format(**values)
        rows.append(
            _row(
                topic,
                level,
                "fill_blank",
                index,
                prompt_text=_blank_first_verb(answer_sentence, values["verb"]),
                choices_json=_choices(level, values["verb"]),
                answer_text=values["verb"],
                explanation_zh=f"{setting['zh_label']}句型練習：{pattern['zh'].format(**values)}",
                pattern_text=answer_sentence,
            )
        )
    return rows


def _build_reorder(topic: Dict[str, Any], level: str, setting: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, pattern in enumerate(setting["patterns"], start=1):
        values = _variant(topic, level, index - 1)
        answer_sentence = pattern["en"].format(**values)
        rows.append(
            _row(
                topic,
                level,
                "reorder",
                index,
                prompt_text="Put the words in the correct order.",
                words_json=_word_bank(answer_sentence),
                answer_text=answer_sentence,
                explanation_zh=f"{setting['zh_label']}語序練習：請依照自然英文順序重組句子。",
                pattern_text=answer_sentence,
            )
        )
    return rows


def _build_translation(topic: Dict[str, Any], level: str, setting: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, pattern in enumerate(setting["patterns"], start=1):
        values = _variant(topic, level, index - 1)
        rows.append(
            _row(
                topic,
                level,
                "translation",
                index,
                zh_prompt=pattern["zh"].format(**values),
                sample_answer=pattern["en"].format(**values),
                explanation_zh=f"{setting['zh_label']}翻譯練習：注意主詞、動詞與情境搭配。",
                patterns_json=[_pattern_hint(pattern["en"])],
            )
        )
    return rows


def _variant(topic: Dict[str, Any], level: str, offset: int) -> Dict[str, str]:
    items = topic.get("items_by_level", {}).get(level) or topic["items"]
    item = items[offset % len(items)]
    place = topic["places"][offset % len(topic["places"])]
    reason = topic["reasons"][offset % len(topic["reasons"])]
    adverb, adverb_zh = LEVEL_SETTINGS[level]["adverbs"][0]
    time_phrase, time_phrase_zh = LEVEL_SETTINGS[level]["time_phrases"][0]
    subject = str(topic["subject"])
    subject_cap = "I" if subject == "I" else subject.capitalize()
    return {
        "subject": subject.lower() if subject != "I" else "I",
        "subject_cap": subject_cap,
        "subject_zh": str(topic["subject_zh"]),
        "verb": str(topic["verb"][level]),
        "verb_zh": str(topic["verb_zh"]),
        "item": str(item["en"]),
        "item_zh": str(item["zh"]),
        "place": str(place["en"]),
        "place_zh": str(place["zh"]),
        "reason": str(reason[0]),
        "reason_zh": str(reason[1]),
        "adverb": adverb,
        "adverb_zh": adverb_zh,
        "time_phrase": time_phrase,
        "time_phrase_zh": time_phrase_zh,
    }


def _blank_first_verb(sentence: str, verb: str) -> str:
    return sentence.replace(f" {verb} ", " ____ ", 1)


def _choices(level: str, verb: str) -> List[str]:
    if level == "beginner":
        return [verb, f"{verb}s", f"{verb}ing"]
    if level == "intermediate":
        return [verb, f"to {verb}", f"{verb}ed"]
    return [verb, f"{verb}ing", f"to {verb}"]


def _word_bank(answer: str) -> List[str]:
    words = answer.rstrip(".?").split()
    if len(words) >= 4:
        return words[1:] + words[:1]
    return list(reversed(words))


def _pattern_hint(template: str) -> str:
    hint = template
    for field in ["subject", "subject_cap", "verb", "item", "place", "reason", "adverb", "time_phrase"]:
        hint = hint.replace("{" + field + "}", "...")
    return hint


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

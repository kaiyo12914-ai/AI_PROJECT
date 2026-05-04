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


def _build_fill_blank(topic: Dict[str, Any], level: str, setting: Dict[str, str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    templates = [
        ("{subject_cap} usually ____ {item} {place}.", "這題練習一般現在式。", "{subject_cap} usually {verb} {item} {place}.", ["check", "{verb}", "cancel"]),
        ("{modal_cap} {subject} ____ {item} {closer}?", "助動詞後面接原形動詞。", "{modal_cap} {subject} {verb} {item} {closer}?", ["{verb}", "{verb}ing", "to {verb}"]),
        ("{subject_cap} need to ____ {item} {time_phrase}.", "need to 後面接原形動詞。", "{subject_cap} need to {verb} {item} {time_phrase}.", ["{verb}", "{verb}s", "{verb}ed"]),
        ("Please ____ {item} {adverb}.", "Please 後面接原形動詞。", "Please {verb} {item} {adverb}.", ["{verb}", "{verb}s", "{verb}ing"]),
        ("{subject_cap} am going to ____ {item} later.", "be going to 後面接原形動詞。", "{subject_cap} am going to {verb} {item} later.", ["{verb}", "{verb}s", "{verb}ed"]),
        ("Let's ____ {item} together.", "Let's 後面接原形動詞。", "Let's {verb} {item} together.", ["{verb}", "{verb}ed", "{verb}ing"]),
        ("{subject_cap} want to ____ {item} after work.", "want to 後面接原形動詞。", "{subject_cap} want to {verb} {item} after work.", ["{verb}", "{verb}s", "{verb}ed"]),
        ("{subject_cap} often ____ {item} with the team.", "often 常放在一般動詞前。", "{subject_cap} often {verb} {item} with the team.", ["{verb}", "{verb}ing", "to {verb}"]),
        ("Do {subject} ____ {item} every day?", "Do 問句後面接原形動詞。", "Do {subject} {verb} {item} every day?", ["{verb}", "{verb}s", "{verb}ed"]),
        ("{subject_cap} tried to ____ {item} yesterday.", "tried to 後面接原形動詞。", "{subject_cap} tried to {verb} {item} yesterday.", ["{verb}", "{verb}ing", "{verb}s"]),
        ("{subject_cap} can ____ {item} right now.", "can 後面接原形動詞。", "{subject_cap} can {verb} {item} right now.", ["{verb}", "{verb}ed", "{verb}ing"]),
        ("{subject_cap} will ____ {item} tomorrow.", "will 後面接原形動詞。", "{subject_cap} will {verb} {item} tomorrow.", ["{verb}", "{verb}s", "{verb}ing"]),
    ]
    variants = _topic_variants(topic, setting)
    for index, (prompt_tmpl, explanation, pattern_tmpl, choice_tmpls) in enumerate(templates, start=1):
        variant = variants[(index - 1) % len(variants)]
        rows.append(
            _row(
                topic,
                level,
                "fill_blank",
                index,
                prompt_text=_fmt(prompt_tmpl, variant),
                choices_json=[_fmt(choice, variant) for choice in choice_tmpls],
                answer_text=variant["verb"],
                explanation_zh=f"{explanation} 主題詞是「{variant['item_zh']}」。",
                pattern_text=_fmt(pattern_tmpl, variant),
            )
        )
    return rows


def _build_reorder(topic: Dict[str, Any], level: str, setting: Dict[str, str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    templates = [
        (["{verb}", "{subject_cap}", "{item}", "{place}"], "{subject_cap} {verb} {item} {place}.", "按照英文基本語序排列。"),
        (["{item}", "{modal_cap}", "{subject}", "{verb}", "{closer}"], "{modal_cap} {subject} {verb} {item} {closer}?", "助動詞問句是助動詞 + 主詞 + 原形動詞。"),
        (["{subject_cap}", "need to", "{verb}", "{item}", "{time_phrase}"], "{subject_cap} need to {verb} {item} {time_phrase}.", "need to 後面接原形動詞。"),
        (["{adverb}", "{verb}", "Please", "{item}"], "Please {verb} {item} {adverb}.", "祈使句用原形動詞。"),
        (["{subject_cap}", "am going to", "{verb}", "{item}", "later"], "{subject_cap} am going to {verb} {item} later.", "be going to 表示即將要做的事。"),
        (["{verb}", "{item}", "Let's", "together"], "Let's {verb} {item} together.", "Let's 後面接原形動詞。"),
        (["{subject_cap}", "want to", "{verb}", "{item}", "after work"], "{subject_cap} want to {verb} {item} after work.", "want to 後面接原形動詞。"),
        (["often", "{subject_cap}", "{verb}", "{item}", "with the team"], "{subject_cap} often {verb} {item} with the team.", "頻率副詞 often 常放在一般動詞前。"),
        (["{subject}", "{verb}", "{item}", "every day", "Do"], "Do {subject} {verb} {item} every day?", "Do 問句用原形動詞。"),
        (["{subject_cap}", "tried to", "{verb}", "{item}", "yesterday"], "{subject_cap} tried to {verb} {item} yesterday.", "tried to 後面接原形動詞。"),
        (["{subject_cap}", "can", "{verb}", "{item}", "right now"], "{subject_cap} can {verb} {item} right now.", "can 後面接原形動詞。"),
        (["{subject_cap}", "will", "{verb}", "{item}", "tomorrow"], "{subject_cap} will {verb} {item} tomorrow.", "will 後面接原形動詞。"),
    ]
    variants = _topic_variants(topic, setting)
    for index, (word_tmpls, answer_tmpl, explanation) in enumerate(templates, start=1):
        variant = variants[(index - 1) % len(variants)]
        rows.append(
            _row(
                topic,
                level,
                "reorder",
                index,
                prompt_text="Put the words in the correct order.",
                words_json=[_fmt(word, variant) for word in word_tmpls],
                answer_text=_fmt(answer_tmpl, variant),
                explanation_zh=f"{explanation} 主題詞是「{variant['item_zh']}」。",
                pattern_text=_fmt(answer_tmpl, variant),
            )
        )
    return rows


def _build_translation(topic: Dict[str, Any], level: str, setting: Dict[str, str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    templates = [
        ("{subject_zh}通常會{verb_zh}{item_zh}。", "{subject_cap} usually {verb} {item} {place}.", "練習主詞 + 副詞 + 動詞。", ["{subject_cap} usually {verb} ...", "{verb} {item}"]),
        ("{subject_zh}{closer_zh}{verb_zh}{item_zh}可以嗎？", "{modal_cap} {subject} {verb} {item} {closer}?", "練習禮貌詢問句。", ["{modal_cap} {subject} {verb} ...?", "{closer}"]),
        ("{subject_zh}需要在{time_phrase_zh}{verb_zh}{item_zh}。", "{subject_cap} need to {verb} {item} {time_phrase}.", "練習 need to 句型。", ["{subject_cap} need to {verb} ...", "{time_phrase}"]),
        ("請{adverb_zh}{verb_zh}{item_zh}。", "Please {verb} {item} {adverb}.", "練習祈使句。", ["Please {verb} ...", "{adverb}"]),
        ("{subject_zh}等一下要{verb_zh}{item_zh}。", "{subject_cap} am going to {verb} {item} later.", "練習 be going to 句型。", ["{subject_cap} am going to {verb} ...", "later"]),
        ("我們一起{verb_zh}{item_zh}吧。", "Let's {verb} {item} together.", "練習 Let's 句型。", ["Let's {verb} ...", "together"]),
        ("{subject_zh}下班後想要{verb_zh}{item_zh}。", "{subject_cap} want to {verb} {item} after work.", "練習 want to 句型。", ["{subject_cap} want to {verb} ...", "after work"]),
        ("{subject_zh}常常和團隊一起{verb_zh}{item_zh}。", "{subject_cap} often {verb} {item} with the team.", "練習 often 的位置。", ["{subject_cap} often {verb} ...", "with the team"]),
        ("{subject_zh}每天都會{verb_zh}{item_zh}嗎？", "Do {subject} {verb} {item} every day?", "練習 Do 問句。", ["Do {subject} {verb} ...?", "every day"]),
        ("{subject_zh}昨天試著{verb_zh}{item_zh}。", "{subject_cap} tried to {verb} {item} yesterday.", "練習 tried to 句型。", ["{subject_cap} tried to {verb} ...", "yesterday"]),
        ("{subject_zh}現在可以{verb_zh}{item_zh}。", "{subject_cap} can {verb} {item} right now.", "練習 can 句型。", ["{subject_cap} can {verb} ...", "right now"]),
        ("{subject_zh}明天會{verb_zh}{item_zh}。", "{subject_cap} will {verb} {item} tomorrow.", "練習 will 句型。", ["{subject_cap} will {verb} ...", "tomorrow"]),
    ]
    variants = _topic_variants(topic, setting)
    for index, (zh_tmpl, answer_tmpl, explanation, patterns) in enumerate(templates, start=1):
        variant = variants[(index - 1) % len(variants)]
        rows.append(
            _row(
                topic,
                level,
                "translation",
                index,
                zh_prompt=_fmt(zh_tmpl, variant),
                sample_answer=_fmt(answer_tmpl, variant),
                explanation_zh=f"{explanation} 主題詞是「{variant['item_zh']}」。",
                patterns_json=[_fmt(pattern, variant) for pattern in patterns],
            )
        )
    return rows


def _topic_variants(topic: Dict[str, Any], setting: Dict[str, str]) -> List[Dict[str, str]]:
    subject = str(topic["subject"])
    subject_cap = subject.capitalize()
    subject_zh = "我" if subject == "I" else "我們"
    modal = str(setting["modal"])
    modal_cap = modal.capitalize()
    variants: List[Dict[str, str]] = []
    synonym_pool = [str(topic["verb"])] + [str(item) for item in topic.get("synonyms", [])]
    for item_index, item in enumerate(topic.get("items", [])):
        place = topic.get("places", [])[item_index % len(topic.get("places", []))]
        verb = synonym_pool[item_index % len(synonym_pool)]
        variants.append(
            {
                "subject": subject,
                "subject_cap": subject_cap,
                "subject_zh": subject_zh,
                "verb": verb,
                "verb_zh": str(topic["verb_zh"]),
                "item": str(item["en"]),
                "item_zh": str(item["zh"]),
                "place": str(place["en"]),
                "place_zh": str(place["zh"]),
                "modal": modal,
                "modal_cap": modal_cap,
                "closer": str(setting["closer"]),
                "closer_zh": _to_zh_closer(str(setting["closer"])),
                "adverb": str(setting["adverb"]),
                "adverb_zh": _to_zh_adverb(str(setting["adverb"])),
                "time_phrase": str(setting["time_phrase"]),
                "time_phrase_zh": _to_zh_time_phrase(str(setting["time_phrase"])),
            }
        )
    return variants


def _to_zh_closer(value: str) -> str:
    mapping = {
        "today": "今天",
        "this week": "這週",
        "as soon as possible": "儘快",
    }
    return mapping.get(value, value)


def _to_zh_adverb(value: str) -> str:
    mapping = {
        "carefully": "仔細地",
        "efficiently": "有效率地",
        "strategically": "有策略地",
    }
    return mapping.get(value, value)


def _to_zh_time_phrase(value: str) -> str:
    mapping = {
        "this morning": "今天早上",
        "before lunch": "午餐前",
        "before the deadline": "截止前",
    }
    return mapping.get(value, value)


def _fmt(template: str, values: Dict[str, str]) -> str:
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

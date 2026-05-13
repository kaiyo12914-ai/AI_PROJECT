from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")

import django

django.setup()

from webapps.englishchat.llm_service import EnglishChatLLMError, invoke_json_array
from webapps.englishchat.repository import EnglishChatQuestionBankRepository

TOPICS = ["meeting", "phone", "restaurant", "travel", "shopping", "school", "fitness", "hospital", "weather", "self_intro"]
MODES = ["fill_blank", "reorder", "translation"]
LEVELS = ["beginner", "intermediate", "advanced"]
GENERATED_PREFIX = "ai-toeic-coca-"
DEFAULT_QUESTIONS_PER_COMBO = 1
DEFAULT_SORT_ORDER_BASE = 100
REPORT_DIR = Path(PROJECT_ROOT) / "scratch" / "reports"


class QuestionGenerationError(Exception):
    pass


@dataclass
class ComboResult:
    topic: str
    mode: str
    level: str
    requested_count: int
    inserted_or_updated: int = 0
    deactivated: int = 0
    skipped_duplicates: int = 0
    failures: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="產生 TOEIC/COCA 題目並寫入 englishchat_question_bank。")
    parser.add_argument("--questions-per-combo", type=int, default=DEFAULT_QUESTIONS_PER_COMBO)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--topics", nargs="*", choices=TOPICS)
    parser.add_argument("--modes", nargs="*", choices=MODES)
    parser.add_argument("--levels", nargs="*", choices=LEVELS)
    return parser.parse_args()


def build_prompt(
    topic: str,
    mode: str,
    level: str,
    requested_count: int,
    banned_signatures: Sequence[str] | None = None,
) -> str:
    beginner_translation_hint = ""
    beginner_level_hint = ""
    if level == "beginner":
        beginner_level_hint = """
beginner 題目請額外遵守以下簡化規則：
- 難度請對齊 CEFR A1/A2。
- 字彙優先參考 Oxford 3000、NGSL 高頻字、GEPT 初級、國中基礎英文常見用字。
- 題型風格可參考 GEPT 初級、國中英文、初級 ESL 練習題。
- 保留 TOEIC/生活情境，但句子必須改寫成初學者也能理解的簡單英文。
- 優先使用日常高頻動詞，例如 `be`, `have`, `go`, `like`, `want`, `need`, `work`, `call`, `eat`, `come`。
- 句子盡量短，避免複句、被動語態、假設語氣、關係子句、分詞構句與過度商務化字彙。
- 一題只考一個重點，不要同時考多個文法或多層語意推理。
- fill_blank 盡量以單字或短片語為答案。
- reorder 盡量控制在 4 到 6 個 words/chunks。
- translation 只出單句，句意要直接、清楚、自然。
"""
    if mode == "translation" and level == "beginner":
        beginner_translation_hint = """
6. beginner 的 translation 題型必須提供額外提示：
   - `patterns_json` 至少要有 3 個簡短提示。
   - 內容必須包含：
     1. 一個句型提示，
     2. 一個關鍵動詞片語，
     3. 一個單字或文法提示。
   - `explanation_zh` 必須用繁體中文清楚說明主詞、動詞型態，以及一個關鍵用字。
   - `sample_answer` 應保持簡短、基礎。
"""
    banned_clause = ""
    if banned_signatures:
        banned_preview = "\n".join(f"- {sig}" for sig in list(banned_signatures)[:30])
        banned_clause = f"\n10. Avoid generating questions that match these existing signatures:\n{banned_preview}\n"

    return f"""
請產生 {requested_count} 題 TOEIC 風格英文練習題，語言要貼近日常實用英文，並參考 COCA 常見用法。

主題：{topic}
題型：{mode}（fill_blank / reorder / translation）
難度：{level}（beginner / intermediate / advanced）

只能回傳 JSON array。
第一個字必須是 `[`，最後一個字必須是 `]`。
不要使用 markdown。
不要加入任何額外說明、前言、結語、註解或 code fence。
不要輸出 ```json 或 ```。
每一題都必須保留所有 key，不可以省略欄位。
若某欄位該題型不使用，請填 `""` 或 `[]`，不要填 null。
除了 JSON array 之外，不要輸出任何文字。
[
  {{
    "prompt_text": "題目文字",
    "choices_json": ["選項A", "選項B", "選項C"],
    "words_json": ["word1", "word2"],
    "answer_text": "正確答案",
    "explanation_zh": "繁體中文解析",
    "pattern_text": "目標句型",
    "zh_prompt": "中文題目",
    "sample_answer": "英文參考答案",
    "patterns_json": ["提示1", "提示2", "提示3"]
  }}
]

規則：
1. fill_blank：
   - `prompt_text` 必須且只能包含一個 `____`。
   - `choices_json` 至少要有 3 個選項。
   - `words_json` 必須是 []。
   - `answer_text`、`explanation_zh`、`pattern_text` 必填。
2. reorder：
   - `prompt_text` 必填。
   - `words_json` 至少要有 3 個打亂順序的單字或片語。
   - `choices_json` 必須是 []（強制規則，不可放任何選項）。
   - 若 `choices_json` 不是 []，視為格式錯誤。
   - `answer_text`、`explanation_zh`、`pattern_text` 必填。
3. translation：
   - `zh_prompt`、`sample_answer`、`explanation_zh` 必填。
   - `explanation_zh` 至少 12 個字，需說明關鍵句型或文法重點。
   - `choices_json` 與 `words_json` 應為 []。
   - `patterns_json` 應提供對學習者有幫助的提示。
4. 每一題都必須符合指定難度。
5. 避免重複題與近似題。
6. 題目內容必須自然、可用於真實情境，不要出現奇怪或生硬的英文。
7. `requested_count` 是 {requested_count}，請輸出剛好 {requested_count} 個 array 元素，不多也不少。
8. 若你差點想輸出說明文字，請刪除，只保留合法 JSON array。
9. 若 level 是 beginner，請優先以初級英文教材風格出題，而不是標準 TOEIC 中高難度句型。
{beginner_level_hint}
{beginner_translation_hint}
{banned_clause}
""".strip()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_string_list(value: Any, field_name: str) -> List[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise QuestionGenerationError(f"{field_name} must be a list.")
    normalized = [normalize_text(item) for item in value]
    if any(not item for item in normalized):
        raise QuestionGenerationError(f"{field_name} cannot contain empty strings.")
    return normalized


def build_translation_explanation_fallback(sample_answer: str, patterns: Sequence[str]) -> str:
    pattern_text = "、".join([normalize_text(p) for p in patterns if normalize_text(p)][:2])
    if pattern_text:
        return f"此句建議使用「{pattern_text}」等句型，請注意語序與動詞形式。"
    if sample_answer:
        return "此句請對照參考答案，注意主詞、動詞與語序是否正確。"
    return "請使用自然且正確的英文語序完成翻譯。"


def question_signature(item: Dict[str, Any]) -> str:
    mode = normalize_text(item.get("mode")).lower()
    topic = normalize_text(item.get("topic_key")).lower()
    level = normalize_text(item.get("level")).lower()
    prompt = normalize_text(item.get("prompt_text")).lower()
    answer = normalize_text(item.get("answer_text")).lower()
    zh_prompt = normalize_text(item.get("zh_prompt")).lower()
    sample_answer = normalize_text(item.get("sample_answer")).lower()
    words = " ".join(normalize_string_list(item.get("words_json"), "words_json")).lower()

    if mode == "fill_blank":
        core = f"{prompt}|{answer}"
    elif mode == "reorder":
        core = f"{prompt}|{answer}|{words}"
    elif mode == "translation":
        core = f"{zh_prompt}|{sample_answer}"
    else:
        core = f"{prompt}|{answer}|{zh_prompt}|{sample_answer}|{words}"
    return f"{topic}|{mode}|{level}|{core}"


def validate_item(item: Any, topic: str, mode: str, level: str, sort_order: int) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise QuestionGenerationError("Each question item must be an object.")

    normalized = {
        "topic_key": topic,
        "mode": mode,
        "level": level,
        "prompt_text": normalize_text(item.get("prompt_text")),
        "choices_json": normalize_string_list(item.get("choices_json"), "choices_json"),
        "words_json": normalize_string_list(item.get("words_json"), "words_json"),
        "answer_text": normalize_text(item.get("answer_text")),
        "explanation_zh": normalize_text(item.get("explanation_zh")),
        "pattern_text": normalize_text(item.get("pattern_text")),
        "zh_prompt": normalize_text(item.get("zh_prompt")),
        "sample_answer": normalize_text(item.get("sample_answer")),
        "patterns_json": normalize_string_list(item.get("patterns_json"), "patterns_json"),
        "sort_order": sort_order,
    }

    # Auto-fix for reorder mode: choices_json must always be empty.
    if mode == "reorder":
        normalized["choices_json"] = []
    if mode == "translation" and not normalized["explanation_zh"]:
        normalized["explanation_zh"] = build_translation_explanation_fallback(
            normalized["sample_answer"],
            normalized["patterns_json"],
        )

    if not normalized["explanation_zh"]:
        raise QuestionGenerationError("explanation_zh is required.")

    if mode == "fill_blank":
        if "____" not in normalized["prompt_text"]:
            raise QuestionGenerationError("fill_blank prompt_text must contain ____.")
        if len(normalized["choices_json"]) < 3:
            raise QuestionGenerationError("fill_blank choices_json must contain at least 3 choices.")
        if normalized["words_json"]:
            raise QuestionGenerationError("fill_blank words_json must be empty.")
        if not normalized["answer_text"] or not normalized["pattern_text"]:
            raise QuestionGenerationError("fill_blank requires answer_text and pattern_text.")
    elif mode == "reorder":
        if not normalized["prompt_text"]:
            raise QuestionGenerationError("reorder prompt_text is required.")
        if len(normalized["words_json"]) < 3:
            raise QuestionGenerationError("reorder words_json must contain at least 3 words.")
        if not normalized["answer_text"] or not normalized["pattern_text"]:
            raise QuestionGenerationError("reorder requires answer_text and pattern_text.")
    elif mode == "translation":
        if not normalized["zh_prompt"] or not normalized["sample_answer"]:
            raise QuestionGenerationError("translation requires zh_prompt and sample_answer.")
        required_pattern_count = 3 if level == "beginner" else 1
        if len(normalized["patterns_json"]) < required_pattern_count:
            raise QuestionGenerationError(
                f"translation patterns_json must contain at least {required_pattern_count} pattern hints."
            )
    else:
        raise QuestionGenerationError(f"Unsupported mode: {mode}")

    normalized["question_id"] = build_question_id(normalized)
    return normalized


def build_question_id(item: Dict[str, Any]) -> str:
    payload = {
        "topic_key": item["topic_key"],
        "mode": item["mode"],
        "level": item["level"],
        "prompt_text": item["prompt_text"],
        "choices_json": item["choices_json"],
        "words_json": item["words_json"],
        "answer_text": item["answer_text"],
        "explanation_zh": item["explanation_zh"],
        "pattern_text": item["pattern_text"],
        "zh_prompt": item["zh_prompt"],
        "sample_answer": item["sample_answer"],
        "patterns_json": item["patterns_json"],
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"{GENERATED_PREFIX}{digest}"


def dedupe_items(items: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    unique_items: List[Dict[str, Any]] = []
    seen_ids = set()
    skipped = 0
    for item in items:
        question_id = item["question_id"]
        if question_id in seen_ids:
            skipped += 1
            continue
        seen_ids.add(question_id)
        unique_items.append(item)
    return unique_items, skipped


def generate_combo_questions(
    topic: str,
    mode: str,
    level: str,
    requested_count: int,
    temperature: float,
    timeout: int,
    banned_signatures: Sequence[str] | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    prompt = build_prompt(topic, mode, level, requested_count, banned_signatures=banned_signatures)
    try:
        raw_items = invoke_json_array(
            prompt,
            purpose=f"generate_question_bank:{topic}:{mode}:{level}",
            temperature=temperature,
            timeout=timeout,
            max_retries=3,
            retry_delay=2.0,
        )
    except EnglishChatLLMError as exc:
        raise QuestionGenerationError(str(exc)) from exc

    validated_items = []
    for index, item in enumerate(raw_items, start=1):
        validated_items.append(validate_item(item, topic, mode, level, DEFAULT_SORT_ORDER_BASE + index - 1))
    existing = set(banned_signatures or [])
    filtered_items: List[Dict[str, Any]] = []
    filtered_out_existing = 0
    for item in validated_items:
        if question_signature(item) in existing:
            filtered_out_existing += 1
            continue
        filtered_items.append(item)

    unique_items, skipped_duplicates = dedupe_items(filtered_items)
    skipped_duplicates += filtered_out_existing
    if len(unique_items) < requested_count:
        raise QuestionGenerationError(
            f"Expected {requested_count} unique questions but received {len(unique_items)} after dedupe; "
            f"skipped_duplicates={skipped_duplicates}."
        )
    return unique_items[:requested_count], skipped_duplicates


def write_report(report_dir: Path, summary: Dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"toeic_coca_generation_{timestamp}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def run_generation(args: argparse.Namespace) -> Tuple[Dict[str, Any], int]:
    repo = EnglishChatQuestionBankRepository()

    topics = args.topics or TOPICS
    modes = args.modes or MODES
    levels = args.levels or LEVELS

    combo_results: List[ComboResult] = []
    failures: List[Dict[str, Any]] = []
    total_upserts = 0
    total_deactivated = 0
    total_skipped_duplicates = 0

    for topic in topics:
        for mode in modes:
            for level in levels:
                combo = ComboResult(topic=topic, mode=mode, level=level, requested_count=args.questions_per_combo)
                combo_results.append(combo)
                print(f"產生組合中 topic={topic} mode={mode} level={level}")
                try:
                    existing_rows = repo.fetch_questions(topic_key=topic, mode=mode, level=level)
                    banned_signatures = [question_signature(row) for row in existing_rows]
                    items, skipped_duplicates = generate_combo_questions(
                        topic,
                        mode,
                        level,
                        args.questions_per_combo,
                        args.temperature,
                        args.timeout,
                        banned_signatures=banned_signatures,
                    )
                    keep_ids = [item["question_id"] for item in items]
                    combo.skipped_duplicates = skipped_duplicates

                    if not args.dry_run:
                        for item in items:
                            repo.upsert_question(item)
                            combo.inserted_or_updated += 1
                        combo.deactivated = repo.deactivate_generated_questions(
                            topic_key=topic,
                            mode=mode,
                            level=level,
                            keep_question_ids=keep_ids,
                            generated_prefix=GENERATED_PREFIX,
                        )
                    else:
                        combo.inserted_or_updated = len(items)

                    total_upserts += combo.inserted_or_updated
                    total_deactivated += combo.deactivated
                    total_skipped_duplicates += combo.skipped_duplicates
                except Exception as exc:
                    combo.failures += 1
                    failures.append(
                        {
                            "topic": topic,
                            "mode": mode,
                            "level": level,
                            "error": str(exc),
                        }
                    )
                    print(f"組合失敗 topic={topic} mode={mode} level={level}: {exc}")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "questions_per_combo": args.questions_per_combo,
        "totals": {
            "combos": len(combo_results),
            "upserts": total_upserts,
            "deactivated": total_deactivated,
            "skipped_duplicates": total_skipped_duplicates,
            "failures": len(failures),
        },
        "combo_results": [combo.__dict__ for combo in combo_results],
        "failures": failures,
    }
    return summary, 1 if failures else 0


def main() -> int:
    args = parse_args()
    summary, exit_code = run_generation(args)
    report_path = write_report(Path(args.report_dir), summary)

    totals = summary["totals"]
    print(
        "產生完成 "
        f"combos={totals['combos']} "
        f"upserts={totals['upserts']} "
        f"deactivated={totals['deactivated']} "
        f"skipped_duplicates={totals['skipped_duplicates']} "
        f"failures={totals['failures']}"
    )
    print(f"報告已寫入 {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

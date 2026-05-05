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

from webapps.englishchat.repository import EnglishChatQuestionBankRepository
from webapps.llm.llm_factory import get_chat_model

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
    parser = argparse.ArgumentParser(description="Generate TOEIC/COCA questions into englishchat_question_bank.")
    parser.add_argument("--questions-per-combo", type=int, default=DEFAULT_QUESTIONS_PER_COMBO)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--topics", nargs="*", choices=TOPICS)
    parser.add_argument("--modes", nargs="*", choices=MODES)
    parser.add_argument("--levels", nargs="*", choices=LEVELS)
    return parser.parse_args()


def build_prompt(topic: str, mode: str, level: str, requested_count: int) -> str:
    return f"""
請產生 {requested_count} 題 TOEIC 風格、結合 COCA 常見語料與實用情境的英文練習題。

主題: {topic}
題型: {mode} (fill_blank / reorder / translation)
難度: {level} (beginner / intermediate / advanced)

請只回傳 JSON 陣列，不要加 Markdown、說明文字或程式碼區塊。每個 item 必須包含以下欄位：
[
  {{
    "prompt_text": "英文題目。fill_blank 必須含有 ____；reorder 可寫 Put the words in the correct order.；translation 可留空字串",
    "choices_json": ["選項A", "選項B", "選項C"],
    "words_json": ["word1", "word2"],
    "answer_text": "正確答案",
    "explanation_zh": "繁體中文解析，需說明語意與用法",
    "pattern_text": "核心句型或搭配",
    "zh_prompt": "中文提示",
    "sample_answer": "英文參考答案",
    "patterns_json": ["句型1", "句型2"]
  }}
]

欄位規則：
1. fill_blank:
   - prompt_text 必須有且包含 ____。
   - choices_json 至少 3 個字串。
   - words_json 必須為 []。
   - answer_text、explanation_zh、pattern_text 必填。
2. reorder:
   - prompt_text 必須有內容。
   - words_json 至少 3 個字串，順序需打亂。
   - choices_json 必須為 []。
   - answer_text、explanation_zh、pattern_text 必填。
3. translation:
   - zh_prompt、sample_answer、explanation_zh 必填。
   - patterns_json 至少 1 個字串。
   - choices_json、words_json 可為 []。
4. 題目不可重複，不可過於相似，內容需符合 {level} 難度。
5. 全部字串請避免前後多餘空白。
""".strip()


def parse_llm_json(raw_text: str) -> List[Dict[str, Any]]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```JSON").removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise QuestionGenerationError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise QuestionGenerationError("LLM response must be a JSON array.")
    return data


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
        if normalized["choices_json"]:
            raise QuestionGenerationError("reorder choices_json must be empty.")
        if len(normalized["words_json"]) < 3:
            raise QuestionGenerationError("reorder words_json must contain at least 3 words.")
        if not normalized["answer_text"] or not normalized["pattern_text"]:
            raise QuestionGenerationError("reorder requires answer_text and pattern_text.")
    elif mode == "translation":
        if not normalized["zh_prompt"] or not normalized["sample_answer"]:
            raise QuestionGenerationError("translation requires zh_prompt and sample_answer.")
        if len(normalized["patterns_json"]) < 1:
            raise QuestionGenerationError("translation patterns_json must contain at least 1 pattern.")
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
    llm: Any,
    topic: str,
    mode: str,
    level: str,
    requested_count: int,
) -> Tuple[List[Dict[str, Any]], int]:
    prompt = build_prompt(topic, mode, level, requested_count)
    response = llm.invoke(prompt)
    raw_text = response.content if hasattr(response, "content") else str(response)
    raw_items = parse_llm_json(raw_text)

    validated_items = []
    for index, item in enumerate(raw_items, start=1):
        validated_items.append(validate_item(item, topic, mode, level, DEFAULT_SORT_ORDER_BASE + index - 1))
    unique_items, skipped_duplicates = dedupe_items(validated_items)
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
    llm = get_chat_model(temperature=args.temperature, timeout=args.timeout)

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
                print(f"Generating combo topic={topic} mode={mode} level={level}")
                try:
                    items, skipped_duplicates = generate_combo_questions(llm, topic, mode, level, args.questions_per_combo)
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
                    print(f"Failed combo topic={topic} mode={mode} level={level}: {exc}")

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
        "Generation finished "
        f"combos={totals['combos']} "
        f"upserts={totals['upserts']} "
        f"deactivated={totals['deactivated']} "
        f"skipped_duplicates={totals['skipped_duplicates']} "
        f"failures={totals['failures']}"
    )
    print(f"Report written to {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())



# H:\AI\VENV3.12\Scripts\python.exe H:\AI\AI_TOOLS\webapps\englishchat\generate_toeic_coca_questions.py
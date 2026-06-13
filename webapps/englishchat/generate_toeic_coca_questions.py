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
EXAM_PROFILES = ["toeic_coca", "toefl_coca", "mixed"]

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
    parser = argparse.ArgumentParser(description="Generate EnglishChat question-bank rows with TOEIC/TOEFL profiles.")
    parser.add_argument("--questions-per-combo", type=int, default=DEFAULT_QUESTIONS_PER_COMBO)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--topics", nargs="*", choices=TOPICS)
    parser.add_argument("--modes", nargs="*", choices=MODES)
    parser.add_argument("--levels", nargs="*", choices=LEVELS)
    parser.add_argument("--exam-profile", choices=EXAM_PROFILES, default="mixed")
    return parser.parse_args()


def build_prompt(
    topic: str,
    mode: str,
    level: str,
    requested_count: int,
    exam_profile: str = "mixed",
    banned_signatures: Sequence[str] | None = None,
) -> str:
    exam_prompt_map = {
        "toeic_coca": "Generate TOEIC-style practical English (business + daily), guided by common COCA usage.",
        "toefl_coca": "Generate TOEFL-style English (academic + campus + lecture), guided by common COCA usage.",
        "mixed": "Generate a balanced mix of TOEIC and TOEFL styles, guided by common COCA usage.",
    }
    exam_instruction = exam_prompt_map.get(exam_profile, exam_prompt_map["mixed"])

    beginner_rule = ""
    if level == "beginner":
        beginner_rule = (
            "Beginner constraints: CEFR A1-A2 vocabulary and grammar; short, clear sentences; "
            "avoid advanced idioms and dense clauses."
        )

    banned_clause = ""
    if banned_signatures:
        banned_preview = "\n".join(f"- {sig}" for sig in list(banned_signatures)[:30])
        banned_clause = f"\nAvoid these existing signatures:\n{banned_preview}\n"

    return f"""
You are generating question-bank rows for English learning.
{exam_instruction}

topic={topic}
mode={mode}
level={level}
count={requested_count}
{beginner_rule}

Return ONLY a valid JSON array (no markdown, no code fence, no extra text).
Must return EXACTLY {requested_count} objects.

Each object must include these keys:
- prompt_text (string)
- choices_json (array of strings)
- words_json (array of strings)
- answer_text (string)
- explanation_zh (string)
- pattern_text (string)
- zh_prompt (string)
- sample_answer (string)
- patterns_json (array of strings)

Mode rules:
1) fill_blank
- prompt_text must contain exactly one "____"
- choices_json must contain >= 3 options
- words_json must be []
- answer_text and pattern_text must be non-empty

2) reorder
- prompt_text must be non-empty
- words_json must contain >= 3 chunks
- choices_json must be []
- answer_text and pattern_text must be non-empty

3) translation
- zh_prompt and sample_answer must be non-empty
- choices_json must be []
- words_json must be []
- patterns_json must contain >= 3 items when level=beginner, else >= 1
- explanation_zh must be non-empty

All items must be mutually different in content.
Do not use null.
Do not leave empty strings in required fields.
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
    hints = " / ".join([normalize_text(p) for p in patterns if normalize_text(p)][:2])
    if hints:
        return f"Use these grammar hints: {hints}."
    if sample_answer:
        return "Use the sample answer as the core sentence pattern."
    return "Provide a concise and grammatically correct translation."


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

    if mode == "reorder":
        normalized["choices_json"] = []
    if not normalized["pattern_text"] and mode in {"fill_blank", "reorder"}:
        normalized["pattern_text"] = normalized["prompt_text"] or f"{mode} pattern"
    if not normalized["explanation_zh"]:
        if normalized["answer_text"]:
            normalized["explanation_zh"] = f"Correct answer: {normalized['answer_text']}."
        elif normalized["sample_answer"]:
            normalized["explanation_zh"] = f"Sample answer: {normalized['sample_answer']}."
    if mode == "translation" and not normalized["explanation_zh"]:
        normalized["explanation_zh"] = build_translation_explanation_fallback(
            normalized["sample_answer"],
            normalized["patterns_json"],
        )

    if not normalized["explanation_zh"]:
        raise QuestionGenerationError("explanation_zh is required.")

    if mode == "fill_blank":
        if normalized["prompt_text"].count("____") != 1:
            raise QuestionGenerationError("fill_blank prompt_text must contain exactly one ____.")
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
            raise QuestionGenerationError("reorder words_json must contain at least 3 chunks.")
        if not normalized["answer_text"] or not normalized["pattern_text"]:
            raise QuestionGenerationError("reorder requires answer_text and pattern_text.")
    elif mode == "translation":
        if not normalized["zh_prompt"] or not normalized["sample_answer"]:
            raise QuestionGenerationError("translation requires zh_prompt and sample_answer.")
        required_pattern_count = 3 if level == "beginner" else 1
        if len(normalized["patterns_json"]) < required_pattern_count:
            raise QuestionGenerationError(
                f"translation patterns_json must contain at least {required_pattern_count} hints."
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
    exam_profile: str,
    temperature: float,
    timeout: int,
    banned_signatures: Sequence[str] | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    _ = banned_signatures  # kept for backward-compatible function signature
    collected: List[Dict[str, Any]] = []
    collected_sigs: set[str] = set()
    skipped_duplicates = 0

    rounds = max(2, requested_count + 1)
    for _round in range(rounds):
        need = requested_count - len(collected)
        if need <= 0:
            break
        prompt = build_prompt(
            topic=topic,
            mode=mode,
            level=level,
            requested_count=need,
            exam_profile=exam_profile,
            banned_signatures=None,
        )
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

        for index, item in enumerate(raw_items, start=1):
            try:
                normalized = validate_item(
                    item=item,
                    topic=topic,
                    mode=mode,
                    level=level,
                    sort_order=DEFAULT_SORT_ORDER_BASE + len(collected) + index - 1,
                )
            except QuestionGenerationError:
                skipped_duplicates += 1
                continue
            sig = question_signature(normalized)
            if sig in collected_sigs:
                skipped_duplicates += 1
                continue
            collected.append(normalized)
            collected_sigs.add(sig)
            if len(collected) >= requested_count:
                break

    unique_items, extra_skipped = dedupe_items(collected)
    skipped_duplicates += extra_skipped

    if len(unique_items) < requested_count:
        raise QuestionGenerationError(
            f"Expected {requested_count} unique questions but received {len(unique_items)} after retries; "
            f"skipped_duplicates={skipped_duplicates}."
        )
    return unique_items[:requested_count], skipped_duplicates


def write_report(report_dir: Path, summary: Dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    profile = str(summary.get("exam_profile") or "mixed")
    report_path = report_dir / f"{profile}_generation_{timestamp}.json"
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
                print(f"Generating combo topic={topic} mode={mode} level={level}")
                try:
                    existing_rows = repo.fetch_questions(topic_key=topic, mode=mode, level=level)
                    banned_signatures = [question_signature(row) for row in existing_rows]
                    items, skipped_duplicates = generate_combo_questions(
                        topic=topic,
                        mode=mode,
                        level=level,
                        requested_count=args.questions_per_combo,
                        exam_profile=args.exam_profile,
                        temperature=args.temperature,
                        timeout=args.timeout,
                        banned_signatures=banned_signatures,
                    )
                    combo.skipped_duplicates = skipped_duplicates

                    if not args.dry_run:
                        for item in items:
                            repo.upsert_question(item)
                            combo.inserted_or_updated += 1
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
                    print(f"Combo failed topic={topic} mode={mode} level={level}: {exc}")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "exam_profile": args.exam_profile,
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
        "Done "
        f"combos={totals['combos']} "
        f"upserts={totals['upserts']} "
        f"deactivated={totals['deactivated']} "
        f"skipped_duplicates={totals['skipped_duplicates']} "
        f"failures={totals['failures']}"
    )
    print(f"Report written: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


# ./venv/Scripts/python.exe ./webapps/englishchat/generate_toeic_coca_questions.py
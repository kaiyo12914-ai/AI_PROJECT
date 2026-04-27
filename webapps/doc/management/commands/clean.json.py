# webapps/doc/management/commands/clean_json.py
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from django.core.management.base import BaseCommand, CommandError


DEFAULT_IN = os.path.join("webapps", "doc", "data", "templates_seed.json")
DEFAULT_OUT = os.path.join("webapps", "doc", "data", "templates_seed_clean.json")


DOC_TYPE_ALLOWED = {"sign_memo", "order_draft", "submit_draft", "letter_draft", "note"}
SCOPE_ALLOWED = {"public", "personal"}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _as_str(x: Any) -> str:
    return "" if x is None else str(x)


def _clean_tags(tags: Any) -> List[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        return []
    out: List[str] = []
    seen = set()
    for t in tags:
        s = _as_str(t).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _normalize_doc_type(dt: str) -> str:
    dt = (dt or "").strip()
    return dt if dt in DOC_TYPE_ALLOWED else dt


def _normalize_scope(scope: str) -> str:
    sc = (scope or "public").strip().lower()
    return sc if sc in SCOPE_ALLOWED else "public"


def _parse_sections_from_text(text: str) -> Dict[str, str]:
    """
    以「主旨/說明/擬辦(或辦法)/附件」為基準抓段落。
    若抓不到就回傳 {raw: text}。
    """
    s = (text or "").strip()
    if not s:
        return {}

    # 找所有段落標籤位置
    labels = [
        ("subject", r"主旨[:：]"),
        ("reason", r"說明[:：]"),
        ("plan", r"(擬辦|辦法)[:：]"),
        ("attach", r"附件[:：]"),
    ]

    hits: List[Tuple[str, int]] = []
    for key, pat in labels:
        m = re.search(pat, s)
        if m:
            hits.append((key, m.start()))

    if not hits:
        return {"raw": s}

    hits.sort(key=lambda x: x[1])
    sections: Dict[str, str] = {}
    for i, (key, pos) in enumerate(hits):
        end = hits[i + 1][1] if i + 1 < len(hits) else len(s)
        chunk = s[pos:end].strip()

        # 去掉標籤本身
        chunk = re.sub(r"^(主旨|說明|擬辦|辦法|附件)[:：]\s*", "", chunk).strip()

        if chunk:
            sections[key] = chunk

    # 若解析太少，保底 raw
    if len(sections) == 0:
        sections["raw"] = s

    return sections


def _compose_content_text_from_sections(sections: Dict[str, Any]) -> str:
    """
    sections => content_text（固定順序）
    """
    if not sections:
        return ""

    if "raw" in sections and isinstance(sections.get("raw"), str):
        return (sections.get("raw") or "").strip()

    order = [("subject", "主旨"), ("reason", "說明"), ("plan", "擬辦"), ("attach", "附件")]
    parts: List[str] = []
    for key, label in order:
        v = sections.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(f"{label}：{v.strip()}")
    return "\n".join(parts).strip()


def _dedup_key(item: Dict[str, Any]) -> Tuple[str, str, str]:
    # title + doc_type + scope 先當 key（clean 階段不處理 owner）
    return (
        (item.get("title") or "").strip(),
        (item.get("doc_type") or "").strip(),
        (item.get("scope") or "public").strip().lower(),
    )


class Command(BaseCommand):
    help = "Clean/normalize seed templates JSON to schema v2 (templates_seed_clean.json)."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="in_path", default=DEFAULT_IN, help=f"Input JSON path (default: {DEFAULT_IN})")
        parser.add_argument("--out", dest="out_path", default=DEFAULT_OUT, help=f"Output JSON path (default: {DEFAULT_OUT})")
        parser.add_argument("--no-dedup", action="store_true", help="Do not deduplicate by (title, doc_type, scope)")
        parser.add_argument("--strict", action="store_true", help="Strict mode: invalid doc_type will raise error")

    def handle(self, *args, **opts):
        in_path: str = opts["in_path"]
        out_path: str = opts["out_path"]
        no_dedup: bool = bool(opts["no_dedup"])
        strict: bool = bool(opts["strict"])

        if not os.path.exists(in_path):
            raise CommandError(f"Input file not found: {in_path}")

        raw = _read_json(in_path)
        if not isinstance(raw, list):
            raise CommandError("Input JSON must be a list[object].")

        cleaned: List[Dict[str, Any]] = []
        seen = set()

        for idx, it in enumerate(raw, 1):
            if not isinstance(it, dict):
                self.stdout.write(self.style.WARNING(f"[skip] #{idx}: not an object"))
                continue

            title = _as_str(it.get("title")).strip()
            doc_type = _normalize_doc_type(_as_str(it.get("doc_type")).strip())
            description = _as_str(it.get("description")).strip()
            tags = _clean_tags(it.get("tags"))
            scope = _normalize_scope(_as_str(it.get("scope")).strip())

            if not title:
                self.stdout.write(self.style.WARNING(f"[skip] #{idx}: missing title"))
                continue

            if strict and doc_type not in DOC_TYPE_ALLOWED:
                raise CommandError(f"#{idx}: invalid doc_type={doc_type}")

            # 讀 content_text / content / sections
            sections_in = it.get("sections")
            if isinstance(sections_in, dict):
                sections = {}
                # 只保留我們認得的 key（或 raw）
                for k in ("subject", "reason", "plan", "attach", "raw"):
                    v = sections_in.get(k)
                    if isinstance(v, str) and v.strip():
                        sections[k] = v.strip()
                content_text = _compose_content_text_from_sections(sections)
            else:
                content_text = _as_str(it.get("content_text") or it.get("content")).strip()
                sections = _parse_sections_from_text(content_text)

            if not content_text:
                # 若 sections 可組出 content_text 就補
                content_text = _compose_content_text_from_sections(sections)

            if not content_text:
                self.stdout.write(self.style.WARNING(f"[skip] #{idx}: empty content"))
                continue

            # schema v2
            out_item: Dict[str, Any] = {
                "schema_ver": 2,
                "title": title,
                "doc_type": doc_type,
                "description": description,
                "tags": tags,
                "scope": scope,
                "content_text": content_text,
                "sections": sections,
                "doc_fields": it.get("doc_fields") if isinstance(it.get("doc_fields"), dict) else {},
                "meta": {
                    **(it.get("meta") if isinstance(it.get("meta"), dict) else {}),
                    "cleaned_at": _now_iso(),
                    "source_index": idx,
                    "source_file": os.path.basename(in_path),
                },
            }

            if not no_dedup:
                k = _dedup_key(out_item)
                if k in seen:
                    self.stdout.write(self.style.WARNING(f"[dedup] #{idx}: duplicated (title/doc_type/scope) -> {k}"))
                    continue
                seen.add(k)

            cleaned.append(out_item)

        _write_json(out_path, cleaned)
        self.stdout.write(self.style.SUCCESS(f"OK: cleaned={len(cleaned)} -> {out_path}"))

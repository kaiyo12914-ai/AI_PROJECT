# webapps/doc/management/commands/seed_doc_templates.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from webapps.doc.models import DocumentTemplate, DOC_TYPE_SECTION_RULES


DEFAULT_PATH = os.path.join("webapps", "doc", "data", "templates_seed_clean.json")


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_str(x: Any) -> str:
    return "" if x is None else str(x)


def _s(x: Any) -> str:
    return _as_str(x).strip()


def _clean_tags(tags: Any) -> List[str]:
    if tags is None or not isinstance(tags, list):
        return []
    out: List[str] = []
    seen = set()
    for t in tags:
        s = _as_str(t).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _safe_scope(scope: str) -> str:
    sc = (scope or "public").strip().lower()
    return sc if sc in ("public", "personal") else "public"


def _safe_mode(mode: str) -> str:
    m = (mode or "suffix").strip().lower()
    return m if m in ("suffix", "overwrite") else "suffix"


def _unique_lookup(scope: str, owner, title: str) -> Dict[str, Any]:
    """
    依你的 model unique constraint 設計：
    - public：以 (scope, title) 唯一
    - personal：以 (scope, owner, title) 唯一
    """
    if scope == "public":
        return {"scope": "public", "title": title}
    return {"scope": "personal", "owner": owner, "title": title}


def _legacy_sections_to_v2(doc_type: str, sec: Dict[str, Any]) -> Dict[str, Any]:
    """
    相容舊 seed 的 sections key：
      - reason -> explain
      - plan -> method
      - attach -> attachments
      - raw -> explain (fallback)
    同時保留已經是新 key 的值。
    """
    if not isinstance(sec, dict):
        return {}

    s2: Dict[str, Any] = dict(sec)

    if "explain" not in s2 and isinstance(s2.get("reason"), str):
        s2["explain"] = s2.get("reason", "")
    if "method" not in s2 and isinstance(s2.get("plan"), str):
        s2["method"] = s2.get("plan", "")
    if "attachments" not in s2 and isinstance(s2.get("attach"), str):
        s2["attachments"] = s2.get("attach", "")

    # raw 兜底：如果 explain 還是空，用 raw
    if (not _s(s2.get("explain"))) and isinstance(s2.get("raw"), str) and _s(s2.get("raw")):
        s2["explain"] = s2.get("raw", "")

    # note：points 若是字串，轉 list
    if doc_type == "note":
        pts = s2.get("points")
        if isinstance(pts, str) and _s(pts):
            s2["points"] = [ln.strip() for ln in pts.splitlines() if ln.strip()]

    return s2


def _build_sections_from_text(doc_type: str, title: str, text: str) -> Dict[str, Any]:
    """
    若 seed 沒給 sections，就用 content_text/legacy content 兜出一份最小可用 sections。
    這裡不做複雜解析，目標是「不會因 clean() 必填缺欄而失敗」。
    """
    dt = _s(doc_type) or "sign_memo"
    t = _s(title) or "未命名"
    c = _s(text)

    rules = DOC_TYPE_SECTION_RULES.get(dt, {})
    req = rules.get("required", [])

    if dt == "note":
        pts = [ln.strip() for ln in c.splitlines() if ln.strip()]
        if not pts and c:
            pts = [c]
        return {"title": t, "points": pts or ["(空)"]}

    out: Dict[str, Any] = {}

    # 最基本：subject 用 title，explain 用全文
    if "subject" in req or "subject" in rules.get("optional", []):
        out["subject"] = t
    if "explain" in req or "explain" in rules.get("optional", []):
        out["explain"] = c

    # method/enforce：若必填就補 "(略)"
    if dt == "order_draft":
        if ("enforce" in req) and not _s(out.get("enforce")):
            out["enforce"] = "(略)"
    else:
        if ("method" in req) and not _s(out.get("method")):
            out["method"] = "(略)"

    return out


def _build_content_text_from_sections(doc_type: str, sec: Dict[str, Any]) -> str:
    """
    用 sections 組出 content_text（新 key：subject/explain/method/attachments...）
    """
    if not isinstance(sec, dict):
        return ""

    dt = _s(doc_type)
    parts: List[str] = []

    if dt == "note":
        title = _s(sec.get("title"))
        pts = sec.get("points")
        if title:
            parts.append(f"主旨：{title}")
        if isinstance(pts, list):
            pts2 = [f"• {_s(p)}" for p in pts if _s(p)]
            if pts2:
                parts.append("重點：")
                parts.extend(pts2)
        action = _s(sec.get("action"))
        if action:
            parts.append(f"擬辦：{action}")
        return "\n".join([p for p in parts if _s(p)]).strip()

    subject = _s(sec.get("subject"))
    explain = _s(sec.get("explain"))
    method = _s(sec.get("method"))
    enforce = _s(sec.get("enforce"))
    attachments = _s(sec.get("attachments"))
    closing = _s(sec.get("closing"))

    if subject:
        parts.append(f"主旨：{subject}")
    if explain:
        parts.append("說明：")
        parts.append(explain)

    if dt == "order_draft":
        if enforce:
            parts.append("施行：")
            parts.append(enforce)
    else:
        if method:
            parts.append("擬辦：")
            parts.append(method)

    if attachments:
        parts.append("附件：")
        parts.append(attachments)

    if closing and dt == "letter_draft":
        parts.append(closing)

    return "\n".join([p for p in parts if _s(p)]).strip()


def _save_with_policy(
    *,
    title: str,
    doc_type: str,
    description: str,
    content_text: str,
    sections: Dict[str, Any],
    doc_fields: Dict[str, Any],
    tags: List[str],
    scope: str,
    owner,
    mode: str,
    schema_ver: int = 2,
    meta: Dict[str, Any] | None = None,
    max_suffix_try: int = 50,
    force_clear_struct: bool = False,
) -> Tuple[DocumentTemplate, bool, str]:
    """
    回傳：obj, created, final_title
    - created=True 代表 create
    - created=False 代表 update_or_create 時是 update
    """
    mode = _safe_mode(mode)
    meta = meta or {}

    # ✅ 可選：強制只存 content_text，不存 sections（避免 save() 重組/預覽重複）
    if force_clear_struct:
        sections = {}
        doc_fields = {}
        meta = {}

    base_defaults = {
        "doc_type": doc_type,
        "description": description,
        "content_text": content_text,
        "tags": tags,
        "scope": scope,
        "owner": (owner if scope == "personal" else None),
        "sections": sections,
        "doc_fields": doc_fields,
        "meta": meta,
        "schema_ver": int(schema_ver or 2),
    }

    if mode == "overwrite":
        lookup = _unique_lookup(scope, owner, title)
        obj, created = DocumentTemplate.objects.update_or_create(defaults=base_defaults, **lookup)
        return obj, created, obj.title

    # suffix 模式：若撞 title 就自動加（2）（3）…
    base = title
    for n in range(1, max_suffix_try + 1):
        try_title = base if n == 1 else f"{base}（{n}）"
        try:
            with transaction.atomic():
                obj = DocumentTemplate.objects.create(title=try_title, **base_defaults)
            return obj, True, obj.title
        except IntegrityError:
            continue

    raise ValueError(f"title conflict too many duplicates: {base}")


class Command(BaseCommand):
    help = "Seed DocumentTemplate from JSON (schema v2 + legacy compatibility)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=DEFAULT_PATH, help=f"Seed JSON path (default: {DEFAULT_PATH})")
        parser.add_argument("--mode", default="suffix", choices=["suffix", "overwrite"], help="Conflict mode")
        parser.add_argument("--scope", default="all", choices=["all", "public", "personal"], help="Only import specific scope")
        parser.add_argument("--owner", default="", help="Username for personal templates (if scope=personal)")
        parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
        parser.add_argument("--max-suffix-try", type=int, default=50, help="Suffix try count when mode=suffix")

        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing DocumentTemplate before import (respect --scope filter).",
        )

        # ✅ 重點：若你想「預覽只顯示 content_text 原文」，就開這個
        parser.add_argument(
            "--force-clear-struct",
            action="store_true",
            help="Force clear sections/doc_fields/meta when saving. Store only content_text/tags/etc.",
        )

    def handle(self, *args, **opts):
        path: str = opts["path"]
        mode: str = opts["mode"]
        scope_filter: str = opts["scope"]
        owner_username: str = (opts["owner"] or "").strip()
        dry_run: bool = bool(opts["dry_run"])
        max_suffix_try: int = int(opts["max_suffix_try"])
        reset: bool = bool(opts["reset"])
        force_clear_struct: bool = bool(opts["force_clear_struct"])

        if not os.path.exists(path):
            raise CommandError(f"Seed file not found: {path}")

        data = _read_json(path)
        if not isinstance(data, list):
            raise CommandError("Seed JSON must be list[object].")

        # owner（personal 時才需要）
        owner = None
        if owner_username:
            User = get_user_model()
            owner = User.objects.filter(username=owner_username).first()
            if not owner:
                raise CommandError(f"Owner user not found: {owner_username}")

        def want_scope(sc: str) -> bool:
            if scope_filter == "all":
                return True
            return sc == scope_filter

        # =========================
        # reset：清除舊資料
        # =========================
        if reset:
            if dry_run:
                self.stdout.write("[dry-run] reset requested: will NOT delete anything.")
            else:
                qs = DocumentTemplate.objects.all()
                if scope_filter in ("public", "personal"):
                    qs = qs.filter(scope=scope_filter)
                if scope_filter == "personal" and owner:
                    qs = qs.filter(owner=owner)

                deleted_count = qs.count()
                qs.delete()
                self.stdout.write(self.style.WARNING(f"[reset] deleted DocumentTemplate rows: {deleted_count}"))

        imported = 0
        updated = 0
        skipped = 0
        downgraded = 0
        errors = 0

        for i, it in enumerate(data, 1):
            try:
                if not isinstance(it, dict):
                    skipped += 1
                    continue

                # schema_ver（缺省視為 2）
                schema_ver_raw = it.get("schema_ver", 2)
                try:
                    schema_ver = int(schema_ver_raw)
                except Exception:
                    schema_ver = 2

                if schema_ver != 2:
                    self.stdout.write(self.style.WARNING(f"[skip] #{i}: schema_ver={schema_ver} != 2"))
                    skipped += 1
                    continue

                title = _s(it.get("title"))
                doc_type = _s(it.get("doc_type"))
                description = _s(it.get("description"))
                tags = _clean_tags(it.get("tags"))
                scope = _safe_scope(_s(it.get("scope")))  # JSON 沒有 scope → public

                # ✅ 兼容：content_text / content
                content_text = _s(it.get("content_text"))
                legacy_content = _s(it.get("content"))
                if not content_text and legacy_content:
                    content_text = legacy_content

                # ✅ sections/doc_fields/meta（缺省給 dict）
                sections_in = it.get("sections")
                sections: Dict[str, Any] = _legacy_sections_to_v2(doc_type, sections_in if isinstance(sections_in, dict) else {})
                doc_fields = it.get("doc_fields") if isinstance(it.get("doc_fields"), dict) else {}
                meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}

                # 若沒 sections，就用文字兜
                if not sections:
                    sections = _build_sections_from_text(doc_type, title, content_text)

                # 若沒 content_text，則用 sections 組一份
                if not content_text:
                    content_text = _build_content_text_from_sections(doc_type, sections)

                # 基本欄位檢核
                if not title or not doc_type:
                    self.stdout.write(self.style.WARNING(f"[skip] #{i}: missing title/doc_type"))
                    skipped += 1
                    continue

                if not content_text:
                    self.stdout.write(self.style.WARNING(f"[skip] #{i}: empty content_text: {title}"))
                    skipped += 1
                    continue

                # scope filter
                if not want_scope(scope):
                    skipped += 1
                    continue

                # personal 但沒 owner → downgrade public
                if scope == "personal" and owner is None:
                    scope = "public"
                    downgraded += 1

                # dry-run
                if dry_run:
                    imported += 1
                    continue

                obj, created, _final_title = _save_with_policy(
                    title=title,
                    doc_type=doc_type,
                    description=description,
                    content_text=content_text,
                    sections=sections,
                    doc_fields=doc_fields,
                    tags=tags,
                    scope=scope,
                    owner=owner,
                    mode=mode,
                    schema_ver=schema_ver,
                    meta=meta,
                    max_suffix_try=max_suffix_try,
                    force_clear_struct=force_clear_struct,
                )
                imported += 1
                if not created:
                    updated += 1

            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"[error] #{i}: {e}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Seed Result ==="))
        self.stdout.write(f"file: {path}")
        self.stdout.write(f"mode: {mode}, scope_filter: {scope_filter}, owner: {owner_username or '-'}")
        self.stdout.write(f"imported: {imported}")
        self.stdout.write(f"updated(overwrite only): {updated}")
        self.stdout.write(f"skipped: {skipped}")
        self.stdout.write(f"downgraded(personal->public): {downgraded}")
        self.stdout.write(f"errors: {errors}")

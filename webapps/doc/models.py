from __future__ import annotations

from typing import Any, Dict, List

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

# ============================================================
# New schema rules (system format)
# ============================================================

DOC_TYPE_CHOICES = [
    ("sign_memo", "簽呈"),
    ("order_draft", "令稿"),
    ("submit_draft", "呈稿"),
    ("letter_draft", "函稿"),
    ("note", "便籤"),
]

SCOPE_CHOICES = [
    ("public", "公開"),
    ("personal", "個人"),
]

DOC_TYPE_SECTION_RULES: Dict[str, Dict[str, List[str]]] = {
    "sign_memo": {
        "required": ["subject", "explain", "method"],
        "optional": ["attachments", "closing", "recipients"],
    },
    "submit_draft": {
        "required": ["subject", "explain"],
        "optional": ["method", "attachments", "closing", "recipients"],
    },
    "order_draft": {
        "required": ["subject", "explain"],
        "optional": ["enforce", "attachments", "recipients", "closing"],
    },
    "letter_draft": {
        "required": ["subject", "explain"],
        "optional": ["method", "attachments", "closing", "recipients"],
    },
    "note": {
        "required": ["title", "points"],
        "optional": ["action", "owner", "due", "ref"],
    },
}

LETTER_DOC_FIELDS_DEFAULT: Dict[str, Any] = {
    "recipient_name": "",
    "recipient_zip": "",
    "recipient_address": "",
    "publish_date": "",
    "show_publish_date": False,
}


def _s(v: Any) -> str:
    return ("" if v is None else str(v)).strip()


def _list_str(v: Any) -> List[str]:
    if isinstance(v, list):
        out: List[str] = []
        seen = set()
        for x in v:
            s = _s(x)
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out
    return []


def _dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


class DocumentTemplate(models.Model):
    """
    新制模板：
    - sections: 結構化段落
    - doc_fields: 函稿常用欄位
    - content_text: 預覽/全文檢索/匯出用（可由 sections 合成，但不強制覆寫）
    """

    # ✅ 讓外部（views / seed / 管理指令）可穩定引用
    DOC_TYPE_CHOICES = DOC_TYPE_CHOICES
    SCOPE_CHOICES = SCOPE_CHOICES
    DOC_TYPE_SECTION_RULES = DOC_TYPE_SECTION_RULES
    LETTER_DOC_FIELDS_DEFAULT = LETTER_DOC_FIELDS_DEFAULT

    title = models.CharField(max_length=200, db_index=True)
    doc_type = models.CharField(max_length=40, choices=DOC_TYPE_CHOICES, db_index=True)
    description = models.CharField(max_length=400, blank=True, default="")

    sections = models.JSONField(default=dict, blank=True)
    doc_fields = models.JSONField(default=dict, blank=True)

    schema_ver = models.PositiveSmallIntegerField(default=2, db_index=True)
    meta = models.JSONField(default=dict, blank=True)

    # ✅ 可直接存「全文型範例」；若 sections 有內容才會重建
    content_text = models.TextField(blank=True, default="")

    tags = models.JSONField(default=list, blank=True)

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default="public",
        db_index=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="doc_templates",
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["doc_type", "scope", "created_at"], name="idx_doc_type_scope_created"),
            models.Index(fields=["schema_ver", "doc_type"], name="idx_doc_schema_doctype"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["title"],
                condition=Q(scope="public"),
                name="uniq_doc_template_public_title",
            ),
            models.UniqueConstraint(
                fields=["owner", "title"],
                condition=Q(scope="personal") & Q(owner__isnull=False),
                name="uniq_doc_template_personal_owner_title",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_doc_type_display()} | {self.title}"

    # ------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------
    def clean(self) -> None:
        super().clean()

        # 1) doc_type 必須合法
        dt = _s(self.doc_type)
        valid_types = {k for k, _ in DOC_TYPE_CHOICES}
        if dt not in valid_types:
            raise ValidationError({"doc_type": f"Invalid doc_type: {dt}"})

        # 2) scope / owner 一致性（避免髒資料）
        sc = _s(self.scope) or "public"
        if sc not in {k for k, _ in SCOPE_CHOICES}:
            raise ValidationError({"scope": f"Invalid scope: {sc}"})

        if sc == "public":
            # 公開模板不應綁 owner（避免誤判權限）
            if self.owner_id is not None:
                self.owner = None
        elif sc == "personal":
            # 個人模板必須有 owner
            if self.owner_id is None:
                raise ValidationError({"owner": "personal scope requires owner"})

        # 3) JSON 欄位型別正規化
        self.tags = _list_str(self.tags)
        self.sections = _dict(self.sections)
        self.doc_fields = _dict(self.doc_fields)
        self.meta = _dict(self.meta)

        # 4) sections 規則檢查（若 rules 不存在就跳過）
        rules = DOC_TYPE_SECTION_RULES.get(dt)
        if not rules:
            return

        # note 規則
        if dt == "note":
            title = _s(self.sections.get("title"))
            if not title:
                raise ValidationError({"sections": "note.sections.title is required"})

            pts = self.sections.get("points")
            if not isinstance(pts, list):
                raise ValidationError({"sections": "note.sections.points must be a list"})

            pts_clean = [_s(p) for p in pts if _s(p)]
            if not pts_clean:
                raise ValidationError({"sections": "note.sections.points must be a non-empty list"})

            # ✅ 讓資料更乾淨：把 points 清成乾淨 list（可選，但很實用）
            self.sections["points"] = pts_clean

            # note 不強制 content_text/sections 之外的欄位
            return

        # 一般公文規則（required 欄位都要非空）
        req = set(rules.get("required", []))
        missing = []
        for k in req:
            v = self.sections.get(k)
            if not _s(v):
                missing.append(k)
        if missing:
            raise ValidationError({"sections": f"Missing required sections: {', '.join(missing)}"})

        # 函稿預設欄位補齊（只在 letter_draft）
        if dt == "letter_draft":
            if not self.doc_fields:
                self.doc_fields = {}
            for k, dv in LETTER_DOC_FIELDS_DEFAULT.items():
                self.doc_fields.setdefault(k, dv)

    # ------------------------------------------------------------
    # Build content_text from sections
    # ------------------------------------------------------------
    def build_content_text(self) -> str:
        dt = _s(self.doc_type)
        s = _dict(self.sections)

        if dt == "note":
            title = _s(s.get("title"))
            pts = s.get("points") if isinstance(s.get("points"), list) else []
            pts2 = [f"• {_s(p)}" for p in pts if _s(p)]
            action = _s(s.get("action"))

            lines: List[str] = []
            if title:
                lines.append(f"主旨：{title}")
            if pts2:
                lines.append("重點：")
                lines.extend(pts2)
            if action:
                lines.append(f"擬辦：{action}")
            return "\n".join(lines).strip()

        subject = _s(s.get("subject"))
        explain = _s(s.get("explain"))
        method = _s(s.get("method"))
        attachments = _s(s.get("attachments"))
        closing = _s(s.get("closing"))
        enforce = _s(s.get("enforce"))

        lines: List[str] = []
        if subject:
            lines.append(f"主旨：{subject}")

        if explain:
            lines.append("說明：")
            lines.append(explain)

        if dt == "order_draft":
            if enforce:
                lines.append("施行：")
                lines.append(enforce)
        else:
            if method:
                lines.append("擬辦：")
                lines.append(method)

        if attachments:
            lines.append("附件：")
            lines.append(attachments)

        # 函稿 closing 才直接附在最後
        if closing and dt == "letter_draft":
            lines.append(closing)

        return "\n".join([x for x in lines if _s(x)]).strip()

    # ------------------------------------------------------------
    # Save override
    # ------------------------------------------------------------
    def save(self, *args, **kwargs) -> None:
        """
        ✅ 必修：不要無條件覆寫 content_text
        - 若是「全文型範例」(只填 content_text)，sections 可能是 {}
          -> 必須保留 content_text 原文，不要重組
        - 若 sections 有內容（結構化模板），才用 build_content_text 重建預覽全文
        """
        try:
            if isinstance(self.sections, dict) and self.sections:
                self.content_text = self.build_content_text()
        except Exception:
            # 任何 build 失敗都不要影響存檔
            pass

        super().save(*args, **kwargs)

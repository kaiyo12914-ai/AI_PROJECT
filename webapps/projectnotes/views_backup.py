from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse
from functools import wraps

import requests
from bs4 import BeautifulSoup
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node

from .models import (
    ProjectNoteAuditLog,
    ProjectNoteChunk,
    ProjectNoteConversation,
    ProjectNoteDigest,
    ProjectNoteProject,
    ProjectNoteSource,
    ProjectNoteTurn,
)


try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover
    DocxDocument = None


TOKEN_RE = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}")
MAX_UPLOAD_MB = 10
ALLOWED_UPLOAD_EXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css", ".pdf", ".docx"}


@require_node("projectnotes")
def index(request: HttpRequest):
    return render(request, "projectnotes/index.html")


def _json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return default


def _safe_text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _read_json_body(request: HttpRequest) -> Dict[str, Any]:
    try:
        return json.loads((request.body or b"").decode("utf-8"))
    except Exception:
        return {}


def _normalize_tokens(text: str) -> List[str]:
    return [x.lower() for x in TOKEN_RE.findall(_safe_text(text))]


def _safe_json_response(data: Dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _api_error(
    message: str,
    *,
    error_code: str = "bad_request",
    status: int = 400,
    detail: Any = None,
) -> JsonResponse:
    payload: Dict[str, Any] = {
        "ok": False,
        "error": _safe_text(message) or "request failed",
        "error_code": _safe_text(error_code) or "bad_request",
    }
    if detail is not None:
        payload["detail"] = detail
    return _safe_json_response(payload, status=status)


def api_guard(view_func):
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any):
        try:
            return view_func(request, *args, **kwargs)
        except Exception as e:
            return _api_error(
                "internal server error",
                error_code="internal_error",
                status=500,
                detail={"type": type(e).__name__},
            )

    return _wrapped


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _current_user_id(request: HttpRequest) -> str:
    uid = _safe_text(getattr(request, "login_user", ""))
    if uid:
        return uid
    user = getattr(request, "user", None)
    return _safe_text(getattr(user, "username", ""))


def _parse_allowed_users(raw: str) -> set[str]:
    arr = _json_loads(raw or "[]", [])
    if not isinstance(arr, list):
        return set()
    out = set()
    for x in arr:
        v = _safe_text(x)
        if v:
            out.add(v)
    return out


def _can_access_project(request: HttpRequest, project: Optional[ProjectNoteProject]) -> bool:
    if not project:
        return False
    mode = _safe_text(project.permission_mode).lower() or "auth"
    uid = _current_user_id(request)
    if mode == "auth":
        return bool(uid)
    if mode == "restricted":
        allow = _parse_allowed_users(project.allowed_users_json)
        if not allow:
            return False
        return uid in allow
    return bool(uid)


def _can_access_source(request: HttpRequest, source: Optional[ProjectNoteSource]) -> bool:
    if not source:
        return False
    mode = _safe_text(source.permission_mode).lower() or "inherit"
    if mode == "inherit":
        return _can_access_project(request, source.project)
    if mode == "restricted":
        uid = _current_user_id(request)
        allow = _parse_allowed_users(source.allowed_users_json)
        if not allow:
            return False
        return uid in allow
    return _can_access_project(request, source.project)


def _write_audit(
    request: HttpRequest,
    *,
    action: str,
    status: str = "ok",
    project: Optional[ProjectNoteProject] = None,
    conversation: Optional[ProjectNoteConversation] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        ProjectNoteAuditLog.objects.create(
            project=project,
            conversation=conversation,
            action=_safe_text(action)[:40],
            status=_safe_text(status)[:20] or "ok",
            user_id=_current_user_id(request)[:80],
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
    except Exception:
        pass


def _upsert_digest(
    *,
    project: ProjectNoteProject,
    digest_type: str,
    content_text: str,
    payload: Dict[str, Any],
    source_ids: List[int],
    updated_by: str,
) -> None:
    obj, _created = ProjectNoteDigest.objects.get_or_create(
        project=project,
        digest_type=digest_type,
        defaults={
            "content_text": content_text,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "source_snapshot_ids_json": json.dumps(source_ids, ensure_ascii=False),
            "updated_by": updated_by,
        },
    )
    obj.content_text = content_text
    obj.payload_json = json.dumps(payload, ensure_ascii=False)
    obj.source_snapshot_ids_json = json.dumps(source_ids, ensure_ascii=False)
    obj.updated_by = updated_by
    obj.save(update_fields=["content_text", "payload_json", "source_snapshot_ids_json", "updated_by", "updated_at"])


def _generate_project_digests(project: ProjectNoteProject, updated_by: str = "") -> Dict[str, Any]:
    sources = list(ProjectNoteSource.objects.filter(project=project, is_enabled=True).order_by("-id")[:30])
    source_ids = [s.id for s in sources]
    if not sources:
        _upsert_digest(
            project=project,
            digest_type="summary",
            content_text="此專案目前尚未有可用來源。",
            payload={"summary": "此專案目前尚未有可用來源。"},
            source_ids=[],
            updated_by=updated_by,
        )
        _upsert_digest(
            project=project,
            digest_type="faq",
            content_text="[]",
            payload={"faq": []},
            source_ids=[],
            updated_by=updated_by,
        )
        _upsert_digest(
            project=project,
            digest_type="decisions",
            content_text="[]",
            payload={"decisions": []},
            source_ids=[],
            updated_by=updated_by,
        )
        return {"summary": "此專案目前尚未有可用來源。", "faq": [], "decisions": []}

    chunks = list(
        ProjectNoteChunk.objects.filter(source_id__in=source_ids).order_by("source_id", "chunk_index")[:40]
    )
    context = "\n\n".join([_safe_text(c.content)[:260] for c in chunks if _safe_text(c.content)])
    titles = [s.title for s in sources]
    fallback_summary = f"專案「{project.name}」目前有 {len(sources)} 份來源，重點包含：" + "、".join(titles[:6])
    fallback_faq = ["此專案目前主要目標是什麼？", "目前關鍵限制與風險為何？", "下一步執行建議是什麼？"]
    fallback_decisions = ["尚未產生可辨識的決策摘要。"]

    summary = fallback_summary
    faq = fallback_faq
    decisions = fallback_decisions

    if context:
        prompt = f"""
你是專案知識整理助理。請依據來源內容輸出 JSON，禁止捏造。
專案：{project.name}
來源標題：{", ".join(titles[:12])}
內容片段：
{context}

輸出：
{{
  "summary": "80-160字摘要",
  "faq": ["3個問題"],
  "decisions": ["3個近期決策或方向"]
}}
""".strip()
        try:
            llm = get_chat_model(temperature=0.2, timeout=90)
            out = llm.invoke(prompt)
            raw = out.content if hasattr(out, "content") else str(out)
            data = _extract_json_from_llm(raw)
            summary = _safe_text(data.get("summary")) or fallback_summary
            faq_raw = data.get("faq") if isinstance(data.get("faq"), list) else []
            decisions_raw = data.get("decisions") if isinstance(data.get("decisions"), list) else []
            faq = [_safe_text(x) for x in faq_raw if _safe_text(x)][:3] or fallback_faq
            decisions = [_safe_text(x) for x in decisions_raw if _safe_text(x)][:3] or fallback_decisions
        except Exception:
            pass

    _upsert_digest(
        project=project,
        digest_type="summary",
        content_text=summary,
        payload={"summary": summary},
        source_ids=source_ids,
        updated_by=updated_by,
    )
    _upsert_digest(
        project=project,
        digest_type="faq",
        content_text="\n".join(faq),
        payload={"faq": faq},
        source_ids=source_ids,
        updated_by=updated_by,
    )
    _upsert_digest(
        project=project,
        digest_type="decisions",
        content_text="\n".join(decisions),
        payload={"decisions": decisions},
        source_ids=source_ids,
        updated_by=updated_by,
    )
    return {"summary": summary, "faq": faq, "decisions": decisions}


def _parse_upload_file_to_text(uploaded_file) -> Tuple[str, str]:
    name = _safe_text(getattr(uploaded_file, "name", ""))
    lower_name = name.lower()
    ext = ""
    if "." in lower_name:
        ext = lower_name[lower_name.rfind(".") :]
    if ext not in ALLOWED_UPLOAD_EXT:
        raise RuntimeError("unsupported file type")
    raw_bytes = uploaded_file.read() or b""

    if lower_name.endswith((".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".css")):
        try:
            return raw_bytes.decode("utf-8"), "text"
        except Exception:
            return raw_bytes.decode("cp950", errors="ignore"), "text"

    if lower_name.endswith(".pdf"):
        if PdfReader is None:
            raise RuntimeError("pypdf not installed")
        reader = PdfReader(BytesIO(raw_bytes))
        pages: List[str] = []
        for i, p in enumerate(reader.pages):
            txt = _safe_text(p.extract_text())
            if txt:
                pages.append(f"[Page {i + 1}]\n{txt}")
        return "\n\n".join(pages), "pdf"

    if lower_name.endswith(".docx"):
        if DocxDocument is None:
            raise RuntimeError("python-docx not installed")
        doc = DocxDocument(BytesIO(raw_bytes))
        lines = [_safe_text(p.text) for p in doc.paragraphs if _safe_text(p.text)]
        return "\n".join(lines), "docx"

    raise RuntimeError("unsupported file type")


def _looks_like_heading(line: str) -> bool:
    s = _safe_text(line)
    if not s:
        return False
    if s.startswith("#"):
        return True
    if len(s) <= 28 and (s.endswith(":") or s.endswith("：")):
        return True
    if re.match(r"^(第[\d一二三四五六七八九十]+[章節部]|[0-9]+(\.[0-9]+)*\s)", s):
        return True
    if len(s) <= 22 and not re.search(r"[。！？.!?]", s):
        return True
    return False


def _split_long_text_preserve_sentence(text: str, max_chars: int, overlap: int) -> List[str]:
    s = _safe_text(text)
    if len(s) <= max_chars:
        return [s] if s else []

    segs: List[str] = []
    rest = s
    while len(rest) > max_chars:
        cut = max_chars
        window = rest[:max_chars]
        candidates: List[int] = []
        for mark in ("。", "！", "？", ".", "!", "?", "\n"):
            pos = window.rfind(mark)
            if pos >= int(max_chars * 0.55):
                candidates.append(pos + 1)
        if candidates:
            cut = max(candidates)
        seg = rest[:cut].strip()
        if seg:
            segs.append(seg)
        rest = rest[max(0, cut - overlap) :].strip()
        if not rest:
            break
    if rest:
        segs.append(rest)
    return segs


def _build_chunks(text: str, max_chars: int = 750, overlap: int = 120) -> List[Tuple[str, str]]:
    text = _safe_text(text)
    if not text:
        return []

    parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: List[Tuple[str, str]] = []
    cur = ""
    cur_section = ""
    active_section = ""

    for part in parts:
        first_line = _safe_text(part.splitlines()[0] if part.splitlines() else part)
        if _looks_like_heading(first_line):
            if cur:
                chunks.append((cur, cur_section))
                cur = ""
                cur_section = ""
            active_section = first_line.lstrip("#").strip("：: ").strip()
            continue

        for seg in _split_long_text_preserve_sentence(part, max_chars=max_chars, overlap=overlap):
            if not cur:
                cur = seg
                cur_section = active_section
                continue
            if len(cur) + 2 + len(seg) <= max_chars and cur_section == active_section:
                cur += "\n\n" + seg
            else:
                chunks.append((cur, cur_section))
                tail = cur[-overlap:] if overlap > 0 else ""
                cur = (tail + "\n" + seg).strip() if tail else seg
                cur_section = active_section
    if cur:
        chunks.append((cur, cur_section))
    return chunks


def _create_source_from_text(
    *,
    project_id: int,
    title: str,
    raw_text: str,
    source_type: str,
    original_filename: str = "",
) -> Tuple[ProjectNoteSource, int]:
    chunks = _build_chunks(raw_text)
    if not chunks:
        raise RuntimeError("no text extracted from source")

    latest = (
        ProjectNoteSource.objects.filter(project_id=project_id, title=title)
        .order_by("-snapshot_no")
        .first()
    )
    next_snapshot_no = 1 if not latest else (latest.snapshot_no + 1)
    source_version = f"v{next_snapshot_no}"

    with transaction.atomic():
        source = ProjectNoteSource.objects.create(
            project_id=project_id,
            title=title,
            source_type=source_type,
            original_filename=original_filename,
            snapshot_no=next_snapshot_no,
            source_version=source_version,
            raw_text=raw_text[:2_000_000],
        )
        ProjectNoteChunk.objects.bulk_create(
            [
                ProjectNoteChunk(
                    source=source,
                    chunk_index=i,
                    section_path=(section or "")[:300],
                    token_count=len(_normalize_tokens(c)),
                    content=c,
                )
                for i, (c, section) in enumerate(chunks)
            ]
        )
    return source, len(chunks)


def _resolve_source_ids_for_scope(
    project_id: int,
    selected_source_ids: List[int],
    version_mode: str,
) -> List[int]:
    """
    version_mode:
      - latest_only: only latest snapshot per title
      - all_versions: all enabled snapshots
      - selected_only: only selected_source_ids
    """
    mode = _safe_text(version_mode).lower() or "latest_only"
    base = ProjectNoteSource.objects.filter(project_id=project_id, is_enabled=True)
    if mode == "selected_only":
        if not selected_source_ids:
            return []
        return list(base.filter(id__in=selected_source_ids).values_list("id", flat=True))

    if mode == "all_versions":
        if selected_source_ids:
            return list(base.filter(id__in=selected_source_ids).values_list("id", flat=True))
        return list(base.values_list("id", flat=True))

    # latest_only
    if selected_source_ids:
        title_qs = base.filter(id__in=selected_source_ids).values_list("title", flat=True)
        titles = list({t for t in title_qs if _safe_text(t)})
        base = base.filter(title__in=titles) if titles else base.none()
    latest_ids: List[int] = []
    for title in base.values_list("title", flat=True).distinct():
        s = base.filter(title=title).order_by("-snapshot_no", "-id").first()
        if s:
            latest_ids.append(s.id)
    return latest_ids


def _is_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def _normalize_search_url(raw_url: str) -> str:
    """
    Normalize search-engine redirect links to real target URL.
    Handles DuckDuckGo links like:
      //duckduckgo.com/l/?uddg=<encoded_target>
      https://duckduckgo.com/l/?uddg=<encoded_target>
    """
    u = _safe_text(raw_url)
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u

    try:
        p = urlparse(u)
    except Exception:
        return u

    if "duckduckgo.com" in (p.netloc or "") and p.path.startswith("/l/"):
        q = parse_qs(p.query or "")
        uddg = _safe_text((q.get("uddg") or [""])[0])
        if uddg:
            return unquote(uddg)
    return u


def _fetch_web_text(source_url: str) -> Tuple[str, str]:
    timeout = 12
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    target_url = _normalize_search_url(source_url)
    resp = requests.get(target_url, timeout=timeout, headers=headers, allow_redirects=True)
    resp.raise_for_status()
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type and "<html" not in resp.text[:400].lower():
        text = _safe_text(resp.text)
        title = target_url
        return text, title

    soup = BeautifulSoup(resp.text, "lxml")
    for node in soup(["script", "style", "noscript", "iframe", "svg"]):
        node.decompose()

    title = _safe_text(soup.title.text if soup.title else "") or target_url
    body = soup.body or soup
    lines: List[str] = []
    for el in body.find_all(["h1", "h2", "h3", "p", "li"]):
        txt = _safe_text(el.get_text(" ", strip=True))
        if not txt:
            continue
        if len(txt) < 8:
            continue
        lines.append(txt)
    if not lines:
        fallback = _safe_text(body.get_text("\n", strip=True))
        if fallback:
            lines = [x for x in fallback.splitlines() if _safe_text(x)]

    text = "\n".join(lines)
    return text, title


def _extract_json_from_llm(raw: str) -> Dict[str, Any]:
    s = _safe_text(raw)
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


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_projects(request: HttpRequest):
    if request.method == "GET":
        all_rows = list(ProjectNoteProject.objects.all().order_by("-updated_at", "-id")[:200])
        rows = [p for p in all_rows if _can_access_project(request, p)][:100]
        data = []
        for p in rows:
            data.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "strict_source_only": p.strict_source_only,
                    "permission_mode": p.permission_mode,
                    "source_count": p.sources.count(),
                    "updated_at": p.updated_at.isoformat(),
                }
            )
        return _safe_json_response({"ok": True, "projects": data})

    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    body = _read_json_body(request)
    name = _safe_text(body.get("name"))
    if not name:
        return _api_error("name is required", error_code="missing_name", status=400)
    description = _safe_text(body.get("description"))
    strict_source_only = bool(body.get("strict_source_only", True))
    permission_mode = _safe_text(body.get("permission_mode")).lower() or "auth"
    if permission_mode not in ("auth", "restricted"):
        permission_mode = "auth"
    allowed_users = body.get("allowed_users") if isinstance(body.get("allowed_users"), list) else []
    allowed_users = [_safe_text(x) for x in allowed_users if _safe_text(x)]
    created_by = _safe_text(getattr(request, "login_user", "")) or _safe_text(getattr(request.user, "username", ""))

    p = ProjectNoteProject.objects.create(
        name=name,
        description=description,
        strict_source_only=strict_source_only,
        permission_mode=permission_mode,
        allowed_users_json=json.dumps(allowed_users, ensure_ascii=False),
        created_by=created_by,
    )
    _write_audit(request, action="project_create", status="ok", project=p, detail={"name": p.name, "permission_mode": permission_mode})
    return _safe_json_response({"ok": True, "project": {"id": p.id, "name": p.name}})


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_digests(request: HttpRequest):
    if request.method not in ("GET", "POST"):
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    if request.method == "GET":
        project_id = _to_int(request.GET.get("project_id"), 0)
        if project_id <= 0:
            return _api_error("project_id is required", error_code="missing_project_id", status=400)
        project = ProjectNoteProject.objects.filter(id=project_id).first()
        if not _can_access_project(request, project):
            return _api_error("forbidden", error_code="forbidden", status=403)

        rows = list(ProjectNoteDigest.objects.filter(project_id=project_id).order_by("digest_type"))
        if not rows:
            data = _generate_project_digests(project, updated_by=_current_user_id(request))
            rows = list(ProjectNoteDigest.objects.filter(project_id=project_id).order_by("digest_type"))
        else:
            data = {}
        out = {}
        for r in rows:
            out[r.digest_type] = {
                "content_text": r.content_text,
                "payload": _json_loads(r.payload_json, {}),
                "updated_at": r.updated_at.isoformat(),
            }
        if data and "summary" in data:
            _write_audit(request, action="digest_generate", status="ok", project=project, detail={"auto": True})
        return _safe_json_response({"ok": True, "digests": out})

    body = _read_json_body(request)
    project_id = _to_int(body.get("project_id"), 0)
    if project_id <= 0:
        return _api_error("project_id is required", error_code="missing_project_id", status=400)
    project = ProjectNoteProject.objects.filter(id=project_id).first()
    if not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)

    data = _generate_project_digests(project, updated_by=_current_user_id(request))
    _write_audit(request, action="digest_generate", status="ok", project=project, detail={"manual": True})
    return _safe_json_response({"ok": True, "generated": data})


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_sources(request: HttpRequest):
    if request.method == "GET":
        project_id = _to_int(request.GET.get("project_id"), 0)
        if project_id <= 0:
            return _api_error("project_id is required", error_code="missing_project_id", status=400)
        project = ProjectNoteProject.objects.filter(id=project_id).first()
        if not _can_access_project(request, project):
            return _api_error("forbidden", error_code="forbidden", status=403)
        rows = ProjectNoteSource.objects.filter(project_id=project_id).order_by("-id")
        data = []
        for s in rows:
            if not _can_access_source(request, s):
                continue
            reference_url = ""
            if _safe_text(s.original_filename).startswith("http"):
                reference_url = _safe_text(s.original_filename)
            data.append(
                {
                    "id": s.id,
                    "project_id": s.project_id,
                    "title": s.title,
                    "source_type": s.source_type,
                    "reference_url": reference_url,
                    "snapshot_no": s.snapshot_no,
                    "source_version": s.source_version,
                    "is_enabled": s.is_enabled,
                    "chunk_count": s.chunks.count(),
                    "updated_at": s.updated_at.isoformat(),
                }
            )
        return _safe_json_response({"ok": True, "sources": data})

    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    project_id = _to_int(request.POST.get("project_id"), 0)
    title = _safe_text(request.POST.get("title"))
    if project_id <= 0:
        return _api_error("project_id is required", error_code="missing_project_id", status=400)
    if not title:
        return _api_error("title is required", error_code="missing_title", status=400)

    project = ProjectNoteProject.objects.filter(id=project_id).first()
    if not project:
        return _api_error("project not found", error_code="project_not_found", status=404)
    if not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)

    upload = request.FILES.get("file")
    if not upload:
        return _api_error("file is required", error_code="missing_file", status=400)
    upload_size = _to_int(getattr(upload, "size", 0), 0)
    if upload_size <= 0:
        return _safe_json_response({"ok": False, "error": "empty file"}, status=400)
    if upload_size > (MAX_UPLOAD_MB * 1024 * 1024):
        return _safe_json_response(
            {"ok": False, "error": f"file too large, limit={MAX_UPLOAD_MB}MB"},
            status=400,
        )

    try:
        raw_text, source_type = _parse_upload_file_to_text(upload)
    except Exception as e:
        return _safe_json_response({"ok": False, "error": f"parse failed: {e}"}, status=400)

    try:
        source, chunk_count = _create_source_from_text(
            project_id=project_id,
            title=title,
            raw_text=raw_text,
            source_type=source_type,
            original_filename=_safe_text(getattr(upload, "name", "")),
        )
    except Exception as e:
        return _safe_json_response({"ok": False, "error": str(e)}, status=400)
    _write_audit(
        request,
        action="source_upload",
        status="ok",
        project=project,
        detail={"source_id": source.id, "title": source.title, "chunk_count": chunk_count},
    )
    _generate_project_digests(project, updated_by=_current_user_id(request))

    return _safe_json_response(
        {
            "ok": True,
            "source": {
                "id": source.id,
                "title": source.title,
                "snapshot_no": source.snapshot_no,
                "source_version": source.source_version,
                "chunk_count": chunk_count,
            },
        }
    )


@require_node("projectnotes", api=True)
@api_guard
def api_turns(request: HttpRequest):
    if request.method != "GET":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)
    conversation_id = _to_int(request.GET.get("conversation_id"), 0)
    if conversation_id <= 0:
        return _api_error("conversation_id is required", error_code="missing_conversation_id", status=400)
    conv = ProjectNoteConversation.objects.filter(id=conversation_id).select_related("project").first()
    if not conv:
        return _api_error("conversation not found", error_code="conversation_not_found", status=404)
    if not _can_access_project(request, conv.project):
        return _api_error("forbidden", error_code="forbidden", status=403)
    rows = ProjectNoteTurn.objects.filter(conversation_id=conversation_id).order_by("id")
    turns = []
    for t in rows:
        turns.append(
            {
                "id": t.id,
                "question": t.question,
                "answer": t.answer,
                "citations": _json_loads(t.citations_json, []),
                "confidence": t.confidence,
                "created_at": t.created_at.isoformat(),
            }
        )
    return _safe_json_response({"ok": True, "turns": turns})


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_source_toggle(request: HttpRequest, source_id: int):
    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)
    body = _read_json_body(request)
    enabled = bool(body.get("is_enabled", True))
    source = ProjectNoteSource.objects.filter(id=source_id).first()
    if not source:
        return _api_error("source not found", error_code="source_not_found", status=404)
    if not _can_access_source(request, source):
        return _api_error("forbidden", error_code="forbidden", status=403)
    source.is_enabled = enabled
    source.save(update_fields=["is_enabled", "updated_at"])
    _write_audit(
        request,
        action="source_toggle",
        status="ok",
        project=source.project,
        detail={"source_id": source.id, "is_enabled": source.is_enabled},
    )
    return _safe_json_response({"ok": True, "source": {"id": source.id, "is_enabled": source.is_enabled}})


@require_node("projectnotes", api=True)
@api_guard
def api_source_versions(request: HttpRequest):
    if request.method != "GET":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)
    project_id = _to_int(request.GET.get("project_id"), 0)
    if project_id <= 0:
        return _api_error("project_id is required", error_code="missing_project_id", status=400)
    project = ProjectNoteProject.objects.filter(id=project_id).first()
    if not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)

    rows = list(
        ProjectNoteSource.objects.filter(project_id=project_id)
        .order_by("title", "-snapshot_no", "-id")
        .values("id", "title", "snapshot_no", "source_version", "source_type", "is_enabled", "updated_at")
    )
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        t = _safe_text(r.get("title")) or "(untitled)"
        grouped.setdefault(t, []).append(
            {
                "id": r["id"],
                "snapshot_no": r["snapshot_no"],
                "source_version": r["source_version"],
                "source_type": r["source_type"],
                "is_enabled": bool(r["is_enabled"]),
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else "",
            }
        )
    out = []
    for title, versions in grouped.items():
        out.append({"title": title, "versions": versions, "latest_id": versions[0]["id"] if versions else 0})
    return _safe_json_response({"ok": True, "items": out})


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_source_resync(request: HttpRequest, source_id: int):
    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)
    source = ProjectNoteSource.objects.filter(id=source_id).first()
    if not source:
        return _api_error("source not found", error_code="source_not_found", status=404)
    if not _can_access_source(request, source):
        return _api_error("forbidden", error_code="forbidden", status=403)
    source_url = _safe_text(source.original_filename)
    if not source_url.startswith("http"):
        return _api_error("source is not a web reference", error_code="not_web_reference", status=400)

    try:
        raw_text, fetched_title = _fetch_web_text(source_url)
    except Exception as e:
        return _api_error(f"fetch failed: {e}", error_code="fetch_failed", status=502)
    if not _safe_text(raw_text):
        return _api_error("web page has no extractable text", error_code="empty_web_text", status=400)

    try:
        new_source, chunk_count = _create_source_from_text(
            project_id=source.project_id,
            title=source.title or fetched_title,
            raw_text=raw_text,
            source_type="reference",
            original_filename=source_url[:240],
        )
    except Exception as e:
        return _api_error(str(e), error_code="resync_failed", status=400)
    _write_audit(
        request,
        action="source_resync",
        status="ok",
        project=source.project,
        detail={"from_source_id": source.id, "new_source_id": new_source.id, "chunk_count": chunk_count},
    )
    _generate_project_digests(source.project, updated_by=_current_user_id(request))

    return _safe_json_response(
        {
            "ok": True,
            "source": {
                "id": new_source.id,
                "title": new_source.title,
                "snapshot_no": new_source.snapshot_no,
                "source_version": new_source.source_version,
                "chunk_count": chunk_count,
            },
        }
    )


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_web_search(request: HttpRequest):
    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    body = _read_json_body(request)
    query = _safe_text(body.get("query"))
    limit = _to_int(body.get("limit"), 10)
    limit = max(1, min(10, limit))
    if not query:
        return _api_error("query is required", error_code="missing_query", status=400)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            timeout=12,
            headers=headers,
        )
        resp.raise_for_status()
    except Exception as e:
        return _safe_json_response({"ok": False, "error": f"search failed: {e}"}, status=502)

    soup = BeautifulSoup(resp.text, "lxml")
    out: List[Dict[str, str]] = []
    for a in soup.select("a.result__a"):
        href = _normalize_search_url(_safe_text(a.get("href")))
        title = _safe_text(a.get_text(" ", strip=True))
        if not href or not title:
            continue
        wrap = a.find_parent(class_="result")
        snippet = ""
        if wrap:
            s = wrap.select_one(".result__snippet")
            if s:
                snippet = _safe_text(s.get_text(" ", strip=True))
        out.append({"title": title, "url": href, "snippet": snippet})
        if len(out) >= limit:
            break

    return _safe_json_response({"ok": True, "query": query, "results": out})


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_sources_web_import(request: HttpRequest):
    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    body = _read_json_body(request)
    project_id = _to_int(body.get("project_id"), 0)
    title = _safe_text(body.get("title"))
    source_url = _safe_text(body.get("source_url"))
    source_urls = body.get("source_urls") if isinstance(body.get("source_urls"), list) else []

    if project_id <= 0:
        return _api_error("project_id is required", error_code="missing_project_id", status=400)
    url_list: List[str] = []
    if source_urls:
        url_list = [_normalize_search_url(_safe_text(x)) for x in source_urls if _safe_text(x)]
    elif source_url:
        url_list = [_normalize_search_url(source_url)]

    if not url_list:
        return _api_error("source_url/source_urls is required", error_code="missing_source_url", status=400)
    if len(url_list) > 10:
        return _safe_json_response({"ok": False, "error": "每次網路資源匯入上限為 10 筆"}, status=400)

    for u in url_list:
        if not _is_http_url(u):
            return _safe_json_response({"ok": False, "error": f"invalid url: {u}"}, status=400)

    project = ProjectNoteProject.objects.filter(id=project_id).first()
    if not project:
        return _api_error("project not found", error_code="project_not_found", status=404)
    if not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)

    imported: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []

    for idx, u in enumerate(url_list, start=1):
        try:
            raw_text, fetched_title = _fetch_web_text(u)
            if not _safe_text(raw_text):
                failed.append({"url": u, "error": "web page has no extractable text"})
                continue
            title_final = title if (title and len(url_list) == 1) else fetched_title or f"web_source_{idx}"
            source, chunk_count = _create_source_from_text(
                project_id=project_id,
                title=title_final[:240],
                raw_text=raw_text,
                source_type="reference",
                original_filename=u[:240],
            )
            imported.append(
                {
                    "id": source.id,
                    "title": source.title,
                    "source_type": source.source_type,
                    "source_version": source.source_version,
                    "chunk_count": chunk_count,
                    "url": u,
                }
            )
        except Exception as e:
            failed.append({"url": u, "error": str(e)})

    if not imported:
        _write_audit(
            request,
            action="source_web_import",
            status="failed",
            project=project,
            detail={"count": 0, "failed": failed[:5]},
        )
        return _safe_json_response({"ok": False, "error": "all web imports failed", "failed": failed}, status=502)

    _write_audit(
        request,
        action="source_web_import",
        status="ok",
        project=project,
        detail={"count": len(imported), "failed_count": len(failed)},
    )
    _generate_project_digests(project, updated_by=_current_user_id(request))

    return _safe_json_response(
        {
            "ok": True,
            "source": imported[0],  # backward compatibility for existing frontend
            "imported": imported,
            "failed": failed,
            "count": len(imported),
        }
    )


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_conversations(request: HttpRequest):
    if request.method == "GET":
        project_id = _to_int(request.GET.get("project_id"), 0)
        if project_id <= 0:
            return _api_error("project_id is required", error_code="missing_project_id", status=400)
        project = ProjectNoteProject.objects.filter(id=project_id).first()
        if not _can_access_project(request, project):
            return _api_error("forbidden", error_code="forbidden", status=403)
        rows = ProjectNoteConversation.objects.filter(project_id=project_id).order_by("-updated_at", "-id")[:60]
        data = []
        for c in rows:
            data.append(
                {
                    "id": c.id,
                    "title": c.title or f"對話 {c.id}",
                    "selected_source_ids": _json_loads(c.selected_source_ids_json, []),
                    "turn_count": c.turns.count(),
                    "updated_at": c.updated_at.isoformat(),
                }
            )
        return _safe_json_response({"ok": True, "conversations": data})

    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    body = _read_json_body(request)
    project_id = _to_int(body.get("project_id"), 0)
    if project_id <= 0:
        return _api_error("project_id is required", error_code="missing_project_id", status=400)
    project = ProjectNoteProject.objects.filter(id=project_id).first()
    if not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)

    title = _safe_text(body.get("title")) or "新對話"
    selected_source_ids = body.get("selected_source_ids") if isinstance(body.get("selected_source_ids"), list) else []
    selected_source_ids = [_to_int(x, 0) for x in selected_source_ids]
    selected_source_ids = [x for x in selected_source_ids if x > 0]
    version_mode = _safe_text(body.get("version_mode")).lower() or "latest_only"
    scoped_source_ids = _resolve_source_ids_for_scope(project_id, selected_source_ids, version_mode)

    created_by = _safe_text(getattr(request, "login_user", "")) or _safe_text(getattr(request.user, "username", ""))

    conv = ProjectNoteConversation.objects.create(
        project_id=project_id,
        title=title,
        selected_source_ids_json=json.dumps(selected_source_ids, ensure_ascii=False),
        created_by=created_by,
    )
    _write_audit(
        request,
        action="conversation_create",
        status="ok",
        project=project,
        conversation=conv,
        detail={"conversation_id": conv.id},
    )
    return _safe_json_response({"ok": True, "conversation": {"id": conv.id, "title": conv.title}})


@dataclass
class _RankedEvidence:
    chunk_id: int
    source_id: int
    source_title: str
    chunk_index: int
    section_path: str
    content: str
    keyword_score: float
    vector_score: float
    rerank_score: float
    score: float


def _score_chunk_keyword(query: str, query_tokens: List[str], content: str) -> float:
    q_norm = query.lower()
    c_norm = content.lower()
    keyword_score = 0.0
    for tok in query_tokens:
        keyword_score += c_norm.count(tok)

    c_tokens = set(_normalize_tokens(content))
    q_set = set(query_tokens)
    jaccard = (len(q_set & c_tokens) / len(q_set | c_tokens)) if q_set and c_tokens else 0.0

    phrase_bonus = 1.4 if q_norm and q_norm in c_norm else 0.0
    return keyword_score + (jaccard * 8.0) + phrase_bonus


def _hash_embedding(text: str, dim: int = 256) -> List[float]:
    vec = [0.0] * dim
    toks = _normalize_tokens(text)
    if not toks:
        return vec
    for t in toks:
        h = hash(t)
        idx = abs(h) % dim
        sign = -1.0 if ((h >> 1) & 1) else 1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-9:
        return vec
    return [x / norm for x in vec]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0
    return sum(a[i] * b[i] for i in range(n))


def _score_chunk_vector(query_vec: List[float], content: str) -> float:
    c_vec = _hash_embedding(content)
    # cosine range is [-1, 1], normalize to [0, 1]
    return (_cosine(query_vec, c_vec) + 1.0) / 2.0


def _rerank_score(
    *,
    query: str,
    query_tokens: List[str],
    context_tokens: List[str],
    content: str,
    keyword_score: float,
    vector_score: float,
) -> float:
    c_norm = content.lower()
    context_overlap = 0.0
    if context_tokens:
        c_set = set(_normalize_tokens(content))
        ct_set = set(context_tokens)
        if c_set and ct_set:
            context_overlap = len(c_set & ct_set) / max(1, len(ct_set))

    exact_phrase = 1.0 if query.lower() and query.lower() in c_norm else 0.0
    # Hybrid merge + rerank
    return (keyword_score * 0.62) + (vector_score * 5.2) + (context_overlap * 1.8) + exact_phrase


def _retrieve_evidence(
    project_id: int,
    query: str,
    selected_source_ids: List[int],
    conversation_context: str = "",
) -> List[_RankedEvidence]:
    chunks_qs = ProjectNoteChunk.objects.filter(source__project_id=project_id, source__is_enabled=True).select_related("source")
    if selected_source_ids:
        chunks_qs = chunks_qs.filter(source_id__in=selected_source_ids)

    query_tokens = _normalize_tokens(query)
    context_tokens = _normalize_tokens(conversation_context)
    query_vec = _hash_embedding(query + "\n" + conversation_context)
    ranked: List[_RankedEvidence] = []
    for ch in chunks_qs[:5000]:
        keyword_score = _score_chunk_keyword(query, query_tokens, ch.content)
        vector_score = _score_chunk_vector(query_vec, ch.content)
        # candidate gate: retain either lexical or vector-similar chunks
        if keyword_score <= 0 and vector_score < 0.52:
            continue
        rerank_score = _rerank_score(
            query=query,
            query_tokens=query_tokens,
            context_tokens=context_tokens,
            content=ch.content,
            keyword_score=keyword_score,
            vector_score=vector_score,
        )
        ranked.append(
            _RankedEvidence(
                chunk_id=ch.id,
                source_id=ch.source_id,
                source_title=ch.source.title,
                chunk_index=ch.chunk_index,
                section_path=_safe_text(ch.section_path),
                content=ch.content,
                keyword_score=keyword_score,
                vector_score=vector_score,
                rerank_score=rerank_score,
                score=rerank_score,
            )
        )

    ranked.sort(key=lambda x: x.rerank_score, reverse=True)
    top = ranked[:10]
    if not top:
        return []

    expanded: Dict[Tuple[int, int], _RankedEvidence] = {}
    for item in top:
        for offset in (-1, 0, 1):
            idx = item.chunk_index + offset
            if idx < 0:
                continue
            neighbor = (
                ProjectNoteChunk.objects.filter(source_id=item.source_id, chunk_index=idx)
                .select_related("source")
                .first()
            )
            if not neighbor:
                continue
            key = (neighbor.source_id, neighbor.chunk_index)
            if key not in expanded:
                expanded[key] = _RankedEvidence(
                    chunk_id=neighbor.id,
                    source_id=neighbor.source_id,
                    source_title=neighbor.source.title,
                    chunk_index=neighbor.chunk_index,
                    section_path=_safe_text(neighbor.section_path),
                    content=neighbor.content,
                    keyword_score=item.keyword_score,
                    vector_score=item.vector_score,
                    rerank_score=item.rerank_score - (0.25 if offset != 0 else 0),
                    score=item.rerank_score - (0.25 if offset != 0 else 0),
                )
    out = sorted(expanded.values(), key=lambda x: x.rerank_score, reverse=True)
    return out[:14]


def _build_evidence_payload(items: Iterable[_RankedEvidence]) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    blocks: List[str] = []
    citations: List[Dict[str, Any]] = []
    used_sources: Dict[int, Dict[str, Any]] = {}
    seq = list(items)
    source_ids = sorted({x.source_id for x in seq})
    source_url_map: Dict[int, str] = {}
    if source_ids:
        for row in ProjectNoteSource.objects.filter(id__in=source_ids).values("id", "original_filename"):
            u = _safe_text(row.get("original_filename"))
            source_url_map[_to_int(row.get("id"), 0)] = u if u.startswith("http") else ""

    for i, e in enumerate(seq, start=1):
        excerpt = _safe_text(e.content)[:280]
        source_url = source_url_map.get(e.source_id, "")
        sec = _safe_text(e.section_path)
        sec_line = f" section={sec}" if sec else ""
        blocks.append(f"[C{i}] source={e.source_title}{sec_line} chunk={e.chunk_index}\n{excerpt}")
        citations.append(
            {
                "ref": f"C{i}",
                "source_id": e.source_id,
                "source_title": e.source_title,
                "chunk_index": e.chunk_index,
                "section_path": sec,
                "excerpt": excerpt,
                "source_url": source_url if source_url.startswith("http") else "",
            }
        )
        used_sources[e.source_id] = {
            "source_id": e.source_id,
            "title": e.source_title,
            "source_url": source_url if source_url.startswith("http") else "",
        }

    return "\n\n".join(blocks), citations, list(used_sources.values())


def _append_reference_section(answer: str, citations: List[Dict[str, Any]]) -> str:
    base = _safe_text(answer)
    if not citations:
        return base
    if "出處：" in base or "出處:" in base:
        return base
    lines: List[str] = []
    for c in citations[:4]:
        ref = _safe_text(c.get("ref"))
        title = _safe_text(c.get("source_title"))
        idx = _to_int(c.get("chunk_index"), 0)
        u = _safe_text(c.get("source_url"))
        if u:
            lines.append(f"[{ref}] {title} (chunk {idx}) - {u}")
        else:
            lines.append(f"[{ref}] {title} (chunk {idx})")
    return (base + "\n\n出處：\n" + "\n".join(lines)).strip()


def _evidence_quality(evidence: List[_RankedEvidence]) -> Dict[str, float]:
    if not evidence:
        return {"top_score": 0.0, "avg_top3": 0.0, "source_count": 0.0, "count": 0.0}
    top_score = float(evidence[0].rerank_score)
    top3 = evidence[:3]
    avg_top3 = sum(x.rerank_score for x in top3) / max(1, len(top3))
    source_count = len({x.source_id for x in evidence})
    return {
        "top_score": top_score,
        "avg_top3": avg_top3,
        "source_count": float(source_count),
        "count": float(len(evidence)),
    }


def _detect_conflicts(evidence: List[_RankedEvidence]) -> List[Dict[str, Any]]:
    if len(evidence) < 2:
        return []

    positive = {"可", "可以", "允許", "應", "必須", "需要", "採用", "同意"}
    negative = {"不可", "不得", "禁止", "不應", "不需", "駁回", "拒絕", "無法"}
    date_re = re.compile(r"(20\d{2}[/-]\d{1,2}[/-]\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)")

    top = evidence[:8]
    src_signs: Dict[int, int] = {}
    src_dates: Dict[int, set[str]] = {}
    for e in top:
        txt = _safe_text(e.content)
        sign = 0
        if any(k in txt for k in positive):
            sign += 1
        if any(k in txt for k in negative):
            sign -= 1
        if sign != 0:
            src_signs[e.source_id] = sign if src_signs.get(e.source_id, 0) == 0 else src_signs[e.source_id]
        for d in date_re.findall(txt):
            src_dates.setdefault(e.source_id, set()).add(d)

    conflicts: List[Dict[str, Any]] = []
    pos_src = [sid for sid, s in src_signs.items() if s > 0]
    neg_src = [sid for sid, s in src_signs.items() if s < 0]
    if pos_src and neg_src:
        conflicts.append(
            {
                "type": "stance_conflict",
                "detail": "sources contain opposite policy stance",
                "source_ids": sorted(set(pos_src + neg_src)),
            }
        )

    all_dates = set()
    for ds in src_dates.values():
        all_dates.update(ds)
    if len(all_dates) >= 2:
        involved = [sid for sid, ds in src_dates.items() if ds]
        conflicts.append(
            {
                "type": "date_conflict",
                "detail": "sources mention inconsistent dates",
                "dates": sorted(all_dates)[:6],
                "source_ids": sorted(set(involved)),
            }
        )
    return conflicts


def _build_default_followups(question: str, not_found_topics: List[str], has_conflict: bool) -> List[str]:
    q = _safe_text(question)
    out: List[str] = []
    if has_conflict:
        out.append("是否要我只用最新版本來源重新回答？")
        out.append("是否要我列出衝突來源的逐條差異？")
    if not_found_topics:
        out.append("是否要縮小問題範圍到單一子題再查詢？")
        out.append("是否要新增相關來源後再回答？")
    if q:
        out.append("是否要我改成條列重點並附每點出處？")
    uniq: List[str] = []
    seen = set()
    for x in out:
        k = x.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        uniq.append(k)
    return uniq[:3]


def _call_llm_answer(question: str, evidence_text: str) -> Dict[str, Any]:
    prompt = f"""
你是「專案筆記查詢」助理。你只能根據 evidence 回答，不可使用外部常識補完專案事實。

規則：
1) 重要陳述都要引用 C 編號。
2) 如果 evidence 不足，必須明確說「來源不足，無法確認」。
3) 若 evidence 互相矛盾，指出衝突點與來源編號。
4) 禁止捏造來源或引用。

問題：
{question}

evidence:
{evidence_text}

請輸出 JSON：
{{
  "answer": "最終回答（繁體中文）",
  "confidence": 0.0,
  "not_found_topics": ["若無可空陣列"],
  "followup_questions": ["最多3個"]
}}
""".strip()

    llm = get_chat_model(temperature=0.1, timeout=90)
    out = llm.invoke(prompt)
    raw = out.content if hasattr(out, "content") else str(out)
    data = _extract_json_from_llm(raw)
    if not isinstance(data, dict):
        return {}
    return data


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_chat(request: HttpRequest):
    t0 = time.perf_counter()
    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    body = _read_json_body(request)
    project_id = _to_int(body.get("project_id"), 0)
    if project_id <= 0:
        return _api_error("project_id is required", error_code="missing_project_id", status=400)
    question = _safe_text(body.get("question"))
    if not question:
        return _api_error("question is required", error_code="missing_question", status=400)

    project = ProjectNoteProject.objects.filter(id=project_id).first()
    if not project:
        return _api_error("project not found", error_code="project_not_found", status=404)
    if not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)

    selected_source_ids = body.get("selected_source_ids") if isinstance(body.get("selected_source_ids"), list) else []
    selected_source_ids = [_to_int(x, 0) for x in selected_source_ids]
    selected_source_ids = [x for x in selected_source_ids if x > 0]

    conversation_id = _to_int(body.get("conversation_id"), 0)
    conversation = ProjectNoteConversation.objects.filter(id=conversation_id, project_id=project_id).first()
    if not conversation:
        conversation = ProjectNoteConversation.objects.create(
            project_id=project_id,
            title=(question[:24] + "...") if len(question) > 24 else question,
            selected_source_ids_json=json.dumps(selected_source_ids, ensure_ascii=False),
            created_by=_safe_text(getattr(request, "login_user", "")) or _safe_text(getattr(request.user, "username", "")),
        )
        _write_audit(request, action="conversation_create", status="ok", project=project, conversation=conversation, detail={})

    recent_turns = list(
        ProjectNoteTurn.objects.filter(conversation_id=conversation.id).order_by("-id")[:3]
    )
    ctx_lines: List[str] = []
    for t in reversed(recent_turns):
        if _safe_text(t.question):
            ctx_lines.append(f"Q: {t.question}")
        if _safe_text(t.answer):
            ctx_lines.append(f"A: {t.answer[:240]}")
    conversation_context = "\n".join(ctx_lines)

    accessible_ids: List[int] = []
    if scoped_source_ids:
        source_rows = {
            s.id: s
            for s in ProjectNoteSource.objects.filter(id__in=scoped_source_ids).select_related("project")
        }
        for sid in scoped_source_ids:
            s = source_rows.get(sid)
            if s and _can_access_source(request, s):
                accessible_ids.append(sid)
    scoped_source_ids = accessible_ids
    evidence = _retrieve_evidence(project_id, question, scoped_source_ids, conversation_context=conversation_context)
    quality = _evidence_quality(evidence)
    insufficient = (quality["count"] < 2.0) or (quality["top_score"] < 1.25) or (quality["avg_top3"] < 1.05)
    if not evidence or insufficient:
        answer = "目前已選來源內找不到足夠證據，來源不足，無法確認。"
        not_found_topics = [question]
        followup_questions = _build_default_followups(question, not_found_topics, has_conflict=False)
        turn = ProjectNoteTurn.objects.create(
            conversation=conversation,
            question=question,
            answer=answer,
            citations_json="[]",
            used_sources_json="[]",
            confidence=0.0,
            not_found_topics_json=json.dumps(not_found_topics, ensure_ascii=False),
            followup_questions_json=json.dumps(followup_questions, ensure_ascii=False),
        )
        _write_audit(
            request,
            action="chat_query",
            status="insufficient",
            project=project,
            conversation=conversation,
            detail={
                "question": question[:240],
                "scoped_source_ids": scoped_source_ids,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return _safe_json_response(
            {
                "ok": True,
                "conversation_id": conversation.id,
                "turn_id": turn.id,
                "answer": answer,
                "confidence": 0.0,
                "citations": [],
                "used_sources": [],
                "not_found_topics": not_found_topics,
                "followup_questions": followup_questions,
                "conflicts": [],
            }
        )

    conflicts = _detect_conflicts(evidence)
    evidence_text, citations, used_sources = _build_evidence_payload(evidence)
    llm_data: Dict[str, Any] = {}
    try:
        llm_data = _call_llm_answer(question, evidence_text)
    except Exception:
        llm_data = {}

    answer = _safe_text(llm_data.get("answer"))
    if not answer:
        top_lines = [f"- [{c['ref']}] {c['source_title']}：{c['excerpt']}" for c in citations[:4]]
        answer = "根據目前來源，我找到以下相關證據：\n" + "\n".join(top_lines)
    if conflicts:
        conflict_lines = []
        for cf in conflicts:
            src_ids = ",".join(str(x) for x in (cf.get("source_ids") or []))
            detail = _safe_text(cf.get("detail"))
            if cf.get("type") == "date_conflict":
                dates = ",".join(cf.get("dates") or [])
                conflict_lines.append(f"- 日期衝突：{detail}（來源#{src_ids}；日期={dates}）")
            else:
                conflict_lines.append(f"- 立場衝突：{detail}（來源#{src_ids}）")
        if conflict_lines:
            answer = answer.strip() + "\n\n衝突來源提醒：\n" + "\n".join(conflict_lines)
    answer = _append_reference_section(answer, citations)

    confidence = llm_data.get("confidence")
    try:
        confidence_value = float(confidence)
    except Exception:
        confidence_value = 0.55
    confidence_value = max(0.0, min(1.0, confidence_value))

    not_found_topics = llm_data.get("not_found_topics") if isinstance(llm_data.get("not_found_topics"), list) else []
    followup_questions = llm_data.get("followup_questions") if isinstance(llm_data.get("followup_questions"), list) else []
    not_found_topics = [_safe_text(x) for x in not_found_topics if _safe_text(x)]
    followup_questions = [_safe_text(x) for x in followup_questions if _safe_text(x)][:3]
    if not followup_questions:
        followup_questions = _build_default_followups(question, not_found_topics, has_conflict=bool(conflicts))
    elif len(followup_questions) < 2:
        extra = _build_default_followups(question, not_found_topics, has_conflict=bool(conflicts))
        followup_questions = (followup_questions + extra)[:3]

    turn = ProjectNoteTurn.objects.create(
        conversation=conversation,
        question=question,
        answer=answer,
        citations_json=json.dumps(citations, ensure_ascii=False),
        used_sources_json=json.dumps(used_sources, ensure_ascii=False),
        confidence=confidence_value,
        not_found_topics_json=json.dumps(not_found_topics, ensure_ascii=False),
        followup_questions_json=json.dumps(followup_questions, ensure_ascii=False),
    )
    _write_audit(
        request,
        action="chat_query",
        status="ok",
        project=project,
        conversation=conversation,
        detail={
            "question": question[:240],
            "confidence": confidence_value,
            "used_source_ids": [x.get("source_id") for x in used_sources],
            "conflict_count": len(conflicts),
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        },
    )

    conversation.selected_source_ids_json = json.dumps(selected_source_ids, ensure_ascii=False)
    conversation.save(update_fields=["selected_source_ids_json", "updated_at"])

    return _safe_json_response(
        {
            "ok": True,
            "conversation_id": conversation.id,
            "turn_id": turn.id,
            "answer": answer,
            "confidence": confidence_value,
            "citations": citations,
            "used_sources": used_sources,
            "version_mode": version_mode,
            "scoped_source_ids": scoped_source_ids,
            "not_found_topics": not_found_topics,
            "followup_questions": followup_questions,
            "conflicts": conflicts,
        }
    )


@require_node("projectnotes", api=True)
@api_guard
def api_citation_context(request: HttpRequest):
    source_id = _to_int(request.GET.get("source_id"), 0)
    chunk_index = _to_int(request.GET.get("chunk_index"), 0)
    if source_id <= 0:
        return _api_error("source_id is required", error_code="missing_source_id", status=400)

    rows = (
        ProjectNoteChunk.objects.filter(source_id=source_id, chunk_index__gte=max(0, chunk_index - 1), chunk_index__lte=chunk_index + 1)
        .order_by("chunk_index")
    )
    source = ProjectNoteSource.objects.filter(id=source_id).first()
    if not _can_access_source(request, source):
        return _api_error("forbidden", error_code="forbidden", status=403)
    return _safe_json_response(
        {
            "ok": True,
            "source": {
                "id": source_id,
                "title": source.title if source else "",
                "reference_url": (_safe_text(source.original_filename) if source and _safe_text(source.original_filename).startswith("http") else ""),
            },
            "chunks": [{"chunk_index": r.chunk_index, "section_path": _safe_text(r.section_path), "content": r.content} for r in rows],
        }
    )


@require_node("projectnotes", api=True)
@api_guard
def api_overview(request: HttpRequest):
    project_id = _to_int(request.GET.get("project_id"), 0)
    if project_id <= 0:
        return _api_error("project_id is required", error_code="missing_project_id", status=400)

    project = ProjectNoteProject.objects.filter(id=project_id).first()
    if not project:
        return _api_error("project not found", error_code="project_not_found", status=404)
    if not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)

    digests = {d.digest_type: d for d in ProjectNoteDigest.objects.filter(project_id=project_id)}
    if not digests:
        generated = _generate_project_digests(project, updated_by=_current_user_id(request))
        _write_audit(request, action="digest_generate", status="ok", project=project, detail={"auto": True})
        summary = _safe_text(generated.get("summary"))
        faq = generated.get("faq") if isinstance(generated.get("faq"), list) else []
        decisions = generated.get("decisions") if isinstance(generated.get("decisions"), list) else []
        keywords = _normalize_tokens(summary)[:8]
        return _safe_json_response(
            {
                "ok": True,
                "overview": {
                    "summary": summary,
                    "faq": faq[:3],
                    "keywords": keywords,
                    "decisions": decisions[:3],
                },
            }
        )

    summary_row = digests.get("summary")
    faq_row = digests.get("faq")
    decisions_row = digests.get("decisions")
    summary = _safe_text(summary_row.content_text) if summary_row else ""
    faq = _json_loads(faq_row.payload_json, {}).get("faq", []) if faq_row else []
    decisions = _json_loads(decisions_row.payload_json, {}).get("decisions", []) if decisions_row else []
    faq = [_safe_text(x) for x in faq if _safe_text(x)][:3]
    decisions = [_safe_text(x) for x in decisions if _safe_text(x)][:3]
    keywords = _normalize_tokens(summary)[:8]

    return _safe_json_response(
        {
            "ok": True,
            "overview": {
                "summary": summary,
                "faq": faq,
                "keywords": keywords,
                "decisions": decisions,
            },
        }
    )


@csrf_exempt
@require_node("projectnotes", api=True)
@api_guard
def api_citation_click(request: HttpRequest):
    if request.method != "POST":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)
    body = _read_json_body(request)
    project_id = _to_int(body.get("project_id"), 0)
    source_id = _to_int(body.get("source_id"), 0)
    chunk_index = _to_int(body.get("chunk_index"), -1)
    project = ProjectNoteProject.objects.filter(id=project_id).first() if project_id > 0 else None
    if project_id > 0 and not _can_access_project(request, project):
        return _api_error("forbidden", error_code="forbidden", status=403)
    _write_audit(
        request,
        action="citation_click",
        status="ok",
        project=project,
        detail={"project_id": project_id, "source_id": source_id, "chunk_index": chunk_index},
    )
    return _safe_json_response({"ok": True})


@require_node("projectnotes")
def metrics_page(request: HttpRequest):
    return render(request, "projectnotes/metrics.html")


@require_node("projectnotes", api=True)
@api_guard
def api_metrics(request: HttpRequest):
    if request.method != "GET":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)

    days = _to_int(request.GET.get("days"), 7)
    days = max(1, min(90, days))
    project_id = _to_int(request.GET.get("project_id"), 0)
    now = timezone.now()
    since = now - timezone.timedelta(days=days)

    qs = ProjectNoteAuditLog.objects.filter(created_at__gte=since)
    if project_id > 0:
        p = ProjectNoteProject.objects.filter(id=project_id).first()
        if not _can_access_project(request, p):
            return _api_error("forbidden", error_code="forbidden", status=403)
        qs = qs.filter(project_id=project_id)
    else:
        allowed_project_ids = [p.id for p in ProjectNoteProject.objects.all() if _can_access_project(request, p)]
        qs = qs.filter(project_id__in=allowed_project_ids)

    total_queries = qs.filter(action="chat_query").count()
    insufficient_queries = qs.filter(action="chat_query", status="insufficient").count()
    citation_clicks = qs.filter(action="citation_click").count()
    usage_events = qs.count()

    # latency avg from detail_json.latency_ms
    latency_vals: List[float] = []
    for row in qs.filter(action="chat_query").values_list("detail_json", flat=True)[:5000]:
        d = _json_loads(row or "{}", {})
        try:
            v = float(d.get("latency_ms"))
            if v >= 0:
                latency_vals.append(v)
        except Exception:
            pass
    avg_latency_ms = (sum(latency_vals) / len(latency_vals)) if latency_vals else 0.0

    insufficient_rate = (insufficient_queries / total_queries) if total_queries > 0 else 0.0
    citation_click_rate = (citation_clicks / total_queries) if total_queries > 0 else 0.0

    return _safe_json_response(
        {
            "ok": True,
            "days": days,
            "project_id": project_id,
            "metrics": {
                "usage_count": usage_events,
                "query_count": total_queries,
                "insufficient_count": insufficient_queries,
                "insufficient_rate": round(insufficient_rate, 4),
                "citation_click_count": citation_clicks,
                "citation_click_rate": round(citation_click_rate, 4),
                "avg_latency_ms": round(avg_latency_ms, 2),
            },
        }
    )


@require_node("projectnotes")
def audit_page(request: HttpRequest):
    return render(request, "projectnotes/audit.html")


@require_node("projectnotes", api=True)
@api_guard
def api_audit_logs(request: HttpRequest):
    if request.method != "GET":
        return _api_error("method not allowed", error_code="method_not_allowed", status=405)
    project_id = _to_int(request.GET.get("project_id"), 0)
    user_id = _safe_text(request.GET.get("user_id"))
    limit = _to_int(request.GET.get("limit"), 100)
    limit = max(1, min(500, limit))

    qs = ProjectNoteAuditLog.objects.select_related("project", "conversation").order_by("-id")
    if project_id > 0:
        p = ProjectNoteProject.objects.filter(id=project_id).first()
        if not _can_access_project(request, p):
            return _api_error("forbidden", error_code="forbidden", status=403)
        qs = qs.filter(project_id=project_id)
    else:
        allowed_project_ids = [p.id for p in ProjectNoteProject.objects.all() if _can_access_project(request, p)]
        qs = qs.filter(project_id__in=allowed_project_ids)

    if user_id:
        qs = qs.filter(user_id__icontains=user_id)

    rows = list(qs[:limit])
    data = []
    for r in rows:
        data.append(
            {
                "id": r.id,
                "project_id": r.project_id,
                "project_name": r.project.name if r.project else "",
                "conversation_id": r.conversation_id,
                "action": r.action,
                "status": r.status,
                "user_id": r.user_id,
                "detail": _json_loads(r.detail_json, {}),
                "created_at": r.created_at.isoformat(),
            }
        )
    return _safe_json_response({"ok": True, "rows": data})

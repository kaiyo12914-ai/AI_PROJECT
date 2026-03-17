# webapps/doc/views_sybase_import.py
from __future__ import annotations # Trigger reload

import io
import base64
import json
import logging
import os
import re
from typing import Any, List, Tuple

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.utils_login import get_login_user_idno, get_login_user_name

# DBFactory（集中連線）— 禁止自行建立連線/禁止在此檔案 new pyodbc/pymssql
from webapps.doc.services.docService import docService

from webapps.doc.views_helpers import (
    _clean_tags,
    _draft_to_sections,
    _extract_text_by_ext,
    _normalize_doc_fields,
    _normalize_meta,
    _normalize_sections,
    _safe_str,
    _save_template_with_conflict_policy_v2,
    _valid_doc_types_set,
)

logger = logging.getLogger(__name__)

# Allowed TD_FORMAT and doc_type mapping (UTF-8 text)
_TD_FORMAT_TO_DOC_TYPE = {
    "便籤": "note",
    "簽呈": "sign_memo",
    "令": "order_draft",
    "呈": "submit_draft",
    "函": "letter_draft",
}
_MAIN_DOC_TD_FORMATS = ("簽呈", "令", "呈", "函", "便籤")
_MAIN_DOC_TD_FORMAT_SET = set(_MAIN_DOC_TD_FORMATS)
# ============================================================


# 使用規範（必讀）
# 1) DB 連線一律走 webapps/database/db_factory.py
# 2) API 必須加上 require_node("doc", api=True)
# 3) Sybase 查詢需限制 TM_PSID = login_user（本人承辦）
# 4) JSON 回應格式：{"ok": bool, ...}，錯誤用 error/detail
# 5) 端點名稱需與 views/urls 一致
# ============================================================

# ============================================================
# Sybase 既有公文 -> 範例庫（依 TM_GRSNO）
# - 需限制 TM_PSID = login_user
# - 可能同時有 DF(DCS0_DOC_FILE) / EF(DCS1_EMAL_FILE)
# ============================================================




def _json_error(error: str, *, status: int, detail: str | None = None) -> JsonResponse:
    """
    JSON 錯誤回應：
      {"ok": False, "error": "...", "detail": "...(optional)"}
    detail 只在 DOC_API_DEBUG=1 時返回。
    """
    payload: dict[str, Any] = {"ok": False, "error": error}

    allow_detail = str(os.getenv("DOC_API_DEBUG", "")).strip().lower() in ("1", "true", "yes", "y")
    if detail and allow_detail:
        payload["detail"] = detail

    return JsonResponse(payload, status=status)


def _debug_enabled() -> bool:
    return str(os.getenv("DOC_API_DEBUG", "")).strip().lower() in ("1", "true", "yes", "y")


def _format_stats(rows: List[Tuple]) -> dict:
    stats: dict[str, int] = {}
    for r in rows or []:
        fmt = _row_td_format(r) or "(empty)"
        stats[fmt] = stats.get(fmt, 0) + 1
    return stats


def _bytes_from_blob(x: Any) -> bytes:
    if x is None:
        return b""
    if isinstance(x, bytes):
        return x
    if isinstance(x, bytearray):
        return bytes(x)
    if isinstance(x, memoryview):
        return x.tobytes()
    # Oracle LOB object (oracledb): read while connection is alive.
    if hasattr(x, "read"):
        try:
            return x.read()
        except Exception as e:
            msg = str(e or "").upper()
            if "DPY-1001" in msg:
                raise RuntimeError("oracle lob read failed: detached connection (DPY-1001)") from e
            pass
    try:
        return bytes(x)
    except Exception:
        return b""


def _safe_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (bytes, bytearray, memoryview)):
        b = x.tobytes() if isinstance(x, memoryview) else bytes(x)
        # prefer SYBASE_CHARSET/CHAR, default cp950
        cs = (os.getenv("SYBASE_CHARSET") or os.getenv("SYBASE_CHAR") or "cp950").strip() or "cp950"
        def _decode_bytes(raw: bytes) -> str:
            if not raw:
                return ""
            if raw.startswith(b"\xef\xbb\xbf"):
                try:
                    return raw.decode("utf-8-sig")
                except Exception:
                    pass
            if raw.startswith(b"\xff\xfe"):
                try:
                    return raw.decode("utf-16le")
                except Exception:
                    pass
            if raw.startswith(b"\xfe\xff"):
                try:
                    return raw.decode("utf-16be")
                except Exception:
                    pass
            if raw.count(0) >= max(2, len(raw) // 4):
                for enc in ("utf-16le", "utf-16be"):
                    try:
                        return raw.decode(enc)
                    except Exception:
                        continue
            candidates = []
            for enc in ("utf-8", cs, "cp950", "big5", "latin-1"):
                if enc and enc not in candidates:
                    candidates.append(enc)
            for enc in candidates:
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            for enc in candidates:
                try:
                    return raw.decode(enc, errors="replace")
                except Exception:
                    continue
            return ""

        return _decode_bytes(b)
    if isinstance(x, str):
        return x
    return str(x)


def _strip_ctrl(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[\x00-\x1f]+", "", s)


def _row_td_format(row: Tuple) -> str:
    # TD_FORMAT 欄位在 idx 2
    try:
        return _strip_ctrl((_safe_text(row[2]) or "").strip())
    except Exception:
        return ""


def _row_td_subj(row: Tuple) -> str:
    # TD_SUBJ 欄位在 idx 3
    try:
        return _strip_ctrl((_safe_text(row[3]) or "").strip())
    except Exception:
        return ""

def _row_td_path(row: Tuple) -> str:
    # TD_PATH 甈???idx 7
    try:
        return _strip_ctrl((_safe_text(row[7]) or "").strip())
    except Exception:
        return ""


def _row_ef_name(row: Tuple) -> str:
    # EF_NAME 欄位在 idx 10 (after adding TD_PATH + DF_NAME/DF_DATA)
    try:
        return _strip_ctrl((_safe_text(row[10]) or "").strip())
    except Exception:
        return ""

def _row_df_name(row: Tuple) -> str:
    # DF_NAME 欄位在 idx 8
    v = ""
    try:
        v = _strip_ctrl((_safe_text(row[8]) or "").strip())
    except Exception:
        v = ""
    if v:
        return v

    v2 = ""
    try:
        v2 = _strip_ctrl((_safe_text(row[10]) or "").strip())
    except Exception:
        v2 = ""
    if v2:
        return v2

    try:
        return _strip_ctrl((_safe_text(row[3]) or "").strip())
    except Exception:
        return ""


def _row_df_name_only(row: Tuple) -> str:
    # 只取 DF_NAME，不做 EF/TD_SUBJ fallback（附件清單用）
    try:
        return _strip_ctrl((_safe_text(row[8]) or "").strip())
    except Exception:
        return ""

def _b64url_encode(s: str) -> str:
    raw = (s or "").encode("utf-8", errors="ignore")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _make_df_attach_key(td_path: str) -> str:
    return f"DF:{_b64url_encode(td_path or '')}"


def _build_attachments(rows: List[Tuple]) -> List[dict[str, str]]:
    """
    Build DF attachments list for preview UI.
    - Uses TD_PATH as key, DF_NAME as filename.
    """
    out: List[dict[str, str]] = []
    seen = set()
    for r in rows or []:
        td_path = _row_td_path(r)
        if not td_path:
            continue
        attach_key = _make_df_attach_key(td_path)
        if attach_key in seen:
            continue
        seen.add(attach_key)
        name = _row_df_name(r) or _row_td_subj(r) or "attachment"
        out.append({"attach_key": attach_key, "filename": name})
    return out


def _map_doc_type(fmt: str) -> str:
    s = _strip_ctrl((fmt or "")).strip()
    if not s:
        return ""
    if "簽呈" in s:
        return "sign_memo"
    if s == "呈" or ("呈" in s and "簽呈" not in s):
        return "submit_draft"
    if "令" in s:
        return "order_draft"
    if "函" in s:
        return "letter_draft"
    if "便籤" in s:
        return "note"
    return _TD_FORMAT_TO_DOC_TYPE.get(s, "")


def _normalize_selected_formats(raw: Any) -> List[str]:
    if raw is None:
        return []

    items: List[Any] = []
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [raw]

    out: List[str] = []
    for x in items:
        s = _strip_ctrl(_safe_str(x)).strip()
        if not s:
            continue
        if s in ("全部", "全選", "所有"):
            out.extend(["簽呈", "令", "呈", "函", "便籤"])
            continue
        if s in ("簽呈", "令", "呈", "函", "便籤"):
            out.append(s)
            continue
        out.append(s)

    seen = set()
    final: List[str] = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        final.append(s)
    return final


def _is_main_doc_td_format(fmt: str) -> bool:
    s = _strip_ctrl((fmt or "")).strip()
    if s == "便簽":
        s = "便籤"
    return s in _MAIN_DOC_TD_FORMAT_SET


def _build_doc_groups(rows: List[Tuple]) -> List[dict[str, Any]]:
    groups: List[dict[str, Any]] = []
    bucket: dict[str, dict[str, Any]] = {}

    for i, r in enumerate(rows or []):
        fmt = _row_td_format(r)
        subj = _row_td_subj(r)
        subj_norm = re.sub(r"\s+", " ", subj).strip()
        base = subj_norm or f"row{i}"
        if subj_norm:
            key = f"{fmt}::{subj_norm}"
        else:
            key = f"{fmt}::{base}"

        if key not in bucket:
            bucket[key] = {
                "key": key,
                "format": fmt,
                "subject": subj_norm,
                "base": base,
                "rows": [],
            }
            groups.append(bucket[key])
        bucket[key]["rows"].append(r)

    return groups

def _looks_binary(b: bytes) -> bool:
    if not b:
        return False
    # 0x00 常見於二進位（圖片/壓縮/Office）
    nul = b.count(b"\x00")
    if nul >= max(8, int(len(b) * 0.02)):
        return True
    return False


def _extract_text_from_blob(blob: bytes, filename: str) -> str:
    if not blob:
        return ""
    name = (filename or "").strip()
    if name:
        try:
            text = _extract_text_by_ext(io.BytesIO(blob), name).strip()
            if text:
                return text
        except Exception:
            pass
    if _looks_binary(blob):
        return ""
    text = _safe_text(blob)
    text = _strip_html_header_noise(text)
    return (text or "").strip()


def _strip_html_header_noise(s: str) -> str:
    """
    移除 HTML/DTD/Header 噪音，避免轉入範例時出現亂碼 Header。
    """
    t = (s or "").strip()
    if not t:
        return ""

    # 若包含 HTML/DTD，先移除 head/style/script 與 tag
    if "<html" in t.lower() or "<!doctype" in t.lower() or "<head" in t.lower():
    # 移除 head/style/script
        t = re.sub(r"(?is)<head.*?</head>", "", t)
        t = re.sub(r"(?is)<style.*?</style>", "", t)
        t = re.sub(r"(?is)<script.*?</script>", "", t)
    # 移除 HTML tag
        t = re.sub(r"(?is)<[^>]+>", "", t)

    # 移除 DTD/HTML header 片段
    t = re.sub(r"(?is)<!DOCTYPE[^>]*>", "", t)
    t = re.sub(r"(?is)PUBLIC\s+\"-//W3C//DTD.*?\"", "", t)
    t = re.sub(r"(?is)xmlns=\"[^\"]*\"", "", t)

    # 整理空白與換行
    t = re.sub(r"\r\n?", "\n", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _pick_doc_blob(tm_rstp: str, td_format: str, df_data: Any, ef_data: Any) -> bytes:
    """
    Select blob bytes for import.
    - EF_DATA (blob file content) is preferred when available.
    - DF_DATA is used as fallback.
    """
    dfb = _bytes_from_blob(df_data)
    efb = _bytes_from_blob(ef_data)
    return efb or dfb


def _extract_text_from_rows(rows: List[Tuple]) -> Tuple[str, str]:
    """
    從多筆資料中抽取主旨與內容
    回傳: (title, content_text)
    """
    best_title = ""
    best_text = ""

    # 優先用 TD_SUBJ 作為 title
    for r in rows:
        td_subj = _row_td_subj(r)
        if td_subj:
            best_title = td_subj
            break
    if not best_title:
        for r in rows:
            df_name = _row_df_name(r)
            if df_name:
                best_title = df_name
                break

    # 嘗試從 blob 解析文字
    for r in rows:
        tm_rstp = r[1] if len(r) > 1 else None
        td_format = r[2] if len(r) > 2 else None
        df_data = r[9] if len(r) > 9 else None
        ef_data = r[11] if len(r) > 11 else None

        blob = _pick_doc_blob(str(tm_rstp or ""), str(td_format or ""), df_data, ef_data)
        if not blob:
            continue
        # prefer EF name; fallback to DF name when EF name is empty
        name = _row_ef_name(r) or _row_df_name(r)
        text = _extract_text_from_blob(blob, name)
        if len(text) >= 30:
            best_text = text
            if not best_title:
                best_title = _row_td_subj(r) or _row_df_name(r)
            break

        # if still empty, try DF name with same blob (fallback for DF-only cases)
        if not text:
            text2 = _extract_text_from_blob(blob, _row_df_name(r))
            if len(text2) >= 30:
                best_text = text2
                if not best_title:
                    best_title = _row_td_subj(r) or _row_df_name(r)
                break

    # 仍無正文時，退而求其次組合格式/主旨/附件
    if not best_text:
        subj = best_title or (rows and _row_td_subj(rows[0]) or "")
        fmt0 = rows and _row_td_format(rows[0]) or ""
        names = []
        for r in rows:
            n = _row_df_name_only(r) or _row_ef_name(r)
            if n and n not in names:
                names.append(n)
        parts = []
        if fmt0:
            parts.append(f"格式：{fmt0}")
        if subj:
            parts.append(f"主旨：{subj}")
        if names:
            parts.append("附件：" + "；".join(names))
        best_text = "\n".join(parts).strip()

    return (best_title or ""), (best_text or "")

@csrf_exempt
@require_node("doc", api=True)
def api_import_template_from_sybase(request: HttpRequest) -> JsonResponse:
    """
    由 Sybase 既有公文（TM_GRSNO）轉入範例庫

    request JSON:
      - grsno: 既有公文相關號（TM_GRSNO）
      - action: preview/import（preview 僅回傳可轉入清單）
      - doc_keys: 轉入指定案件（preview 回傳的 key）
      - td_formats: 轉入類別（可複選；例：簽呈/令/呈/函/便簽/稿；preview 也可用）
      - doc_type: 既定 doc_type（未對應 TD_FORMAT 時才使用）
      - scope: public/personal（預設 personal）
      - tags: list[str]
      - title: 可覆寫標題
      - description: 可覆寫描述
      - on_conflict: overwrite/suffix（預設 suffix）
      - schema_ver: int（預設 2）
      - doc_fields/meta: dict
    """
    if request.method != "POST":
        return _json_error("method not allowed", status=405)

    # -------- parse body --------
    try:
        raw = (request.body or b"{}").decode("utf-8", errors="ignore")
        body = json.loads(raw) if raw else {}
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    # -------- auth / login_user --------
    dj_user = getattr(request, "user", None)
    is_auth = bool(dj_user and getattr(dj_user, "is_authenticated", False))

    login_user = (get_login_user_idno(request) or "").strip()
    login_user_name = (get_login_user_name(request) or "").strip()
    if not login_user:
        return _json_error("login user missing", status=401)

    # -------- inputs --------
    grsno = _safe_str(body.get("grsno")).strip()
    doc_type = _safe_str(body.get("doc_type")).strip()
    scope = (_safe_str(body.get("scope") or "personal").strip().lower() or "personal")
    on_conflict = (_safe_str(body.get("on_conflict") or "suffix").strip().lower() or "suffix")

    if not grsno:
        return _json_error("missing field: grsno", status=400)

    # 基本格式檢查：避免不合法字元
    # - 多數 TM_GRSNO 為數字，可視需求調整
    if not re.fullmatch(r"[0-9]{6,32}", grsno):
        return _json_error("invalid grsno format", status=400)

    if scope not in ("public", "personal"):
        return _json_error("invalid scope (public/personal)", status=400)

    if scope == "personal" and not is_auth:
        return _json_error("login required for personal templates", status=401)

    if on_conflict not in ("overwrite", "suffix"):
        on_conflict = "suffix"

    tags = _clean_tags(body.get("tags", []))
    title_override = _safe_str(body.get("title")).strip()
    desc_override = _safe_str(body.get("description")).strip()
    content_override = body.get("content_override") if isinstance(body.get("content_override"), dict) else {}

    # schema_ver 轉型失敗時預設 2
    try:
        schema_ver = int(body.get("schema_ver") or 2)
    except Exception:
        schema_ver = 2

    # -------- sybase query（本人承辦限制）--------
    try:
        svc = docService(login_user_id=login_user, login_user_name=login_user_name)
        # 依既定 SQL 僅用 TM_GRSNO 查詢
        rows = svc.query_import_from_template(grsno)
        if not rows:
            # fallback: incoming (DCS1) uses EM_GRSNO + EM_PSID
            rows = svc.lookup_incoming(login_user, grsno)
    except Exception as e:
        logger.warning("[sybase_import] query failed grsno=%s err=%s", grsno, str(e))
        return _json_error("db query failed", status=502, detail=str(e))

    if not rows:
        # 查無資料或無權限
        return _json_error("not found or no permission", status=404)

    # 只允許「呈文」格式可轉入（排除 TD_FORMAT='檔案' 等附件列）
    raw_format_stats = _format_stats(rows) if _debug_enabled() else None

    action = _safe_str(body.get("action") or body.get("mode")).strip().lower()
    preview_only = bool(body.get("preview") or body.get("preview_only")) or action in ("preview", "list")

    rows = [r for r in rows if _is_main_doc_td_format(_row_td_format(r))]
    if not rows:
        if preview_only:
            payload = {"ok": True, "grsno": grsno, "count": 0, "docs": []}
            if _debug_enabled():
                payload["meta"] = {
                    "rows_total": 0,
                    "formats": {},
                    "formats_all": raw_format_stats,
                    "selected_formats": [],
                }
            return JsonResponse(payload, status=200)
        return _json_error("no transferable main documents", status=400)

    if not preview_only and not tags:
        return _json_error("missing tags (required)", status=400)

    selected_formats = _normalize_selected_formats(
        body.get("td_formats") or body.get("td_format") or body.get("formats")
    )

    if selected_formats:
        rows = [r for r in rows if _row_td_format(r) in selected_formats]
        if not rows:
            if _debug_enabled():
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "no matched TD_FORMAT",
                        "formats": raw_format_stats,
                        "selected": selected_formats,
                    },
                    status=400,
                )
            return _json_error("no matched TD_FORMAT", status=400)

    # 僅使用 DF_NAME；若 DF_NAME 為空，視為不可轉入
    rows = [r for r in rows if _row_df_name(r)]
    if not rows:
        if preview_only:
            return JsonResponse({"ok": True, "grsno": grsno, "count": 0, "docs": []}, status=200)
        return _json_error("no documents with DF_NAME", status=400)

    # 依文件群組整理（同一格式 + 同一檔案視為同一案件）
    groups = _build_doc_groups(rows)

    if not selected_formats:
        fmt0 = _row_td_format(rows[0])
        mapped0 = _TD_FORMAT_TO_DOC_TYPE.get(fmt0)
        if mapped0:
            doc_type = mapped0
    valid_doc_types = _valid_doc_types_set()

    doc_fields = _normalize_doc_fields(body.get("doc_fields"))
    meta = _normalize_meta(body.get("meta"))

    # 預覽清單
    if preview_only:
        fmt_counts: dict[str, int] = {}
        for g in groups:
            fmt_counts[g["format"]] = fmt_counts.get(g["format"], 0) + 1

        fmt_seen: dict[str, int] = {}
        docs: list[dict[str, Any]] = []
        for g in groups:
            fmt = g["format"]
            rows_g = g["rows"]
            mapped_doc_type = _map_doc_type(fmt) or doc_type
            title = _row_td_subj(rows_g[0]) if rows_g else ""
            if not title:
                title = _row_df_name(rows_g[0]) if rows_g else ""
            title2, content_text = _extract_text_from_rows(rows_g)
            if not title:
                title = title2
            if not title:
                title = f"TM_GRSNO {grsno}"
            if fmt_counts.get(fmt, 0) > 1:
                fmt_seen[fmt] = fmt_seen.get(fmt, 0) + 1
                title = f"{title} ({fmt_seen[fmt]})"

            docs.append(
                {
                    "key": g["key"],
                    "format": fmt,
                    "title": title,
                    "subject": _row_td_subj(rows_g[0]) if rows_g else "",
                    "content_text": content_text,
                    "doc_type": mapped_doc_type,
                    "count": len(rows_g),
                    "attachments": _build_attachments(rows_g),
                }
            )

        payload = {
            "ok": True,
            "grsno": grsno,
            "count": len(docs),
            "docs": docs,
        }
        if _debug_enabled():
            payload["meta"] = {
                "rows_total": len(rows),
                "formats": _format_stats(rows),
                "formats_all": raw_format_stats,
                "selected_formats": selected_formats,
            }
        return JsonResponse(payload, status=200)

    # 若多筆案件但未指定選擇清單 -> 強制要求使用者選擇
    selected_keys_raw = body.get("doc_keys") or body.get("doc_ids") or body.get("selected_keys")
    selected_keys: List[str] = []
    if isinstance(selected_keys_raw, (list, tuple)):
        selected_keys = [str(x).strip() for x in selected_keys_raw if str(x).strip()]
    elif selected_keys_raw:
        selected_keys = [str(selected_keys_raw).strip()]

    if not selected_keys and len(groups) > 1:
        return _json_error("multiple documents found; please select doc_keys", status=409)

    if selected_keys:
        selected_set = set(selected_keys)
        groups = [g for g in groups if g["key"] in selected_set]
        if not groups:
            return _json_error("no matched documents by doc_keys", status=400)

    fmt_counts: dict[str, int] = {}
    for g in groups:
        fmt_counts[g["format"]] = fmt_counts.get(g["format"], 0) + 1

    fmt_seen: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    created_count = 0
    errors: list[dict[str, Any]] = []

    for g in groups:
        fmt = g["format"]
        mapped_doc_type = _map_doc_type(fmt) or doc_type
        
        if not mapped_doc_type or mapped_doc_type not in valid_doc_types:
            errors.append({"format": fmt, "error": f"invalid doc_type: {mapped_doc_type}"})
            continue

        syb_title, content_text = _extract_text_from_rows(g["rows"])
        override_text = content_override.get(g["key"]) if isinstance(content_override, dict) else None
        if isinstance(override_text, str) and override_text.strip():
            content_text = override_text.strip()

        if not content_text:
            syb_title = syb_title or f"TM_GRSNO {grsno}"
            content_text = syb_title

        base_title = title_override or _row_td_subj(g["rows"][0]) or syb_title or f"TM_GRSNO {grsno}"
        if fmt:
            base_title = f"{fmt}: {base_title}"

        if fmt_counts.get(fmt, 0) > 1:
            fmt_seen[fmt] = fmt_seen.get(fmt, 0) + 1
            base_title = f"{base_title} ({fmt_seen[fmt]})"

        description = desc_override or f"轉入：{grsno}"

        sections = _draft_to_sections(mapped_doc_type, content_text)
        sections = _normalize_sections(sections)

        try:
            obj, created, final_title2, policy, status_msg = _save_template_with_conflict_policy_v2(
                title=base_title,
                doc_type=mapped_doc_type,
                description=description,
                sections=sections,
                doc_fields=doc_fields,
                meta=meta,
                tags=tags,
                scope=scope,
                user=dj_user,
                on_conflict=on_conflict,
                schema_ver=schema_ver,
                max_suffix_try=int(os.getenv("DOC_TPL_SUFFIX_MAX_TRY", "50")),
            )
        except Exception as e:
            errors.append({"format": fmt, "title": base_title, "error": str(e)})
            continue

        results.append(
            {
                "id": obj.id,
                "created": created,
                "title": final_title2,
                "scope": getattr(obj, "scope", scope),
                "on_conflict": policy,
                "status": status_msg,
                "format": fmt,
                "doc_type": mapped_doc_type,
                "doc_key": g["key"],
            }
        )
        if created:
            created_count += 1

    if not results:
        if _debug_enabled():
            return JsonResponse(
                {
                    "ok": False,
                    "error": "no valid documents to import",
                    "errors": errors,
                    "formats": raw_format_stats,
                },
                status=400,
            )
        return _json_error("no valid documents to import", status=400)

    payload = {
        "ok": True,
        "created": created_count,
        "created_count": created_count,
        "count": len(results),
        "skipped": len(errors),
        "results": results,
    }
    if _debug_enabled():
        payload["meta"] = {
            "rows_total": len(rows),
            "formats": _format_stats(rows),
            "formats_all": raw_format_stats,
            "selected_formats": selected_formats,
        }

    if len(results) == 1:
        payload.update(
            {
                "id": results[0]["id"],
                "title": results[0]["title"],
                "scope": results[0]["scope"],
                "on_conflict": results[0]["on_conflict"],
                "status": results[0]["status"],
            }
        )

    if _debug_enabled():
        payload.update(
            {
                "meta": {
                    "rows_total": len(rows),
                    "formats": _format_stats(rows),
                    "formats_all": raw_format_stats,
                    "selected_formats": selected_formats,
                    "charset": (os.getenv("SYBASE_CHARSET") or os.getenv("SYBASE_CHAR") or "").strip(),
                },
                "errors": errors,
            }
        )

    return JsonResponse(payload, status=201 if created_count > 0 else 200)









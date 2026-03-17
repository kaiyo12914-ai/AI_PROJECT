from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import json
import mimetypes
import os
import re
import socket
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.template import Engine, TemplateDoesNotExist
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.services.docService import docService
from webapps.doc.services.doc_db_router import DOC_PLANT_CODES, normalize_doc_plant
from webapps.doc.utils_login import get_login_user_idno, get_login_user_name
from webapps.doc.views_helpers import _extract_text_by_ext
from webapps.doc.views_pages import _calc_app_base_url


MAIN_DOC_FORMATS = {"簽呈", "呈", "令", "函", "便籤"}
MAIN_DOC_FORMAT_ALIASES = {"蝪賢?", "隞?", "靘輻惜"}
ATTACH_DOC_FORMATS = {"檔案", "瑼?"}


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _to_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x).strip()
        if not s:
            return default
        return int(float(s))
    except Exception:
        return default


def _is_main_doc_format(fmt: str) -> bool:
    t = (fmt or "").strip()
    if not t:
        return False
    if t in MAIN_DOC_FORMATS:
        return True
    if t in MAIN_DOC_FORMAT_ALIASES:
        return True
    if t in ATTACH_DOC_FORMATS:
        return False
    # Fallback for mixed-encoding values: classify by visible keywords.
    return any(k in t for k in ("簽", "呈", "令", "函", "便"))



def _is_known_doc_format(fmt: str) -> bool:
    t = (fmt or "").strip()
    if not t:
        return False
    return (
        t in MAIN_DOC_FORMATS
        or t in MAIN_DOC_FORMAT_ALIASES
        or t in ATTACH_DOC_FORMATS
    )


def _parse_trst_row(r: Any) -> Dict[str, Any]:
    tm_grsno = (_coerce_text(r[0] if len(r) > 0 else "") or "").strip()
    tm_date = _safe_str(r[1] if len(r) > 1 else "").strip()
    tm_psid = (_coerce_text(r[2] if len(r) > 2 else "") or "").strip()
    tm_name = (_coerce_text(r[3] if len(r) > 3 else "") or "").strip()
    tm_rstp = (_coerce_text(r[4] if len(r) > 4 else "") or "").strip()
    td_format = (_coerce_text(r[5] if len(r) > 5 else "") or "").strip()
    td_subj = (_coerce_text(r[6] if len(r) > 6 else "") or "").strip()
    td_path = (_coerce_text(r[7] if len(r) > 7 else "") or "").strip()
    df_name = (_coerce_text(r[8] if len(r) > 8 else "") or "").strip()
    data_len = _to_int(r[9] if len(r) > 9 else 0, 0)

    # Defensive mapping: if SQL column order drifts and TD_FORMAT is read from
    # PSID/RSTP slot, auto-correct to avoid dropping main-draft rows.
    if _is_known_doc_format(tm_psid) and not _is_known_doc_format(td_format):
        tm_psid, td_format = td_format, tm_psid
    elif _is_known_doc_format(tm_rstp) and not _is_known_doc_format(td_format):
        tm_rstp, td_format = td_format, tm_rstp

    return {
        "grsno": tm_grsno,
        "date": tm_date,
        "psid": tm_psid,
        "name": tm_name,
        "rstp": tm_rstp,
        "format": td_format,
        "subject": td_subj,
        "path": td_path,
        "df_name": df_name,
        "data_len": data_len,
    }
DOC_CATEGORY_ALL = "all"
DOC_CATEGORY_DRAFT_DOCS = "draft_docs"
DOC_CATEGORY_DRAFT_ATTACHMENTS = "draft_attachments"
DOC_CATEGORY_INCOMING_ALL = "incoming_all"
DOC_CATEGORY_ALLOWED = {
    DOC_CATEGORY_ALL,
    DOC_CATEGORY_DRAFT_DOCS,
    DOC_CATEGORY_DRAFT_ATTACHMENTS,
    DOC_CATEGORY_INCOMING_ALL,
}
SYBASE_QUERY_ALLOWED_USERS = {"H121356578", "F129195600"}


def _strip_ctrl(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[\x00-\x1f]+", "", s)


def _to_bool_setting(v: object, default: bool = True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if not s:
        return default
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _normalize_charset_name(cs: str) -> str:
    c = (cs or "").strip()
    if not c:
        return ""
    if c.upper() in ("BIG5", "BIG-5", "CP950"):
        return "cp950"
    return c


def _text_score(s: str) -> tuple[int, int, int]:
    t = _strip_ctrl(s)
    if not t:
        return (-10**9, -10**9, -10**9)
    repl = t.count("\ufffd")
    cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    return (cjk, -repl, len(t))


def _decode_u_escapes(s: str) -> str:
    t = (s or "")
    if "\\u" not in t:
        return t
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)


def _coerce_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (bytes, bytearray, memoryview)):
        b = x.tobytes() if isinstance(x, memoryview) else bytes(x)
        cs = (os.getenv("SYBASE_CHARSET") or os.getenv("SYBASE_CHAR") or "cp950").strip() or "cp950"
        return _decode_u_escapes(_decode_bytes_best_effort(b, cs))
    if isinstance(x, str):
        return _decode_u_escapes(_strip_ctrl(x))
    return _decode_u_escapes(_strip_ctrl(str(x)))


def _decode_bytes_best_effort(raw: bytes, preferred_charset: str = "") -> str:
    if not raw:
        return ""

    candidates: List[str] = []
    pref = _normalize_charset_name(preferred_charset)

    if raw.startswith(b"\xef\xbb\xbf"):
        candidates.append("utf-8-sig")
    if raw.startswith(b"\xff\xfe"):
        candidates.append("utf-16le")
    if raw.startswith(b"\xfe\xff"):
        candidates.append("utf-16be")
    if raw.count(0) >= max(2, len(raw) // 4):
        candidates.extend(["utf-16le", "utf-16be"])

    for enc in (pref, "cp950", "big5", "utf-8", "latin-1"):
        if enc and enc not in candidates:
            candidates.append(enc)

    best_text = ""
    best_score = (-10**9, -10**9, -10**9)
    for enc in candidates:
        try:
            decoded = raw.decode(enc)
        except Exception:
            try:
                decoded = raw.decode(enc, errors="replace")
            except Exception:
                continue

        score = _text_score(decoded)
        if score > best_score:
            best_score = score
            best_text = decoded
    return _strip_ctrl(best_text)


def _bytes_from_blob(x: Any) -> bytes:
    if x is None:
        return b""
    if isinstance(x, bytes):
        return x
    if isinstance(x, bytearray):
        return bytes(x)
    if isinstance(x, memoryview):
        return x.tobytes()
    # Handle Oracle LOB
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


def _guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename or "")
    return ctype or "application/octet-stream"


def _short_hash(text: str, size: int = 16) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    return hashlib.sha1(t.encode("utf-8", errors="ignore")).hexdigest()[:size]


def _lookup_item_id(kind: str, key: str, filename: str, grsno: str = "", subject: str = "") -> str:
    base = f"{kind}|{key}|{filename}|{grsno}|{subject}"
    return _short_hash(base, 20)


def _lookup_blob_hash(attach_key: str, filename: str, blob_size: int, mime: str) -> str:
    # Lightweight metadata hash (not file-content hash) for fast lookup responses.
    base = f"{attach_key}|{filename}|{int(blob_size or 0)}|{mime}"
    return _short_hash(base, 20)


def _sanitize_filename(name: str) -> str:
    s = _strip_ctrl(name or "").strip()
    if not s:
        return ""
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s


def _guess_extension_from_blob(data: bytes) -> str:
    if not data:
        return ".bin"
    if data.startswith(b"%PDF"):
        return ".pdf"
    if data.startswith(b"PK\x03\x04"):
        return ".docx"
    if data.startswith(b"{\\rtf"):
        return ".rtf"
    head = data[:64].lstrip()
    if head.startswith(b"<"):
        return ".txt"
    sample = _decode_bytes_best_effort(data[:2048], (os.getenv("SYBASE_CHARSET") or "cp950").strip())
    if sample and sum(1 for ch in sample if ch.isprintable()) >= max(8, int(len(sample) * 0.6)):
        return ".txt"
    return ".bin"


def _extract_grsno_from_df_path(df_path: str) -> str:
    s = (df_path or "").strip()
    if not s:
        return ""
    m = re.search(r"-(\d{6,})-", s)
    return m.group(1) if m else ""


def _resolve_df_filename_fallback(svc: docService, df_path: str, data: bytes) -> str:
    base = ""
    grsno = _extract_grsno_from_df_path(df_path)
    if grsno:
        try:
            rows = svc.search_trst_advanced(grsno=grsno, subject="", limit=500)
        except Exception:
            rows = []
        for r in rows or []:
            td_path = (_coerce_text(r[7] if len(r) > 7 else "") or "").strip()
            if td_path != df_path:
                continue
            df_name = (_coerce_text(r[8] if len(r) > 8 else "") or "").strip()
            if df_name:
                base = df_name
            else:
                td_format = (_coerce_text(r[5] if len(r) > 5 else "") or "").strip()
                td_subj = (_coerce_text(r[6] if len(r) > 6 else "") or "").strip()
                if td_format and td_subj:
                    base = f"{td_format}_{td_subj}"
                else:
                    base = td_subj or td_format
            break

    if not base:
        base = os.path.basename((df_path or "").strip()) or "attachment"

    base = _sanitize_filename(base) or "attachment"
    _, ext = os.path.splitext(base)
    if not ext:
        base = f"{base}{_guess_extension_from_blob(data)}"
    return base


def _set_attachment_headers(resp: HttpResponse, filename: str) -> None:
    name = (filename or "").strip() or "attachment.bin"
    name = os.path.basename(name)
    name = _strip_ctrl(name).replace('"', "").strip() or "attachment.bin"

    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not ascii_fallback:
        ascii_fallback = "attachment.bin"
    if "." not in ascii_fallback and "." in name:
        ext = os.path.splitext(name)[1]
        ext_ascii = re.sub(r"[^A-Za-z0-9.]+", "", ext)
        if ext_ascii:
            ascii_fallback += ext_ascii

    quoted = quote(name, safe="")
    resp["Content-Disposition"] = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quoted}'


def _b64url_encode(s: str) -> str:
    raw = (s or "").encode("utf-8", errors="ignore")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    pad = "=" * ((4 - (len(t) % 4)) % 4)
    try:
        return base64.urlsafe_b64decode((t + pad).encode("ascii")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _norm_filename(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _name_hash(name: str) -> str:
    n = _norm_filename(_decode_u_escapes(_coerce_text(name)).strip())
    if not n:
        return ""
    return hashlib.sha1(n.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _make_ef_attach_key(ef_id: str, ef_page: str = "", ef_name: str = "") -> str:
    ef = (ef_id or "").strip()
    page = (ef_page or "").strip()
    if not ef:
        return ""
    h = _name_hash(ef_name)
    if h:
        ef = f"{ef}|h{h}"
    if page and re.fullmatch(r"\d{1,6}", page):
        return f"EF:{ef}@{page}"
    return f"EF:{ef}"


def _make_df_attach_key(df_path: str) -> str:
    return f"DF:{_b64url_encode(df_path or '')}"


def _limit_rows_by_grsno(rows: Sequence[Any], limit_docs: int, is_trst: bool = False) -> List[Any]:
    if not rows:
        return []
    if limit_docs <= 0:
        return list(rows)
    out: List[Any] = []
    selected_keys = set()
    for r in rows:
        g = (_coerce_text(r[0] if len(r) > 0 else "") or "").strip()

        if is_trst and len(r) >= 6:
            fmt = (_coerce_text(r[5]) or "").strip()
            rstp = (_coerce_text(r[4]) or "").strip()
            g_key = f"{g}_{fmt}_{rstp}"
        else:
            g_key = g

        if not g_key:
            out.append(r)
            continue

        if g_key in selected_keys:
            out.append(r)
            continue

        if len(selected_keys) >= limit_docs:
            continue

        selected_keys.add(g_key)
        out.append(r)
    return out


def _parse_attach_key(attach_key: str) -> Tuple[str, str, str]:
    s = (attach_key or "").strip()
    if s.startswith("EF:"):
        body = s[3:].strip()
        if "@" in body:
            ef_id, page = body.rsplit("@", 1)
            p = page.strip()
            if not re.fullmatch(r"\d{1,6}", p or ""):
                p = ""
            return "EF", ef_id.strip(), p
        return "EF", body, ""
    if s.startswith("DF:"):
        return "DF", s[3:].strip(), ""
    return "", "", ""


def _parse_ip_token(raw: str) -> str:
    token = (raw or "").strip()
    if not token:
        return ""
    token = token.split(";", 1)[0].strip()
    if token.lower().startswith("for="):
        token = token[4:].strip()
    token = token.strip().strip('"').strip("'").strip()
    if token.startswith("[") and "]" in token:
        token = token[1 : token.find("]")]
    elif token.count(":") == 1 and "." in token:
        host, port = token.rsplit(":", 1)
        if port.isdigit():
            token = host
    token = token.strip().strip("[]").strip()
    if token.lower() == "unknown":
        return ""
    try:
        return str(ipaddress.ip_address(token))
    except Exception:
        return ""


def _collect_client_ip_candidates(request: HttpRequest) -> List[str]:
    trust_xff = _to_bool_setting(getattr(settings, "DOC_QUERY_TRUST_X_FORWARDED_FOR", True), default=True)
    candidates: List[str] = []

    if trust_xff:
        header_keys = (
            "HTTP_X_FORWARDED_FOR",
            "HTTP_X_REAL_IP",
            "HTTP_X_ORIGINAL_FOR",
            "HTTP_X_CLIENT_IP",
            "HTTP_CLIENT_IP",
            "HTTP_FORWARDED",
        )
        for key in header_keys:
            raw_val = (request.META.get(key) or "").strip()
            if not raw_val:
                continue
            for part in raw_val.split(","):
                ip = _parse_ip_token(part)
                if ip:
                    candidates.append(ip)

    remote_ip = _parse_ip_token((request.META.get("REMOTE_ADDR") or "").strip())
    if remote_ip:
        candidates.append(remote_ip)
    return candidates


def _pick_non_loopback_ip(candidates: Sequence[str]) -> str:
    for ip in candidates:
        try:
            obj = ipaddress.ip_address(ip)
        except Exception:
            continue
        if obj.is_loopback or obj.is_unspecified or obj.is_link_local:
            continue
        return ip
    return ""


def _get_server_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = str(s.getsockname()[0] or "").strip()
            if ip and not ip.startswith("127."):
                return ip
        finally:
            s.close()
    except Exception:
        pass

    try:
        host = socket.gethostname()
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except Exception:
        infos = []
    for info in infos:
        try:
            ip = str(info[4][0] or "").strip()
            obj = ipaddress.ip_address(ip)
        except Exception:
            continue
        if obj.is_loopback or obj.is_unspecified or obj.is_link_local:
            continue
        return ip
    return ""


def _get_client_ip_for_policy(request: HttpRequest) -> str:
    return _get_client_ip(request)


def _get_client_ip(request: HttpRequest) -> str:
    candidates = _collect_client_ip_candidates(request)
    lan = _get_server_lan_ip()

    real_candidates = []
    for ip in candidates:
        try:
            obj = ipaddress.ip_address(ip)
            if obj.is_loopback or obj.is_unspecified or obj.is_link_local:
                continue
            if lan and ip == lan:
                continue
            real_candidates.append(ip)
        except Exception:
            continue

    if real_candidates:
        return real_candidates[0]

    return lan or ""


def _collect_ip_debug_meta(request: HttpRequest) -> Dict[str, str]:
    keys = (
        "HTTP_X_FORWARDED_FOR",
        "HTTP_X_REAL_IP",
        "HTTP_X_ORIGINAL_FOR",
        "HTTP_X_CLIENT_IP",
        "HTTP_CLIENT_IP",
        "HTTP_FORWARDED",
        "REMOTE_ADDR",
    )
    out: Dict[str, str] = {}
    for k in keys:
        out[k] = (request.META.get(k) or "").strip()
    out["RESOLVED_CLIENT_IP"] = _get_client_ip(request)
    out["POLICY_CLIENT_IP"] = _get_client_ip_for_policy(request)
    return out


def _ip_in_allow_list(ip: str, allow_list: Sequence[str]) -> bool:
    cur = (ip or "").strip()
    if not cur:
        return False
    if "*" in [x.strip() for x in (allow_list or [])]:
        return True

    try:
        ip_obj = ipaddress.ip_address(cur)
    except Exception:
        return False

    for raw in (allow_list or []):
        item = (raw or "").strip()
        if not item:
            continue
        if item == cur:
            return True
        try:
            net = ipaddress.ip_network(item, strict=False)
        except Exception:
            continue
        if ip_obj in net:
            return True
    return False


def _deny_if_ip_not_allowed(request: HttpRequest, *, api: bool):
    ip = _get_client_ip_for_policy(request)
    allow_list = list(getattr(settings, "DOC_QUERY_ALLOWED_IPS", []) or [])
    if _ip_in_allow_list(ip, allow_list):
        return None

    if api:
        return JsonResponse(
            {"ok": False, "error": "ip not allowed", "ip": ip},
            status=403,
            json_dumps_params={"ensure_ascii": False},
        )
    return HttpResponseForbidden("Forbidden: IP not allowed")


def _is_authorized_query_ip(request: HttpRequest) -> bool:
    ip = _get_client_ip_for_policy(request)
    allow_list = list(getattr(settings, "DOC_QUERY_ALLOWED_IPS", []) or [])
    return _ip_in_allow_list(ip, allow_list)


def _deny_if_user_not_allowed(request: HttpRequest, *, api: bool):
    user_id = (get_login_user_idno(request) or "").strip().upper()
    if user_id in SYBASE_QUERY_ALLOWED_USERS:
        return None
    if api:
        return JsonResponse(
            {"ok": False, "error": "user not allowed", "login_user": user_id},
            status=403,
            json_dumps_params={"ensure_ascii": False},
        )
    return HttpResponseForbidden("Forbidden: user not allowed")


def _parse_search_args(request: HttpRequest) -> Tuple[str, str, str, int, str, Optional[int], str]:
    grsno = (_safe_str(request.GET.get("grsno")) or "").strip()
    subject = (_safe_str(request.GET.get("subject")) or "").strip()
    handler_name = (_safe_str(request.GET.get("handler_name")) or "").strip()
    limit_raw = (_safe_str(request.GET.get("limit")) or "").strip()
    plant_raw = (_safe_str(request.GET.get("plant")) or "").strip()
    days_ago_raw = (_safe_str(request.GET.get("days_ago")) or "").strip()
    doc_category = (_safe_str(request.GET.get("doc_category")) or "").strip().lower()

    if request.method == "POST":
        body = {}
        try:
            body = json.loads((request.body or b"{}").decode("utf-8") or "{}")
        except Exception:
            body = {}
        if not grsno:
            grsno = (_safe_str(body.get("grsno")) or "").strip()
        if not subject:
            subject = (_safe_str(body.get("subject")) or "").strip()
        if not handler_name:
            handler_name = (_safe_str(body.get("handler_name")) or "").strip()
        if not limit_raw:
            limit_raw = (_safe_str(body.get("limit")) or "").strip()
        if not plant_raw:
            plant_raw = (_safe_str(body.get("plant")) or "").strip()
        if not days_ago_raw:
            days_ago_val = body.get("days_ago")
            if days_ago_val is not None:
                days_ago_raw = str(days_ago_val).strip()
        if not doc_category:
            doc_category = (_safe_str(body.get("doc_category")) or "").strip().lower()

    try:
        limit = int(limit_raw or "50")
    except Exception:
        limit = 50
    if limit <= 0:
        limit = 50
    if limit > 500:
        limit = 500

    days_ago = None
    if days_ago_raw:
        try:
            da = int(days_ago_raw)
            if da > 0:
                days_ago = da
        except Exception:
            pass

    plant = normalize_doc_plant(plant_raw, default="MPC") if plant_raw else "MPC"
    if doc_category not in DOC_CATEGORY_ALLOWED:
        doc_category = DOC_CATEGORY_ALL
    return grsno, subject, handler_name, limit, plant, days_ago, doc_category


def _read_plant_arg(request: HttpRequest) -> str:
    from webapps.doc.utils_login import get_plant_arg
    return get_plant_arg(request)


def _build_doc_service(request: HttpRequest, *, plant: str = "") -> docService:
    return docService(
        plant=plant,
        login_user_id=(get_login_user_idno(request) or "").strip(),
        login_user_name=(get_login_user_name(request) or "").strip(),
    )


def _contains_non_ascii(s: str) -> bool:
    t = (s or "").strip()
    return bool(t and re.search(r"[^\x00-\x7f]", t))


def _looks_like_psid(s: str) -> bool:
    t = (s or "").strip()
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]{5,15}", t))


def _resolve_handler_psids(handler_name: str) -> List[str]:
    name = (handler_name or "").strip()
    if not name:
        return []

    if _looks_like_psid(name):
        return [name.upper()]

    try:
        from webapps.portal.oracle_emp import find_emp_ids_by_name

        ids = find_emp_ids_by_name(name, limit=50)
    except Exception:
        ids = []

    out = []
    seen = set()
    for x in ids or []:
        v = (str(x or "").strip() or "").upper()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _fetch_blob_by_attach_key(svc: docService, attach_key: str) -> Tuple[str, bytes]:
    kind, val, page = _parse_attach_key(attach_key)
    if not kind or not val:
        return "", b""

    if kind == "EF":
        ef_id = (val or "").strip()
        hint_hash = ""
        m = re.match(r"^(.*)\|h([0-9a-fA-F]{8,40})$", ef_id)
        if m:
            ef_id = (m.group(1) or "").strip()
            hint_hash = (m.group(2) or "").strip().lower()

        rows = svc.list_files_by_ef_id(ef_id, page if page else None)
        if not rows and page:
            rows = svc.list_files_by_ef_id(ef_id, None)

        row = None
        if hint_hash and rows:
            for rr in rows:
                nm = (_coerce_text(rr[0] if len(rr) > 0 else "") or "").strip()
                if _name_hash(nm) == hint_hash:
                    row = rr
                    break
        if row is None and rows:
            row = rows[0]
        if not row:
            return "", b""
        filename = (_coerce_text(row[0]) or "attachment.bin").strip() or "attachment.bin"
        data = _bytes_from_blob(row[1] if len(row) > 1 else None)
        return filename, data

    df_path = _b64url_decode(val) or val
    if not df_path:
        return "", b""
    row = svc.get_file_by_df_path(df_path)
    if not row:
        return "", b""
    raw_name = (_coerce_text(row[0]) or "").strip()
    data = _bytes_from_blob(row[1] if len(row) > 1 else None)
    if not data:
        return "", b""

    filename = _sanitize_filename(raw_name)
    if not filename:
        filename = _resolve_df_filename_fallback(svc, df_path, data)
    else:
        _, ext = os.path.splitext(filename)
        if not ext:
            filename = f"{filename}{_guess_extension_from_blob(data)}"
    return filename, data


def _is_attach_owned_by_user(svc: docService, login_user: str, attach_key: str) -> bool:
    kind, val, _page = _parse_attach_key(attach_key)
    if not kind or not val:
        return False

    if kind == "EF":
        ef_id = (val or "").strip()
        m = re.match(r"^(.*)\|h([0-9a-fA-F]{8,40})$", ef_id)
        if m:
            ef_id = (m.group(1) or "").strip()
        if ef_id and svc.check_ownership(login_user, "EF", ef_id):
            return True
        return bool(ef_id and svc.check_ownership(login_user, "DF", ef_id))

    df_path = _b64url_decode(val) or val
    if not df_path:
        return False
    return bool(svc.check_ownership(login_user, "DF", df_path))


def _blob_to_text(blob: bytes, filename: str) -> str:
    if not blob:
        return ""

    try:
        text = _extract_text_by_ext(io.BytesIO(blob), filename).strip()
        if text:
            return text
    except Exception:
        pass

    return _decode_bytes_best_effort(blob, (os.getenv("SYBASE_CHARSET") or "cp950").strip())


def _build_oracle_three_block_payload(
    svc: docService,
    *,
    grsno: str,
    subject: str,
    handler_name: str,
    limit: int,
    doc_category: str = DOC_CATEGORY_ALL,
    handler_warning: str = "",
) -> Dict[str, Any]:
    subject_needle = (subject or "").strip().casefold()
    handler_needle = (handler_name or "").strip().casefold()
    emp_name_cache: Dict[str, str] = {}

    def _resolve_emp_name(emp_id: str) -> str:
        key = (emp_id or "").strip()
        if not key:
            return ""
        if key in emp_name_cache:
            return emp_name_cache[key]
        name = ""
        try:
            from webapps.portal.oracle_emp import get_emp_name
            name = (get_emp_name(key) or "").strip()
        except Exception:
            name = ""
        emp_name_cache[key] = name
        return name

    def _match_subject(s: str) -> bool:
        if not subject_needle:
            return True
        return subject_needle in (s or "").casefold()

    def _match_handler(psid: str, name: str) -> bool:
        if not handler_needle:
            return True
        p = (psid or "").strip()
        n = (name or "").strip()
        if handler_needle in p.casefold():
            return True
        if n and handler_needle in n.casefold():
            return True
        resolved = _resolve_emp_name(p) if p else ""
        return bool(resolved and handler_needle in resolved.casefold())

    need_draft_docs = doc_category in (DOC_CATEGORY_ALL, DOC_CATEGORY_DRAFT_DOCS)
    need_draft_attach = doc_category in (DOC_CATEGORY_ALL, DOC_CATEGORY_DRAFT_ATTACHMENTS)
    need_incoming = doc_category in (DOC_CATEGORY_ALL, DOC_CATEGORY_INCOMING_ALL)

    draft_doc_rows = svc.query_oracle_draft_documents_by_grsno(grsno, subject=subject) if need_draft_docs else []
    draft_attach_rows = svc.query_oracle_draft_attachments_by_grsno(grsno, subject=subject) if need_draft_attach else []
    incoming_rows = svc.query_oracle_incoming_with_attachments_by_grsno(grsno, subject=subject) if need_incoming else []

    draft_docs: List[Dict[str, Any]] = []
    draft_attachments: List[Dict[str, Any]] = []
    incoming_docs: List[Dict[str, Any]] = []
    incoming_attachments: List[Dict[str, Any]] = []

    seen_draft_doc = set()
    seen_draft_attach = set()
    seen_incoming_attach = set()
    incoming_bucket: Dict[str, Dict[str, Any]] = {}

    for r in draft_doc_rows or []:
        parsed = _parse_trst_row(r)
        tm_grsno = parsed["grsno"]
        tm_date = parsed["date"]
        tm_psid = parsed["psid"]
        tm_name = parsed["name"]
        tm_rstp = parsed["rstp"]
        td_format = parsed["format"]
        td_subj = parsed["subject"]
        td_path = parsed["path"]
        df_name = parsed["df_name"]
        data_len = parsed["data_len"]
        if not _match_subject(td_subj):
            continue
        if not _match_handler(tm_psid, tm_name):
            continue
        row = {
            "grsno": tm_grsno,
            "date": tm_date,
            "psid": tm_psid,
            "sender": tm_name,
            "handler_name": (tm_name or _resolve_emp_name(tm_psid) or tm_psid),
            "flow_info": tm_rstp,
            "format": td_format,
            "subject": td_subj,
            "filename": (df_name or td_subj),
            "attach_key": (_make_df_attach_key(td_path) if td_path else ""),
            "has_blob": data_len > 0,
            "blob_size": data_len,
            "mime": _guess_content_type(df_name or td_subj or ""),
            "hash": _lookup_blob_hash((_make_df_attach_key(td_path) if td_path else ""), (df_name or td_subj or ""), data_len, _guess_content_type(df_name or td_subj or "")),
            "id": _lookup_item_id("DF", (_make_df_attach_key(td_path) if td_path else ""), (df_name or td_subj or ""), tm_grsno, td_subj),
            "has_attachment": bool(td_path and data_len > 0),
            "plant": svc.target.plant,
        }
        doc_key = f"{tm_grsno}::{tm_date}::{tm_rstp}::{td_format}::{td_subj}::{td_path}"
        if doc_key in seen_draft_doc:
            continue
        seen_draft_doc.add(doc_key)
        draft_docs.append(row)

    for r in draft_attach_rows or []:
        parsed = _parse_trst_row(r)
        tm_grsno = parsed["grsno"]
        tm_date = parsed["date"]
        tm_psid = parsed["psid"]
        tm_name = parsed["name"]
        tm_rstp = parsed["rstp"]
        td_format = parsed["format"]
        td_subj = parsed["subject"]
        td_path = parsed["path"]
        df_name = parsed["df_name"]
        data_len = parsed["data_len"]
        if not _match_subject(td_subj):
            continue
        if not _match_handler(tm_psid, tm_name):
            continue
        attach_key = _make_df_attach_key(td_path) if td_path else ""
        if not attach_key:
            continue
        row = {
            "grsno": tm_grsno,
            "date": tm_date,
            "psid": tm_psid,
            "sender": tm_name,
            "handler_name": (tm_name or _resolve_emp_name(tm_psid) or tm_psid),
            "flow_info": tm_rstp,
            "format": td_format,
            "subject": td_subj,
            "filename": (df_name or td_subj),
            "attach_key": attach_key,
            "has_blob": data_len > 0,
            "blob_size": data_len,
            "mime": _guess_content_type(df_name or td_subj or ""),
            "hash": _lookup_blob_hash(attach_key, (df_name or td_subj or ""), data_len, _guess_content_type(df_name or td_subj or "")),
            "id": _lookup_item_id("DF", attach_key, (df_name or td_subj or ""), tm_grsno, td_subj),
            "has_attachment": bool(attach_key and data_len > 0),
            "plant": svc.target.plant,
        }
        dedupe_key = f"{tm_grsno}::{attach_key}::{td_format}"
        if dedupe_key in seen_draft_attach:
            continue
        seen_draft_attach.add(dedupe_key)
        draft_attachments.append(row)

    for r in incoming_rows or []:
        im_grsno = (_coerce_text(r[0] if len(r) > 0 else "") or "").strip()
        im_psid = (_coerce_text(r[1] if len(r) > 1 else "") or "").strip()
        im_subj = (_coerce_text(r[2] if len(r) > 2 else "") or "").strip()
        ef_name = (_coerce_text(r[3] if len(r) > 3 else "") or "").strip()
        ef_id = (_coerce_text(r[4] if len(r) > 4 else "") or "").strip()
        ef_page = (_coerce_text(r[5] if len(r) > 5 else "") or "").strip()
        ef_size = _to_int(r[6] if len(r) > 6 and r[6] is not None else 0, 0)
        if not _match_subject(im_subj):
            continue
        if not _match_handler(im_psid, ""):
            continue
        bucket_key = f"{im_grsno}::{im_subj}"
        if bucket_key not in incoming_bucket:
            incoming_bucket[bucket_key] = {
                "grsno": im_grsno,
                "psid": im_psid,
                "handler_name": (_resolve_emp_name(im_psid) or im_psid),
                "subject": im_subj,
                "attach_count": 0,
                "has_attachment": False,
                "id": _lookup_item_id("IN_DOC", bucket_key, "", im_grsno, im_subj),
                "plant": svc.target.plant,
            }
            incoming_docs.append(incoming_bucket[bucket_key])
        attach_key = _make_ef_attach_key(ef_id, ef_page, ef_name)
        if not attach_key or attach_key in seen_incoming_attach:
            continue
        seen_incoming_attach.add(attach_key)
        incoming_bucket[bucket_key]["attach_count"] += 1
        incoming_bucket[bucket_key]["has_attachment"] = True
        mime = _guess_content_type(ef_name or ef_id or "")
        incoming_attachments.append(
            {
                "grsno": im_grsno,
                "subject": im_subj,
                "filename": ef_name or ef_id,
                "page": ef_page,
                "attach_key": attach_key,
                "mime": mime,
                "blob_size": ef_size,
                "hash": _lookup_blob_hash(attach_key, (ef_name or ef_id or ""), ef_size, mime),
                "id": _lookup_item_id("EF", attach_key, (ef_name or ef_id or ""), im_grsno, im_subj),
                "has_attachment": True,
                "plant": svc.target.plant,
            }
        )

    if limit > 0:
        draft_docs = draft_docs[:limit]
        draft_attachments = draft_attachments[: max(limit * 10, limit)]
        incoming_docs = incoming_docs[:limit]
        incoming_attachments = incoming_attachments[: max(limit * 10, limit)]

    incoming_grsno_set = {x.get("grsno", "") for x in incoming_docs if x.get("grsno")}
    trst_grsno_set = {x.get("grsno", "") for x in draft_docs if x.get("grsno")}
    case_incoming_only = sorted(incoming_grsno_set - trst_grsno_set, reverse=True)
    case_both = sorted(incoming_grsno_set & trst_grsno_set, reverse=True)
    case_trst_only = sorted(trst_grsno_set - incoming_grsno_set, reverse=True)

    payload = {
        "ok": True,
        "query": {
            "grsno": grsno,
            "subject": subject,
            "handler_name": handler_name,
            "plant": svc.target.plant,
            "limit": limit,
            "doc_category": doc_category,
            "subject_filter_mode": ("python" if subject_needle else "sql"),
            "subject_filter_mode_incoming": ("python" if subject_needle else "sql"),
            "subject_filter_mode_trst": ("python" if subject_needle else "sql"),
            "case_counts": {
                "incoming_only": len(case_incoming_only),
                "incoming_and_trst": len(case_both),
                "trst_only": len(case_trst_only),
            },
            "query_mode": "oracle_three_blocks",
            "lookup_mode": "metadata_only",
            "download_mode": "single_item_or_bundle",
        },
        "counts": {
            "incoming_docs": len(incoming_docs),
            "incoming_attachments": len(incoming_attachments),
            "draft_docs": len(draft_docs),
            "draft_attachments": len(draft_attachments),
        },
        "incoming_docs": incoming_docs,
        "incoming_attachments": incoming_attachments,
        "draft_docs": draft_docs,
        "draft_attachments": draft_attachments,
        **({"warning": handler_warning} if handler_warning else {}),
    }
    return payload


@require_node("doc")
def sybase_query_page(request: HttpRequest):
    denied = _deny_if_user_not_allowed(request, api=False)
    if denied is not None:
        return denied

    app_base_url = _calc_app_base_url(request)
    svc = _build_doc_service(request, plant=_read_plant_arg(request))
    authorized_ip = _is_authorized_query_ip(request)
    ip_debug = (_safe_str(request.GET.get("ipdebug")) or "").strip() == "1"
    context = {
        "app_base_url": app_base_url,
        "client_ip": _get_client_ip(request),
        "authorized_ip": authorized_ip,
        "restricted_to_self": (not authorized_ip),
        "plants": ["MPC", "202", "205", "209", "401"],
        "default_plant": svc.target.plant or "MPC",
        "ip_debug_meta": (_collect_ip_debug_meta(request) if ip_debug else {}),
    }

    try:
        return render(request, "doc/sybase_query.html", context)
    except TemplateDoesNotExist:
        from pathlib import Path

        tpl_path = Path(__file__).resolve().parent / "templates" / "doc" / "sybase_query.html"
        if tpl_path.exists():
            engine = Engine.get_default()
            template = engine.from_string(tpl_path.read_text(encoding="utf-8"))
            return HttpResponse(template.render(context, request))
        raise


@csrf_exempt
@require_node("doc", api=True)
def api_sybase_query_search(request: HttpRequest):
    denied = _deny_if_user_not_allowed(request, api=True)
    if denied is not None:
        return denied

    if request.method not in ("GET", "POST"):
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    grsno, subject, handler_name, limit, plant, days_ago, doc_category = _parse_search_args(request)
    if not grsno and not subject and not handler_name:
        return JsonResponse(
            {"ok": False, "error": "need handler_name or grsno or subject"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    authorized_ip = True
    restricted_to_self = False

    handler_psids = _resolve_handler_psids(handler_name) if handler_name else []
    handler_warning = ""
    handler_filter_disabled = False
    if handler_name and not handler_psids:
        handler_warning = "handler id not found; skip handler filter to avoid empty results"
        handler_filter_disabled = True

    use_python_subject_filter = bool(subject and _contains_non_ascii(subject))
    incoming_python_subject = use_python_subject_filter
    trst_python_subject = use_python_subject_filter
    subject_sql = "" if use_python_subject_filter else subject
    fetch_limit = limit
    if use_python_subject_filter:
        if grsno:
            fetch_limit = min(max(limit * 4, 400), 2000)
        else:
            fetch_limit = min(max(limit * 8, 800), 3000)
    elif handler_name and not grsno and not subject:
        fetch_limit = min(max(limit * 8, 800), 3000)

    svc = _build_doc_service(request, plant=plant)

    need_incoming = doc_category in (DOC_CATEGORY_ALL, DOC_CATEGORY_INCOMING_ALL)
    need_trst = doc_category in (DOC_CATEGORY_ALL, DOC_CATEGORY_DRAFT_DOCS, DOC_CATEGORY_DRAFT_ATTACHMENTS)
    need_draft_docs = doc_category in (DOC_CATEGORY_ALL, DOC_CATEGORY_DRAFT_DOCS)
    need_draft_attach = doc_category in (DOC_CATEGORY_ALL, DOC_CATEGORY_DRAFT_ATTACHMENTS)

    incoming_sql_psids = None if handler_name else handler_psids
    trst_sql_psids = None if handler_name else handler_psids
    try:
        incoming_rows = svc.search_incoming_advanced(
            grsno=grsno,
            subject=subject_sql,
            psids=incoming_sql_psids,
            limit=fetch_limit,
            days_ago=days_ago,
        ) if need_incoming else []
        trst_rows = svc.search_trst_advanced(
            grsno=grsno,
            subject=subject_sql,
            psids=trst_sql_psids,
            limit=fetch_limit,
            days_ago=days_ago,
        ) if need_trst else []
    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "doc query failed", "detail": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

    def _row_grsno(r: Any) -> str:
        return (_coerce_text(r[0] if len(r) > 0 else "") or "").strip()

    def _subject_filter_and_rehydrate(rows: Sequence[Any], *, subject_idx: int, fetch_by_grsno) -> List[Any]:
        needle = (subject or "").strip().casefold()
        if not needle:
            return list(rows or [])

        hits: List[Any] = []
        for r in (rows or []):
            s = (_coerce_text(r[subject_idx] if len(r) > subject_idx else "") or "").strip()
            if needle in s.casefold():
                hits.append(r)

        matched_grsnos: List[str] = []
        seen_g = set()
        for r in hits:
            g = _row_grsno(r)
            if not g or g in seen_g:
                continue
            seen_g.add(g)
            matched_grsnos.append(g)
        if limit > 0:
            matched_grsnos = matched_grsnos[:limit]

        out: List[Any] = []
        seen_rows = set()
        for g in matched_grsnos:
            try:
                fetched = fetch_by_grsno(g)
            except Exception:
                fetched = []
            for r in fetched or []:
                try:
                    k = tuple(r) if isinstance(r, (list, tuple)) else (str(r),)
                except Exception:
                    k = repr(r)
                if k in seen_rows:
                    continue
                seen_rows.add(k)
                out.append(r)
        return out

    if subject and (not use_python_subject_filter):
        if grsno:
            fetch_limit_fb = min(max(limit * 4, 400), 2000)
        else:
            fetch_limit_fb = min(max(limit * 8, 800), 3000)

        if need_incoming and not incoming_rows:
            incoming_python_subject = True
            try:
                incoming_rows = svc.search_incoming_advanced(
                    grsno=grsno,
                    subject="",
                    psids=incoming_sql_psids,
                    limit=fetch_limit_fb,
                )
            except Exception:
                incoming_rows = []

        if need_trst and not trst_rows:
            trst_python_subject = True
            try:
                trst_rows = svc.search_trst_advanced(
                    grsno=grsno,
                    subject="",
                    psids=trst_sql_psids,
                    limit=fetch_limit_fb,
                )
            except Exception:
                trst_rows = []

    if need_incoming and incoming_python_subject:
        incoming_rows = _subject_filter_and_rehydrate(
            incoming_rows or [],
            subject_idx=2,
            fetch_by_grsno=lambda g: svc.search_incoming_advanced(
                grsno=g,
                subject="",
                psids=incoming_sql_psids,
                limit=2000,
                days_ago=days_ago,
            ),
        )

    if need_trst and trst_python_subject:
        trst_rows = _subject_filter_and_rehydrate(
            trst_rows or [],
            subject_idx=6,
            fetch_by_grsno=lambda g: svc.search_trst_advanced(
                grsno=g,
                subject="",
                psids=trst_sql_psids,
                limit=2000,
                days_ago=days_ago,
            ),
        )

    emp_name_cache: Dict[str, str] = {}

    def _resolve_emp_name(emp_id: str) -> str:
        key = (emp_id or "").strip()
        if not key:
            return ""
        if key in emp_name_cache:
            return emp_name_cache[key]
        name = ""
        try:
            from webapps.portal.oracle_emp import get_emp_name
            name = (get_emp_name(key) or "").strip()
        except Exception:
            name = ""
        emp_name_cache[key] = name
        return name

    handler_psid_set = {str(x or "").strip().upper() for x in (handler_psids or []) if str(x or "").strip()}
    handler_needle = (handler_name or "").strip().casefold()

    def _incoming_match_handler(r: Any) -> bool:
        if handler_filter_disabled:
            return True
        if not handler_name:
            return True
        im_psid = (_coerce_text(r[1] if len(r) > 1 else "") or "").strip().upper()
        if handler_psid_set and im_psid in handler_psid_set:
            return True
        if not handler_needle:
            return False
        if im_psid and handler_needle in im_psid.casefold():
            return True
        if im_psid:
            resolved = _resolve_emp_name(im_psid)
            if resolved and handler_needle in resolved.casefold():
                return True
        return False

    def _trst_match_handler(r: Any) -> bool:
        if handler_filter_disabled:
            return True
        if not handler_name:
            return True
        tm_psid = (_coerce_text(r[2] if len(r) > 2 else "") or "").strip().upper()
        tm_name = (_coerce_text(r[3] if len(r) > 3 else "") or "").strip()
        if handler_psid_set and tm_psid in handler_psid_set:
            return True
        if not handler_needle:
            return False
        if tm_name and handler_needle in tm_name.casefold():
            return True
        if tm_psid:
            resolved = _resolve_emp_name(tm_psid)
            if resolved and handler_needle in resolved.casefold():
                return True
        return False

    if handler_name and not handler_filter_disabled:
        fallback_limit = min(max(fetch_limit * 4, 400), 2000) if (grsno or subject) else min(max(fetch_limit * 8, 800), 3000)

        matched_incoming = [r for r in (incoming_rows or []) if _incoming_match_handler(r)] if need_incoming else []
        if need_incoming and not matched_incoming:
            try:
                incoming_rows_fb = svc.search_incoming_advanced(grsno=grsno, subject="" if incoming_python_subject else subject_sql, psids=None, limit=fallback_limit, days_ago=days_ago)
            except Exception: incoming_rows_fb = []
            if incoming_python_subject:
                incoming_rows_fb = _subject_filter_and_rehydrate(incoming_rows_fb or [], subject_idx=2, fetch_by_grsno=lambda g: svc.search_incoming_advanced(grsno=g, subject="", psids=None, limit=2000, days_ago=days_ago))
            matched_incoming = [r for r in (incoming_rows_fb or []) if _incoming_match_handler(r)]
        incoming_rows = _limit_rows_by_grsno(matched_incoming, limit, is_trst=False) if need_incoming else []

        matched_trst = [r for r in (trst_rows or []) if _trst_match_handler(r)] if need_trst else []
        if need_trst and not matched_trst:
            try:
                trst_rows_fb = svc.search_trst_advanced(grsno=grsno, subject="" if trst_python_subject else subject_sql, psids=None, limit=fallback_limit, days_ago=days_ago)
            except Exception: trst_rows_fb = []
            if trst_python_subject:
                trst_rows_fb = _subject_filter_and_rehydrate(trst_rows_fb or [], subject_idx=6, fetch_by_grsno=lambda g: svc.search_trst_advanced(grsno=g, subject="", psids=None, limit=2000, days_ago=days_ago))
            matched_trst = [r for r in (trst_rows_fb or []) if _trst_match_handler(r)]
        trst_rows = _limit_rows_by_grsno(matched_trst, limit, is_trst=True) if need_trst else []
    else:
        incoming_rows = _limit_rows_by_grsno(incoming_rows or [], limit, is_trst=False) if need_incoming else []
        trst_rows = _limit_rows_by_grsno(trst_rows or [], limit, is_trst=True) if need_trst else []

    def _row_key(r: Any) -> tuple:
        if isinstance(r, tuple): return r
        if isinstance(r, list): return tuple(r)
        return (str(r),)

    def _dedupe_rows(rows: Sequence[Any]) -> List[Any]:
        out: List[Any] = []
        seen = set()
        for r in (rows or []):
            k = _row_key(r)
            if k in seen: continue
            seen.add(k)
            out.append(r)
        return out

    def _group_rows_by_grsno(rows: Sequence[Any]) -> Dict[str, List[Any]]:
        out: Dict[str, List[Any]] = {}
        for r in (rows or []):
            g = _row_grsno(r)
            if not g: continue
            out.setdefault(g, []).append(r)
        return out

    incoming_rows = _dedupe_rows(incoming_rows or []) if need_incoming else []
    trst_rows = _dedupe_rows(trst_rows or []) if need_trst else []

    incoming_by_grsno = _group_rows_by_grsno(incoming_rows)
    trst_by_grsno = _group_rows_by_grsno(trst_rows)

    merged_grsnos: List[str] = []
    for g in list(incoming_by_grsno.keys()) + list(trst_by_grsno.keys()):
        if not g or g in merged_grsnos: continue
        merged_grsnos.append(g)
    if limit > 0: merged_grsnos = merged_grsnos[:limit]

    for g in merged_grsnos:
        if need_incoming and g not in incoming_by_grsno:
            try:
                rows_fb = svc.search_incoming_advanced(grsno=g, subject="", psids=incoming_sql_psids, limit=2000, days_ago=days_ago)
            except Exception: rows_fb = []
            rows_fb = [r for r in (rows_fb or []) if _incoming_match_handler(r)]
            rows_fb = _dedupe_rows(rows_fb)
            if rows_fb: incoming_by_grsno[g] = rows_fb

        if need_trst and g not in trst_by_grsno:
            try:
                rows_fb = svc.search_trst_advanced(grsno=g, subject="", psids=trst_sql_psids, limit=2000, days_ago=days_ago)
            except Exception: rows_fb = []
            rows_fb = [r for r in (rows_fb or []) if _trst_match_handler(r)]
            rows_fb = _dedupe_rows(rows_fb)
            if rows_fb: trst_by_grsno[g] = rows_fb

    incoming_rows = []
    trst_rows = []
    for g in merged_grsnos:
        incoming_rows.extend(incoming_by_grsno.get(g, []))
        trst_rows.extend(trst_by_grsno.get(g, []))
    incoming_rows = _dedupe_rows(incoming_rows)
    trst_rows = _dedupe_rows(trst_rows)

    incoming_grsno_set = {g for g in incoming_by_grsno.keys() if g in merged_grsnos}
    trst_grsno_set = {g for g in trst_by_grsno.keys() if g in merged_grsnos}
    case_incoming_only = sorted(incoming_grsno_set - trst_grsno_set, reverse=True)
    case_both = sorted(incoming_grsno_set & trst_grsno_set, reverse=True)
    case_trst_only = sorted(trst_grsno_set - incoming_grsno_set, reverse=True)

    # --- 區塊 3: 來文清單及附件 (Incoming Docs & Attachments) ---
    incoming_docs: List[Dict[str, Any]] = []
    incoming_attachments: List[Dict[str, Any]] = []
    incoming_bucket: Dict[str, Dict[str, Any]] = {}
    seen_incoming_attach = set()

    for r in incoming_rows or []:
        im_grsno = (_coerce_text(r[0] if len(r) > 0 else "") or "").strip()
        im_psid = (_coerce_text(r[1] if len(r) > 1 else "") or "").strip()
        td_subj = (_coerce_text(r[2] if len(r) > 2 else "") or "").strip()
        ef_id = (_coerce_text(r[3] if len(r) > 3 else "") or "").strip()
        ef_name = (_coerce_text(r[4] if len(r) > 4 else "") or "").strip()
        ef_page = (_coerce_text(r[5] if len(r) > 5 else "") or "").strip()

        key = f"{im_grsno}::{td_subj}"
        if key not in incoming_bucket:
            incoming_bucket[key] = {
                "grsno": im_grsno,
                "psid": im_psid,
                "handler_name": (_resolve_emp_name(im_psid) or im_psid),
                "subject": td_subj,
                "attach_count": 0,
                "has_attachment": False,
                "id": _lookup_item_id("IN_DOC", key, "", im_grsno, td_subj),
                "plant": svc.target.plant,
            }
            incoming_docs.append(incoming_bucket[key])

        attach_key = _make_ef_attach_key(ef_id, ef_page, ef_name)
        if attach_key and attach_key not in seen_incoming_attach:
            seen_incoming_attach.add(attach_key)
            incoming_bucket[key]["attach_count"] += 1
            incoming_bucket[key]["has_attachment"] = True
            mime = _guess_content_type(ef_name or ef_id or "")
            incoming_attachments.append({
                "grsno": im_grsno,
                "subject": td_subj,
                "filename": ef_name or ef_id,
                "page": ef_page,
                "attach_key": attach_key,
                "mime": mime,
                "blob_size": 0,
                "hash": _lookup_blob_hash(attach_key, (ef_name or ef_id or ""), 0, mime),
                "id": _lookup_item_id("EF", attach_key, (ef_name or ef_id or ""), im_grsno, td_subj),
                "has_attachment": True,
                "plant": svc.target.plant,
            })

    # --- 區塊 1 & 2: 呈文清單 (Draft Docs) 與 呈文附件 (Draft Attachments) ---
    draft_docs: List[Dict[str, Any]] = []
    draft_attachments: List[Dict[str, Any]] = []
    seen_draft_doc = set()
    seen_draft_attach = set()

    for r in trst_rows or []:
        parsed = _parse_trst_row(r)
        tm_grsno = parsed["grsno"]
        tm_date = parsed["date"]
        tm_psid = parsed["psid"]
        tm_name = parsed["name"]
        tm_rstp = parsed["rstp"]
        td_format = parsed["format"]
        td_subj = parsed["subject"]
        td_path = parsed["path"]
        df_name = parsed["df_name"]
        data_len = parsed["data_len"]
        has_blob = data_len > 0

        attach_key = _make_df_attach_key(td_path) if td_path else ""
        filename = df_name or (td_subj if td_subj else "")

        row = {
            "grsno": tm_grsno,
            "date": tm_date,
            "psid": tm_psid,
            "sender": tm_name,
            "handler_name": (tm_name or _resolve_emp_name(tm_psid) or tm_psid),
            "flow_info": tm_rstp,
            "format": td_format,
            "subject": td_subj,
            "filename": filename,
            "attach_key": attach_key,
            "has_blob": has_blob,
            "blob_size": data_len,
            "mime": _guess_content_type(filename or td_subj or ""),
            "hash": _lookup_blob_hash(attach_key, (filename or td_subj or ""), data_len, _guess_content_type(filename or td_subj or "")),
            "id": _lookup_item_id("DF", attach_key, (filename or td_subj or ""), tm_grsno, td_subj),
            "has_attachment": bool(attach_key and has_blob),
            "plant": svc.target.plant,
        }

        if _is_main_doc_format(td_format) and need_draft_docs:
            # 區塊 1: 呈文清單 (Draft Documents)
            # 優化去重：包含流程編號 (tm_rstp) 避免同一案件不同流程階段的呈文被合併
            doc_key = f"DOC::{tm_grsno}::{tm_date}::{tm_rstp}::{td_format}::{td_subj}"
            if doc_key not in seen_draft_doc:
                seen_draft_doc.add(doc_key)
                draft_docs.append(row)
        elif need_draft_attach:
            # 區塊 2: 呈文附件清單 (Draft Attachments)
            # 優化去重：依據實體路徑 (attach_key) 區分，確保不同版次的參考附件均呈現
            attach_dedup_key = f"ATT::{tm_grsno}::{attach_key}::{td_format}"
            if attach_key and attach_dedup_key not in seen_draft_attach:
                seen_draft_attach.add(attach_dedup_key)
                draft_attachments.append(row)

    return JsonResponse({
        "ok": True,
        "query": {
            "grsno": grsno, "subject": subject, "handler_name": handler_name,
            "plant": svc.target.plant, "limit": limit, "doc_category": doc_category,
            "lookup_mode": "metadata_only",
            "download_mode": "single_item_or_bundle",
            "case_counts": {
                "incoming_only": len(case_incoming_only),
                "incoming_and_trst": len(case_both),
                "trst_only": len(case_trst_only),
            },
        },
        "counts": {
            "incoming_docs": len(incoming_docs),
            "incoming_attachments": len(incoming_attachments),
            "draft_docs": len(draft_docs),
            "draft_attachments": len(draft_attachments),
        },
        "incoming_docs": incoming_docs,
        "incoming_attachments": incoming_attachments,
        "draft_docs": draft_docs,
        "draft_attachments": draft_attachments,
        **({"warning": handler_warning} if handler_warning else {}),
    }, status=200, json_dumps_params={"ensure_ascii": False})


def _read_attach_key(request: HttpRequest) -> str:
    key = (_safe_str(request.GET.get("attach_key")) or "").strip()
    if key: return key
    if request.method == "POST":
        try: body = json.loads((request.body or b"{}").decode("utf-8") or "{}")
        except Exception: body = {}
        key = (_safe_str(body.get("attach_key")) or "").strip()
    return key


@csrf_exempt
@require_node("doc", api=True)
def api_sybase_query_file(request: HttpRequest):
    denied = _deny_if_user_not_allowed(request, api=True)
    if denied is not None:
        return denied

    if request.method not in ("GET", "POST"): return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    attach_key = _read_attach_key(request)
    if not attach_key: return JsonResponse({"ok": False, "error": "empty attach_key"}, status=400)
    svc = _build_doc_service(request, plant=_read_plant_arg(request))
    filename, data = _fetch_blob_by_attach_key(svc, attach_key)
    if not filename or not data: return JsonResponse({"ok": False, "error": "not found"}, status=404)
    resp = HttpResponse(data, content_type=_guess_content_type(filename))
    _set_attachment_headers(resp, filename)
    return resp


@csrf_exempt
@require_node("doc", api=True)
def api_sybase_query_preview(request: HttpRequest):
    denied = _deny_if_user_not_allowed(request, api=True)
    if denied is not None:
        return denied

    if request.method not in ("GET", "POST"): return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    attach_key = _read_attach_key(request)
    if not attach_key: return JsonResponse({"ok": False, "error": "empty attach_key"}, status=400)
    svc = _build_doc_service(request, plant=_read_plant_arg(request))
    filename, data = _fetch_blob_by_attach_key(svc, attach_key)
    if not filename or not data: return JsonResponse({"ok": False, "error": "not found"}, status=404)
    text = _blob_to_text(data, filename).strip()
    if len(text) > 20000: text = text[:20000] + "\n...(truncated)"
    return JsonResponse({
        "ok": True, "attach_key": attach_key, "filename": filename,
        "size": len(data), "plant": svc.target.plant,
        "preview_text": text, "is_binary": not bool(text.strip()),
    }, status=200, json_dumps_params={"ensure_ascii": False})

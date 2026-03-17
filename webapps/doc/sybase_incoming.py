# webapps/doc/sybase_incoming.py (updated)

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Sequence
from urllib.parse import quote

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.utils_login import get_login_user_idno, get_login_user_name

# Keep docService import direct; it already handles DB factory fallback.
from webapps.doc.services.docService import docService




# ============================================================
# helpers
# ============================================================

def _strip_ctrl(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[\x00-\x1f]+", "", s)


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


def _coerce_text(x: Any) -> str:
    """
    Normalize to text with Sybase-aware decoding for VARBINARY fields.
    """
    if x is None:
        return ""
    if isinstance(x, (bytes, bytearray, memoryview)):
        b = x.tobytes() if isinstance(x, memoryview) else bytes(x)
        cs = (os.getenv("SYBASE_CHARSET") or os.getenv("SYBASE_CHAR") or "cp950").strip() or "cp950"
        return _decode_bytes_best_effort(b, cs)
    if isinstance(x, str):
        return _strip_ctrl(x)
    return _strip_ctrl(str(x))


def _decode_u_escapes(s: str) -> str:
    t = (s or "")
    if "\\u" not in t:
        return t
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)

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
        except Exception:
            pass
    try:
        return bytes(x)
    except Exception:
        return b""


def _set_attachment_headers(resp: HttpResponse, filename: str) -> None:
    """
    Set RFC5987-compatible attachment headers with safe fallback.
    """
    name = (filename or "").strip() or "attachment.bin"
    name = os.path.basename(name)
    name = _strip_ctrl(name).replace('"', "").strip() or "attachment.bin"

    # Preserve English names in legacy clients that only parse filename=...
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not ascii_fallback:
        ascii_fallback = "attachment.bin"
    if "." not in ascii_fallback and "." in name:
        ext = os.path.splitext(name)[1]
        ext_ascii = re.sub(r"[^A-Za-z0-9.]+", "", ext)
        if ext_ascii:
            ascii_fallback = ascii_fallback + ext_ascii

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


def _pick_attachment_source(tm_rstp: str, td_format: str, ef_id: str, td_path: str) -> str:
    """
    Matches raw-query intent:
      CASE WHEN TD_FORMAT not in ('PAPER', 'E-SWAP(PAPER)') AND TM_RSTP NOT IN ('LETTER', 'DRAFT')
           THEN EF
           ELSE DF
    """
    ef_id = (ef_id or "").strip()
    td_path = (td_path or "").strip()

    # Keep this helper permissive; incoming flow should prefer EF when EF_ID exists.
    use_ef = bool(ef_id)
    if use_ef:
        return "EF"
    if td_path:
        return "DF"
    return "EF" if ef_id else "DF"


def _make_attach_key(kind: str, ef_id: str, td_path: str, ef_page: str = "", ef_name: str = "") -> str:
    if kind == "EF":
        base = re.sub(r"[\x00-\x1f]+", "", (ef_id or "").strip())
        if len(base) > 110:
            base = base[:110]
        h = _name_hash(ef_name)
        if h:
            base = f"{base}|h{h}"
        page = (ef_page or "").strip()
        if not re.fullmatch(r"\d{1,6}", page or ""):
            page = ""
        if not base:
            return ""
        return f"EF:{base}@{page}" if page else f"EF:{base}"
    return f"DF:{_b64url_encode(td_path or '')}"


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
    # Backward compatibility: no prefix means EF_ID.
    return "EF", s, ""


def _norm_filename(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _name_hash(name: str) -> str:
    n = _norm_filename(_decode_u_escapes(_coerce_text(name)).strip())
    if not n:
        return ""
    return hashlib.sha1(n.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _strip_file_ext(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return ""
    base, ext = os.path.splitext(s)
    if ext and len(ext) <= 10:
        return base
    return s


def _dedupe_safe_filename(
    existing_norms: set,
    base_name: str,
    source: str,
    counter: Dict[Tuple[str, str], int],
) -> str:
    """
    De-duplicate within the same source + normalized filename by appending (2), (3), ...
    """
    base = (base_name or "attachment").strip() or "attachment"
    norm = _norm_filename(base)
    k = (source, norm)

    if k not in existing_norms:
        existing_norms.add(k)
        counter[k] = 1
        return base

    n = int(counter.get(k, 1)) + 1
    counter[k] = n

    m = re.match(r"^(.*?)(\.[A-Za-z0-9]{1,10})$", base)
    if m:
        stem, ext = m.group(1), m.group(2)
        return f"{stem}({n}){ext}"
    return f"{base}({n})"


def _pick_ef_row(rows: Sequence[Any], hint_name: str, hint_hash: str = "") -> Any:
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    hh = (hint_hash or "").strip().lower()
    if hh:
        for r in rows:
            name = _decode_u_escapes(_coerce_text(_row_get(r, 0, "EF_NAME")).strip())
            if _name_hash(name) == hh:
                return r

    hint_norm = _norm_filename(_decode_u_escapes(_coerce_text(hint_name)).strip())
    if hint_norm:
        for r in rows:
            name = _decode_u_escapes(_coerce_text(_row_get(r, 0, "EF_NAME")).strip())
            if _norm_filename(name) == hint_norm:
                return r
    return rows[0]


def _guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename or "")
    return ctype or "application/octet-stream"


def _get_tm_grsno(request: HttpRequest) -> str:
    """
    Get incoming document number from request.
    - GET: im_grsno / tm_grsno / grsno
    - POST JSON: {"im_grsno": "..."} or {"tm_grsno": "..."} or {"grsno": "..."}
    """
    # GET first (for your current JS)
    tm_grsno = (_coerce_text(request.GET.get("im_grsno")) or "").strip()
    if not tm_grsno:
        tm_grsno = (_coerce_text(request.GET.get("tm_grsno")) or "").strip()
    if not tm_grsno:
        tm_grsno = (_coerce_text(request.GET.get("grsno")) or "").strip()
    if tm_grsno:
        return tm_grsno

    # POST JSON
    try:
        payload = json.loads((request.body or b"").decode("utf-8") or "{}")
    except Exception:
        payload = {}

    tm = (_coerce_text(payload.get("im_grsno")) or "").strip()
    if not tm:
        tm = (_coerce_text(payload.get("tm_grsno")) or "").strip()
    if tm:
        return tm
    return (_coerce_text(payload.get("grsno")) or "").strip()


def _row_get(row: Any, idx: int, *keys: str) -> Any:
    try:
        if hasattr(row, "_mapping"):
            m = row._mapping
            for key in keys:
                if key in m:
                    return m.get(key)
                k_up = key.upper()
                if k_up in m:
                    return m.get(k_up)
                k_lo = key.lower()
                if k_lo in m:
                    return m.get(k_lo)
    except Exception:
        pass
    try:
        return row[idx]
    except Exception:
        return None


def _build_items_from_rows(rows: List[Tuple]) -> List[Dict[str, Any]]:
    """
    Convert query rows into grouped item payload with attachments.
    """
    bucket: Dict[str, Dict[str, Any]] = {}

    for r in rows or []:
        tm_grsno_v = ""
        tm_psid_v = ""
        td_subj = ""
        ef_id = ""
        ef_name = ""
        ef_page = ""

        # SQL_1 full shape:
        #   0: IM/EM_GRSNO
        #   1: IM/EM_PSID
        #   2: TD_SUBJ
        #   3: EF_ID
        #   4: EF_NAME
        #   5: EF_DATA
        #   6: EF_DATA_LEN
        #   7: EM_SUBJ_LEN
        #   8: IM_SUBJ_LEN
        #   9: EF_NAME_LEN
        #  10: EF_PAGE
        if len(r) >= 11:
            tm_grsno_v = _coerce_text(_row_get(r, 0, "IM_GRSNO", "EM_GRSNO", "TM_GRSNO")).strip()
            tm_psid_v = _coerce_text(_row_get(r, 1, "IM_PSID", "EM_PSID", "TM_PSID")).strip()
            td_subj = _decode_u_escapes(_coerce_text(_row_get(r, 2, "TD_SUBJ")).strip())
            ef_id = _coerce_text(_row_get(r, 3, "EF_ID")).strip()
            ef_name = _decode_u_escapes(_coerce_text(_row_get(r, 4, "EF_NAME")).strip())
            ef_page = _coerce_text(_row_get(r, 10, "EF_PAGE")).strip()
        # Slim incoming shape:
        #   0: EM_GRSNO
        #   1: EM_PSID
        #   2: TD_SUBJ
        #   3: EF_ID
        #   4: EF_NAME
        #   5: EF_PAGE
        elif len(r) >= 6:
            tm_grsno_v = _coerce_text(_row_get(r, 0, "IM_GRSNO", "EM_GRSNO", "TM_GRSNO")).strip()
            tm_psid_v = _coerce_text(_row_get(r, 1, "IM_PSID", "EM_PSID", "TM_PSID")).strip()
            td_subj = _decode_u_escapes(_coerce_text(_row_get(r, 2, "TD_SUBJ")).strip())
            ef_id = _coerce_text(_row_get(r, 3, "EF_ID")).strip()
            ef_name = _decode_u_escapes(_coerce_text(_row_get(r, 4, "EF_NAME")).strip())
            ef_page = _coerce_text(_row_get(r, 5, "EF_PAGE")).strip()
        # Legacy shape (old SQL without EM_PSID):
        #   0: EM_GRSNO
        #   1: TD_SUBJ
        #   2: EF_ID
        #   3: EF_NAME
        #   4: EF_PAGE
        elif len(r) >= 5:
            tm_grsno_v = _coerce_text(_row_get(r, 0, "IM_GRSNO", "EM_GRSNO", "TM_GRSNO")).strip()
            td_subj = _decode_u_escapes(_coerce_text(_row_get(r, 1, "TD_SUBJ")).strip())
            ef_id = _coerce_text(_row_get(r, 2, "EF_ID")).strip()
            ef_name = _decode_u_escapes(_coerce_text(_row_get(r, 3, "EF_NAME")).strip())
            ef_page = _coerce_text(_row_get(r, 4, "EF_PAGE")).strip()
        elif len(r) >= 4:
            tm_grsno_v = _coerce_text(_row_get(r, 0, "IM_GRSNO", "EM_GRSNO", "TM_GRSNO")).strip()
            td_subj = _decode_u_escapes(_coerce_text(_row_get(r, 1, "TD_SUBJ")).strip())
            ef_id = _coerce_text(_row_get(r, 2, "EF_ID")).strip()
            ef_name = _decode_u_escapes(_coerce_text(_row_get(r, 3, "EF_NAME")).strip())

        # Guard malformed page values (e.g. binary blob by wrong column mapping)
        if ef_page and not re.fullmatch(r"\d{1,6}", ef_page):
            ef_page = ""

        if not td_subj and ef_name:
            td_subj = _strip_file_ext(ef_name)

        key_head = tm_grsno_v or tm_psid_v
        if not key_head:
            continue

        # Same grsno may contain multiple incoming subjects (INT behavior).
        # Group by (grsno/psid, subject) so distinct docs are not merged.
        key = f"{key_head}::{td_subj}" if td_subj else key_head
        if key not in bucket:
            bucket[key] = {
                "grsno": tm_grsno_v,
                "im_grsno": tm_grsno_v,
                "tm_grsno": tm_grsno_v,
                "im_psid": tm_psid_v,
                "tm_psid": tm_psid_v,
                "td_subj": td_subj,
                "subject": td_subj,
                "attachments": [],
                "_seen_attach": set(),
                "_seen_name": set(),
                "_name_counter": {},
            }
        else:
            if not bucket[key].get("td_subj") and td_subj:
                bucket[key]["td_subj"] = td_subj
                bucket[key]["subject"] = td_subj

        if not ef_id:
            continue

        source = "EF"
        attach_key = _make_attach_key(source, ef_id, "", ef_page, ef_name)
        if not attach_key:
            continue
        attach_name_norm = _norm_filename(ef_name or ef_id or "")
        attach_token = f"{attach_key}::{attach_name_norm}" if attach_name_norm else attach_key
        if attach_token in bucket[key]["_seen_attach"]:
            continue
        bucket[key]["_seen_attach"].add(attach_token)

        # Incoming list should show EF attachment names only; never reuse subject as pseudo filename.
        filename = ef_name or ef_id or "attachment.bin"

        if not bucket[key].get("td_subj") and filename:
            bucket[key]["td_subj"] = filename
            bucket[key]["subject"] = filename

        filename = _dedupe_safe_filename(
            bucket[key]["_seen_name"],
            filename,
            source,
            bucket[key]["_name_counter"],
        )

        bucket[key]["attachments"].append(
            {
                "attach_key": attach_key,
                "filename": filename,
                "raw_filename": ef_name or filename,
                "td_format": "",
                "source": source,
                "page": ef_page,
            }
        )

    out: List[Dict[str, Any]] = []
    for v in bucket.values():
        v.pop("_seen_attach", None)
        v.pop("_seen_name", None)
        v.pop("_name_counter", None)
        out.append(v)

    out.sort(
        key=lambda x: (
            x.get("grsno") or x.get("im_grsno") or x.get("tm_grsno") or "",
            x.get("td_subj", ""),
        ),
        reverse=True,
    )
    return out

# ============================================================
# API
# ============================================================

@csrf_exempt
@require_node("doc", api=True)
@csrf_exempt
@require_node("doc", api=True)
def incoming_lookup(request: HttpRequest):
    """
    Incoming lookup API (GET / POST).
    GET:
      /doc/incoming_lookup/?tm_grsno=1150001261
    POST JSON:
      { "tm_grsno": "1150001261" }
    POST form:
      tm_grsno=1150001261

    Response:
      { ok, items: [ {tm_grsno, tm_psid, td_subj, attachments:[...]} ] }
    """
    if request.method not in ("GET", "POST"):
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405, json_dumps_params={"ensure_ascii": False})

    # -------------------------
    # 1) Validate login user context.
    # -------------------------
    login_user = (get_login_user_idno(request) or "").strip()
    login_user_name = (get_login_user_name(request) or "").strip()
    if not login_user:
        # Keep the response explicit for troubleshooting auth in browser/network logs.
        # utils_login may use IIS RemoteUser in production and DEV fallback in debug mode.
        # (e.g. DEV_LOGIN_USER when DJANGO_DEBUG=1).
        return JsonResponse(
            {
                "ok": False,
                "error": "missing login_user",
                "hint": "missing IIS RemoteUser; set DEV_LOGIN_USER when DJANGO_DEBUG=1",
            },
            status=401,
        )

    # -------------------------
    # 2) Read tm_grsno from GET / JSON / form.
    # -------------------------
    tm_grsno = _get_tm_grsno(request)

    # Fallback for form-style POST.
    if not tm_grsno and request.method == "POST":
        try:
            tm_grsno = (_coerce_text(request.POST.get("im_grsno")) or "").strip()
            if not tm_grsno:
                tm_grsno = (_coerce_text(request.POST.get("tm_grsno")) or "").strip()
            if not tm_grsno:
                tm_grsno = (_coerce_text(request.POST.get("grsno")) or "").strip()
        except Exception:
            pass

    tm_grsno = (tm_grsno or "").strip()

    if not tm_grsno:
        return JsonResponse({"ok": False, "error": "need grsno"}, status=400, json_dumps_params={"ensure_ascii": False})

    # Enforce numeric-only grsno to match backend expectation and avoid malformed input.
    # This also keeps errors deterministic across clients/environments.
    if not re.fullmatch(r"[0-9]{6,20}", tm_grsno):
        return JsonResponse(
            {
                "ok": False,
                "error": "invalid grsno format",
                "im_grsno": tm_grsno,
                "tm_grsno": tm_grsno,
            },
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    # -------------------------
    # 3) Query Sybase
    # -------------------------
    try:
        from webapps.doc.utils_login import get_plant_arg
        plant = get_plant_arg(request)
        svc = docService(plant=plant, login_user_id=login_user, login_user_name=login_user_name)
        rows = svc.lookup_incoming(login_user, tm_grsno)
    except Exception as e:
        return JsonResponse(
            {
                "ok": False,
                "error": "sybase query failed",
                "detail": str(e),
                "meta": {
                    "login_user": login_user,
                    "grsno": tm_grsno,
                    "im_grsno": tm_grsno,
                    "tm_grsno": tm_grsno,
                },
            },
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

    items = _build_items_from_rows(rows)

    # Include request meta to simplify debugging in browser DevTools/Network.
    return JsonResponse(
        {
            "ok": True,
            "items": items,
            "meta": {
                "login_user": login_user,
                "grsno": tm_grsno,
                "im_grsno": tm_grsno,
                "tm_grsno": tm_grsno,
            },
        },
        status=200,
        json_dumps_params={"ensure_ascii": False},
    )


@csrf_exempt
@require_node("doc", api=True)
def incoming_files(request: HttpRequest):
    """
    Incoming files API (GET / POST).
    Returns a flat attachment list and grouped items from the same lookup source.

    GET:
      /doc/incoming_files/?tm_grsno=1150001261
    POST JSON:
      { "tm_grsno": "1150001261" }

    Response:
      { ok, tm_grsno, attachments:[...], items:[...] }

    - attachments: flattened unique attachments from all items
    - items: grouped by (grsno/psid, subject)
    """
    if request.method not in ("GET", "POST"):
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405, json_dumps_params={"ensure_ascii": False})

    login_user = get_login_user_idno(request)
    login_user_name = (get_login_user_name(request) or "").strip()
    if not login_user:
        return JsonResponse({"ok": False, "error": "missing login_user"}, status=401)

    tm_grsno = _get_tm_grsno(request)
    if not tm_grsno:
        return JsonResponse({"ok": False, "error": "need grsno"}, status=400, json_dumps_params={"ensure_ascii": False})

    try:
        from webapps.doc.utils_login import get_plant_arg
        plant = get_plant_arg(request)
        svc = docService(plant=plant, login_user_id=login_user, login_user_name=login_user_name)
        rows = svc.lookup_incoming(login_user, tm_grsno)
    except Exception as e:
        return JsonResponse({"ok": False, "error": "sybase query failed", "detail": str(e)}, status=500, json_dumps_params={"ensure_ascii": False})

    items = _build_items_from_rows(rows)

    flat: List[Dict[str, Any]] = []
    seen = set()
    for it in items:
        for a in (it.get("attachments") or []):
            k = (_coerce_text(a.get("attach_key")) or "").strip()
            name_norm = _norm_filename(_coerce_text(a.get("filename")) or "")
            token = f"{k}::{name_norm}" if name_norm else k
            if not k or token in seen:
                continue
            seen.add(token)
            flat.append(a)

    return JsonResponse(
        {
            "ok": True,
            "grsno": tm_grsno,
            "im_grsno": tm_grsno,
            "tm_grsno": tm_grsno,
            "attachments": flat,
            "items": items,
        },
        status=200,
        json_dumps_params={"ensure_ascii": False},
    )


def _download_incoming_file(request: HttpRequest, attach_key: str):
    """
    GET /doc/incoming_file/<attach_key>/

    - Download by attach_key after ownership check for current login_user.
    - EF: read from DCS1_EMAL_FILE(EF_ID)
    - DF: read from DCS0_DOC_FILE(DF_PATH), where attach_key may hold base64url TD_PATH.
    """
    login_user = get_login_user_idno(request)
    login_user_name = (get_login_user_name(request) or "").strip()
    if not login_user:
        return JsonResponse({"ok": False, "error": "missing login_user"}, status=401)

    attach_key = (attach_key or "").strip()
    if not attach_key:
        return JsonResponse({"ok": False, "error": "empty attach_key"}, status=400)

    kind, val, page = _parse_attach_key(attach_key)
    if not val:
        return JsonResponse({"ok": False, "error": "invalid attach_key"}, status=400)

    hint_hash = ""
    if kind == "EF":
        m_hint = re.match(r"^(.*)\|h([0-9a-fA-F]{8,40})$", val or "")
        if m_hint:
            val = (m_hint.group(1) or "").strip()
            hint_hash = (m_hint.group(2) or "").strip().lower()

    hint_name = (request.GET.get("hint_name") or request.GET.get("filename") or "").strip()
    if not hint_name and request.method == "POST":
        body = {}
        try:
            body = json.loads((request.body or b"{}").decode("utf-8") or "{}")
        except Exception:
            body = {}
        hint_name = str(body.get("hint_name") or body.get("filename") or "").strip()

    try:
        from webapps.doc.utils_login import get_plant_arg
        plant = get_plant_arg(request)
        svc = docService(plant=plant, login_user_id=login_user, login_user_name=login_user_name)
        if kind == "EF":
            row = None
            ok = svc.check_ownership(login_user, "EF", val)
            if ok:
                rows = svc.list_files_by_ef_id(val, page if page else None)
                if not rows and page:
                    rows = svc.list_files_by_ef_id(val, None)
                row = _pick_ef_row(rows or [], hint_name, hint_hash)

                # Legacy/variant key fallback: EF:<id>-<page>
                if not row and (not page):
                    m = re.match(r"^(.+)-(\d{1,6})$", val)
                    if m:
                        ef_id2, page2 = m.group(1).strip(), m.group(2).strip()
                        rows2 = svc.list_files_by_ef_id(ef_id2, page2) or svc.list_files_by_ef_id(ef_id2, None)
                        row = _pick_ef_row(rows2 or [], hint_name, hint_hash)

            # Compatibility fallback: treat EF payload as raw TD_PATH (e.g. EF:mnda-xxxxx-yy)
            if not row and svc.check_ownership(login_user, "DF", val):
                row_df = svc.get_file_by_df_path(val)
                if row_df:
                    filename = (_coerce_text(row_df[0]) or "attachment.bin").strip() or "attachment.bin"
                    data = _bytes_from_blob(row_df[1] if len(row_df) > 1 else None)
                    if data:
                        resp = HttpResponse(data, content_type=_guess_content_type(filename))
                        _set_attachment_headers(resp, filename)
                        return resp

            if not row:
                return JsonResponse({"ok": False, "error": "not found"}, status=404)

            filename = (_coerce_text(row[0]) or "attachment.bin").strip() or "attachment.bin"
            data = _bytes_from_blob(row[1] if len(row) > 1 else None)
            if not data:
                return JsonResponse({"ok": False, "error": "EF_DATA is null/empty"}, status=404)

            resp = HttpResponse(data, content_type=_guess_content_type(filename))
            _set_attachment_headers(resp, filename)
            return resp

        # DF
        df_path = _b64url_decode(val) or val
        if not df_path:
            return JsonResponse({"ok": False, "error": "invalid DF path"}, status=400)

        ok = svc.check_ownership(login_user, "DF", df_path)
        if not ok:
            return JsonResponse({"ok": False, "error": "not found"}, status=404)

        row = svc.get_file_by_df_path(df_path)
        if not row:
            return JsonResponse({"ok": False, "error": "not found"}, status=404)

        filename = (_coerce_text(row[0]) or "attachment.bin").strip() or "attachment.bin"
        data = _bytes_from_blob(row[1] if len(row) > 1 else None)
        if not data:
            return JsonResponse({"ok": False, "error": "DF_DATA is null/empty"}, status=404)

        resp = HttpResponse(data, content_type=_guess_content_type(filename))
        _set_attachment_headers(resp, filename)
        return resp

    except Exception as e:
        return JsonResponse({"ok": False, "error": "sybase download failed", "detail": str(e)}, status=500)


@csrf_exempt
@require_node("doc", api=True)
def incoming_file(request: HttpRequest, attach_key: str):
    """
    GET /doc/incoming_file/<attach_key>/
    """
    return _download_incoming_file(request, attach_key)


@csrf_exempt
@require_node("doc", api=True)
def incoming_file_query(request: HttpRequest):
    """
    GET /doc/incoming_file/?attach_key=...
    POST form/json: attach_key=...
    """
    attach_key = (request.GET.get("attach_key") or "").strip()
    if not attach_key:
        try:
            body = request.json if hasattr(request, "json") else {}  # type: ignore
        except Exception:
            body = {}
        if not body:
            try:
                import json
                body = json.loads((request.body or b"{}").decode("utf-8") or "{}")
            except Exception:
                body = {}
        attach_key = str(body.get("attach_key") or "").strip()

    if not attach_key:
        return JsonResponse({"ok": False, "error": "empty attach_key"}, status=400)
    return _download_incoming_file(request, attach_key)


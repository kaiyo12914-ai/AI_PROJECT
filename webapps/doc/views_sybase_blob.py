# webapps/doc/views_sybase_blob.py
from __future__ import annotations

import base64
import hashlib
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple
import re

from django.conf import settings
from django.http import HttpRequest, JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.utils_login import get_login_user_idno, get_login_user_name
from webapps.doc.services.docService import docService

# =========================
# 依 attach_key 取回檔名/bytes
# 你在 sybase_incoming.py 已經有處理 DF/EF 的邏輯（可直接複用/搬過來）
# 這裡提供「最小可用」版本：假設 attach_key 對應 EF_ID（可再擴充 DF_PATH）
# =========================



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


def _b64url_decode(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    pad = "=" * ((4 - (len(t) % 4)) % 4)
    try:
        return base64.urlsafe_b64decode((t + pad).encode("ascii")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _decode_bytes(b: bytes) -> str:
    if not b:
        return ""
    cs = _normalize_charset_name((os.getenv("SYBASE_CHARSET") or os.getenv("SYBASE_CHAR") or "cp950").strip() or "cp950")
    candidates = []
    if b.startswith(b"\xef\xbb\xbf"):
        candidates.append("utf-8-sig")
    if b.startswith(b"\xff\xfe"):
        candidates.append("utf-16le")
    if b.startswith(b"\xfe\xff"):
        candidates.append("utf-16be")
    if b.count(0) >= max(2, len(b) // 4):
        candidates.extend(["utf-16le", "utf-16be"])
    for enc in (cs, "cp950", "big5", "utf-8", "latin-1"):
        if enc and enc not in candidates:
            candidates.append(enc)

    best_text = ""
    best_score = (-10**9, -10**9, -10**9)
    for enc in candidates:
        try:
            decoded = b.decode(enc)
        except Exception:
            try:
                decoded = b.decode(enc, errors="replace")
            except Exception:
                continue
        score = _text_score(decoded)
        if score > best_score:
            best_score = score
            best_text = decoded
    return _strip_ctrl(best_text)


def _safe_name(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (bytes, bytearray, memoryview)):
        b = x.tobytes() if isinstance(x, memoryview) else bytes(x)
        return _strip_ctrl(_decode_bytes(b))
    if isinstance(x, str):
        return _strip_ctrl(x)
    return _strip_ctrl(str(x))


def _decode_u_escapes(s: str) -> str:
    t = (s or "")
    if "\\u" not in t:
        return t
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)


def _norm_name(s: str) -> str:
    t = _decode_u_escapes(_safe_name(s)).strip().lower()
    return re.sub(r"\s+", " ", t)


def _name_hash(s: str) -> str:
    t = _norm_name(s)
    if not t:
        return ""
    return hashlib.sha1(t.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _pick_row_by_hint(rows: list[Any], hint_name: str = "", hint_hash: str = "") -> Any:
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    hh = (hint_hash or "").strip().lower()
    if hh:
        for rr in rows:
            rn = _name_hash(rr[0] if len(rr) > 0 else "")
            if rn == hh:
                return rr

    if hint_name:
        hn = _norm_name(hint_name)
        for rr in rows:
            rn = _norm_name(rr[0] if len(rr) > 0 else "")
            if rn == hn:
                return rr
    return rows[0]


def _bytes_from_blob(x: Any) -> bytes:
    if x is None:
        return b""
    if isinstance(x, bytes):
        return x
    if isinstance(x, bytearray):
        return bytes(x)
    if isinstance(x, memoryview):
        return x.tobytes()
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
    return "EF", s, ""


def _fetch_blob_by_attach_key(
    attach_key: str,
    *,
    login_user: str,
    login_user_name: str = "",
    hint_name: str = "",
) -> Tuple[str, bytes]:
    ak = (attach_key or "").strip()
    if not ak:
        raise ValueError("attach_key is empty")

    kind, ef_id, page = _parse_attach_key(ak)
    hint_hash = ""
    if kind == "EF":
        m_hint = re.match(r"^(.*)\|h([0-9a-fA-F]{8,40})$", ef_id or "")
        if m_hint:
            ef_id = (m_hint.group(1) or "").strip()
            hint_hash = (m_hint.group(2) or "").strip().lower()
    if kind == "EF" and not ef_id:
        raise ValueError("invalid attach_key")

    svc = docService(login_user_id=login_user, login_user_name=login_user_name)
    if kind == "EF":
        ef_owned = bool(svc.check_ownership(login_user, "EF", ef_id))
        row = None
        if ef_owned:
            rows = svc.list_files_by_ef_id(ef_id, page if page else None)
            if not rows and page:
                # Fallback: page-specific row may not exist in some datasets.
                rows = svc.list_files_by_ef_id(ef_id, None)
            if rows:
                row = _pick_row_by_hint(list(rows), hint_name=hint_name, hint_hash=hint_hash)

            # Legacy/variant key fallback: EF:<id>-<page>
            if not row and (not page):
                m = re.match(r"^(.+)-(\d{1,6})$", ef_id)
                if m:
                    ef_id2, page2 = m.group(1).strip(), m.group(2).strip()
                    rows2 = svc.list_files_by_ef_id(ef_id2, page2) or svc.list_files_by_ef_id(ef_id2, None)
                    if rows2:
                        row = _pick_row_by_hint(list(rows2), hint_name=hint_name, hint_hash=hint_hash)

        if row:
            # docService returns (EF_NAME, EF_DATA)
            name = (_safe_name(row[0] if len(row) > 0 else "") or "attachment.bin").strip()
            raw = _bytes_from_blob(row[1] if len(row) > 1 else None)
            # If page is specified but EF_DATA is empty, fallback to EF_ID only
            if not raw and page:
                rows3 = svc.list_files_by_ef_id(ef_id, None)
                row2 = _pick_row_by_hint(list(rows3 or []), hint_name=hint_name, hint_hash=hint_hash)
                if row2:
                    name = (_safe_name(row2[0] if len(row2) > 0 else "") or name).strip()
                    raw = _bytes_from_blob(row2[1] if len(row2) > 1 else None)
            if raw:
                return name, raw

        # Compatibility fallback: treat EF payload as raw TD_PATH (e.g. EF:mnda-xxxxx-yy)
        df_path_raw = ef_id
        if df_path_raw and svc.check_ownership(login_user, "DF", df_path_raw):
            row_df = svc.get_file_by_df_path(df_path_raw)
            if row_df:
                name = (_safe_name(row_df[0] if len(row_df) > 0 else "") or "attachment.bin").strip()
                raw = _bytes_from_blob(row_df[1] if len(row_df) > 1 else None)
                if raw:
                    return name, raw

        if not ef_owned:
            raise PermissionError("forbidden")
        raise FileNotFoundError(f"EF not found for attach_key={ak}")

    # DF
    df_path = _b64url_decode(ef_id) or ef_id
    if not df_path:
        raise ValueError("invalid DF path")
    if not svc.check_ownership(login_user, "DF", df_path):
        raise PermissionError("forbidden")
    row = svc.get_file_by_df_path(df_path)
    if not row:
        raise FileNotFoundError(f"DF not found for attach_key={ak}")
    name = (_safe_name(row[0] if len(row) > 0 else "") or "attachment.bin").strip()
    raw = _bytes_from_blob(row[1] if len(row) > 1 else None)
    if not raw:
        raise FileNotFoundError("DF_DATA is empty")
    return name, raw


def _stash_dir_for_user(user_id: str) -> Path:
    # MEDIA_ROOT/doc/sybase_stash/<user_id>/
    root = Path(getattr(settings, "MEDIA_ROOT", "") or "")
    if not str(root):
        # 沒設 MEDIA_ROOT 就用專案目錄底下 media（你專案通常有）
        root = Path("media")
    p = root / "doc" / "sybase_stash" / (user_id or "anonymous")
    p.mkdir(parents=True, exist_ok=True)
    return p


@csrf_exempt
@require_node("doc", api=True)
def api_sybase_blob_stash(request: HttpRequest):
    try:
        body: Dict[str, Any] = {}
        try:
            body = request.json if hasattr(request, "json") else {}  # type: ignore
        except Exception:
            body = {}

        if not body:
            import json
            body = json.loads((request.body or b"{}").decode("utf-8") or "{}")

        attach_key = str(body.get("attach_key") or "").strip()
        hint_name = str(body.get("hint_name") or "").strip()

        user_id = (get_login_user_idno(request) or "").strip()
        if not user_id:
            return JsonResponse({"ok": False, "error": "missing login_user"}, status=401)

        user_name = (get_login_user_name(request) or "").strip()
        filename, raw = _fetch_blob_by_attach_key(
            attach_key,
            login_user=user_id,
            login_user_name=user_name,
            hint_name=hint_name,
        )

        # hint_name 可當 fallback
        if not filename and hint_name:
            filename = hint_name

        token = uuid.uuid4().hex
        out_dir = _stash_dir_for_user(user_id)
        out_path = out_dir / f"{token}__{filename}"
        out_path.write_bytes(raw)

        return JsonResponse({
            "ok": True,
            "token": token,
            "filename": filename,
            "size": len(raw),
        })
    except PermissionError:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@require_node("doc", api=True)
def api_sybase_blob_download(request: HttpRequest, token: str):
    user_id = (get_login_user_idno(request) or "").strip()
    if not user_id:
        return JsonResponse({"ok": False, "error": "missing login_user"}, status=401)
    out_dir = _stash_dir_for_user(user_id)

    # 找到 token 開頭的檔案
    token = (token or "").strip()
    if not token:
        raise Http404

    hit = None
    for p in out_dir.glob(f"{token}__*"):
        hit = p
        break

    if not hit or not hit.exists():
        raise Http404

    return FileResponse(open(hit, "rb"), as_attachment=True, filename=hit.name.split("__", 1)[-1])

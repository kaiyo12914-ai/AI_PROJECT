# webapps/doc/services/todo_service.py
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Iterable

from webapps.doc.services.docService import docService


_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "todo_mock.json"
_PINNED_TODO_FILENAME = "令發國防部通電資通報11500001號乙則，請照辦。.pdf"
_PINNED_TODO_SUBJECT_PREFIX = "令發國防部通電資通報11500001號乙則，請照辦。"
_PINNED_TODO_KEYWORD = "令發國防部通電資通報11500001號乙則"


def _is_int_env() -> bool:
    return (os.getenv("ENV") or "").strip().upper() == "INT"


def _normalize_charset_name(cs: str) -> str:
    c = (cs or "").strip()
    if not c:
        return ""
    if c.upper() in ("BIG5", "BIG-5", "CP950"):
        return "cp950"
    return c


def _strip_ctrl(s: str) -> str:
    if not s:
        return ""
    out = []
    for ch in s:
        o = ord(ch)
        if ch in ("\n", "\r", "\t") or o >= 32:
            out.append(ch)
    return "".join(out)


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


def _safe_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (bytes, bytearray, memoryview)):
        b = x.tobytes() if isinstance(x, memoryview) else bytes(x)
        cs = (os.getenv("SYBASE_CHARSET") or os.getenv("SYBASE_CHAR") or "cp950").strip() or "cp950"
        return _decode_bytes_best_effort(b, cs)
    if isinstance(x, str):
        return _strip_ctrl(x)
    return str(x)


def _decode_u_escapes(s: str) -> str:
    t = (s or "")
    if "\\u" not in t:
        return t
    import re
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)


def _match_q(item: Dict[str, Any], q: str) -> bool:
    if not q:
        return True
    q = q.strip().casefold()
    if not q:
        return True

    fields = [
        "im_grsno",
        "tm_grsno",
        "grsno",
        "subject",
        "from_org",
        "doc_no",
        "doc_type",
        "doc_date",
        "status",
    ]
    for k in fields:
        v = _safe_text(item.get(k)).casefold()
        if q in v:
            return True
    return False


def _rows_to_items(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}

    for r in rows or []:
        grsno = _safe_text(r[0] if len(r) > 0 else "").strip()
        psid = _safe_text(r[1] if len(r) > 1 else "").strip()
        subj = _decode_u_escapes(_safe_text(r[2] if len(r) > 2 else "").strip())
        ef_id = _safe_text(r[3] if len(r) > 3 else "").strip()
        ef_name = _decode_u_escapes(_safe_text(r[4] if len(r) > 4 else "").strip())
        ef_page = _safe_text(r[5] if len(r) > 5 else "").strip()

        if not grsno:
            continue

        # Todo list should be one option per document item.
        # Deduplicate by (grsno, subject); attachment-level variants must not duplicate rows.
        key = f"{grsno}::SUBJ::{subj}" if subj else grsno

        if key not in bucket:
            bucket[key] = {
                "im_grsno": grsno,
                "tm_grsno": grsno,
                "grsno": grsno,
                "im_psid": psid,
                "tm_psid": psid,
                "assignee_idno": psid,
                "subject": subj,
                "td_subj": subj,
                "ef_id": ef_id,
                "ef_name": ef_name,
                "ef_page": ef_page,
                "status": "待辦",
            }
        else:
            if not bucket[key].get("subject") and subj:
                bucket[key]["subject"] = subj
                bucket[key]["td_subj"] = subj
            if not bucket[key].get("ef_id") and ef_id:
                bucket[key]["ef_id"] = ef_id
            if not bucket[key].get("ef_name") and ef_name:
                bucket[key]["ef_name"] = ef_name
            if not bucket[key].get("ef_page") and ef_page:
                bucket[key]["ef_page"] = ef_page

    items = list(bucket.values())

    def _norm_text(s: str) -> str:
        t = _safe_text(s).strip()
        return re.sub(r"[\s　，,。．\.、:：;；\-_/]+", "", t)

    def _is_cjk_head(s: str) -> int:
        t = _safe_text(s).strip()
        if not t:
            return 1
        return 0 if re.match(r"^[\u4e00-\u9fff]", t) else 1

    def _pin_rank(it: Dict[str, Any]) -> int:
        subj_raw = _safe_text(it.get("subject") or it.get("td_subj")).strip()
        fname_raw = _safe_text(it.get("ef_name")).strip()
        subj = _norm_text(subj_raw)
        fname = _norm_text(fname_raw)
        kw = _norm_text(_PINNED_TODO_KEYWORD)
        if kw and (kw in subj or kw in fname):
            return 0
        if fname == _PINNED_TODO_FILENAME:
            return 0
        if subj_raw.startswith(_PINNED_TODO_SUBJECT_PREFIX):
            return 0
        return 1

    def _grsno_desc_num(it: Dict[str, Any]) -> int:
        g = _safe_text(it.get("grsno") or it.get("im_grsno") or it.get("tm_grsno")).strip()
        try:
            return -int(g)
        except Exception:
            return 0

    items.sort(
        key=lambda x: (
            _pin_rank(x),
            _is_cjk_head(_safe_text(x.get("subject") or x.get("td_subj"))),
            _grsno_desc_num(x),
            _norm_text(_safe_text(x.get("subject") or x.get("td_subj"))),
        )
    )
    return items


class todoService:
    """
    個人待辦服務：
    - 優先查詢資料庫（Sybase/Oracle 由 docService 路由）
    - 若非 INT 環境且資料庫失敗，可退回 todo_mock.json
    - 回傳格式需穩定，供前端 UI 直接渲染
    """

    def __init__(self, data_path: Path | None = None):
        self.data_path = data_path or _DEFAULT_PATH

    def load(self) -> Dict[str, Any]:
        path = self.data_path
        if not path.exists():
            return {
                "version": "1.0",
                "source": "mock",
                "items": [],
                "warning": f"todo json not found: {path}",
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return {
                "version": "1.0",
                "source": "mock",
                "items": [],
                "error": f"todo json load failed: {e}",
            }

    def list_items(self, *, login_user: str, login_user_name: str = "", q: str = "", plant: str = "") -> Dict[str, Any]:
        q = (q or "").strip()
        try:
            svc = docService(plant=plant, login_user_id=login_user, login_user_name=login_user_name)
            rows = svc.list_incoming_todo(login_user)
            items = _rows_to_items(rows)
            if q:
                items = [it for it in items if _match_q(it, q)]

            syb_sql = ""
            if svc.target.db_type == "sybase":
                em = f"{svc.owner}.DCS1_EMAL_TMP" if svc.owner else "DCS1_EMAL_TMP"
                im = f"{svc.owner}.DCS1_IN_MAST" if svc.owner else "DCS1_IN_MAST"
                ef = f"{svc.owner}.DCS1_EMAL_FILE" if svc.owner else "DCS1_EMAL_FILE"
                syb_sql = (getattr(svc, "SYB_INCOMING_TODO_LIST_SQL", "") or "").format(em=em, im=im, ef=ef)

            meta = {
                "version": "1.0",
                "source": svc.target.db_type,
                "owner_org": None,
                "sql_example": {
                    "dialect": svc.target.db_type,
                    "query": syb_sql.strip() if svc.target.db_type == "sybase" else "(oracle dynamic SQL)",
                    "params": {"login_user": login_user},
                    "plant": svc.target.plant,
                    "owner": svc.target.owner,
                },
                "warning": None,
                "error": None,
            }
            return {"items": items, "meta": meta}
        except Exception as e:
            # INT mode must not fall back to mock JSON.
            if _is_int_env():
                return {
                    "items": [],
                    "meta": {
                        "version": "1.0",
                        "source": "sybase",
                        "owner_org": None,
                        "sql_example": None,
                        "warning": "INT mode: mock fallback disabled.",
                        "error": f"db query failed: {e}",
                    },
                }

            data = self.load()
            items = data.get("items") or []

            out: List[Dict[str, Any]] = []
            for it in items:
                assignee = _safe_text(it.get("assignee_idno")).strip()
                # 在不是 DEV/EXT 模式下，才強制過濾 assignee
                if login_user and assignee and assignee != login_user and _is_int_env():
                    continue
                if not _match_q(it, q):
                    continue
                out.append(it)

            meta = {
                "version": data.get("version"),
                "source": data.get("source", "mock"),
                "owner_org": data.get("owner_org"),
                "sql_example": data.get("sql_example"),
                "warning": data.get("warning"),
                "error": f"db query failed: {e}",
            }
            return {"items": out, "meta": meta}

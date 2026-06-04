# webapps/database/db_factory.py
from __future__ import annotations

import json
import os
import base64
import re
import time
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union, Literal

try:
    import pyodbc  # type: ignore
except Exception:
    pyodbc = None  # type: ignore

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore


DBType = Literal["sqlserver", "oracle", "sybase", "postgresql"]
Params = Optional[Union[Dict[str, Any], Sequence[Any]]]


# ============================================================
# .env loader
# ============================================================
def load_env() -> None:
    if load_dotenv is None:
        return
    env_path = (os.getenv("ENV_PATH") or "").strip()
    if env_path:
        load_dotenv(env_path, override=False)
    else:
        load_dotenv(override=False)


load_env()


def _env(k: str, d: str = "") -> str:
    md_overrides = _load_db_factory_md_overrides()
    md_val = (md_overrides.get((k or "").strip().upper()) or "").strip()
    if md_val:
        return md_val
    return (os.getenv(k) or d).strip()


def _external_db_disabled(db_type: DBType) -> bool:
    """
    ENV mode hard rules:
    - EXT: PostgreSQL is allowed; SQL Server / Oracle / Sybase must use mock JSON.
    - INT: always use external DB, never use mock JSON.
    - Others: default to external DB.
    """
    env_mode = (os.getenv("ENV") or "").strip().upper()
    if env_mode == "EXT":
        return db_type in ("sqlserver", "oracle", "sybase")
    if env_mode == "INT":
        return False
    return False


# ============================================================
# EXT mock DB (read JSON) helpers
# ============================================================
_MOCK_DB_CACHE: Dict[str, Any] = {"path": "", "mtime": 0.0, "data": None}
_DB_FACTORY_MD_CACHE: Dict[str, Any] = {"path": "", "mtime": 0.0, "data": None}
_ORA_THICK_INIT_LOCK = threading.Lock()
_ORA_THICK_INIT_DONE = False


def _mock_json_path() -> str:
    return (
        os.getenv("MOCK_DB_JSON")
        or os.getenv("SQLDOC_JSON")
        or os.getenv("SQLDOC_JSON_PATH")
        or os.getenv("SQLTEST_JSON")
        or os.getenv("SQLTEST_JSON_PATH")
        or "SQLTEST_output.json"
    )


def _load_mock_db() -> Dict[str, Any]:
    path = _mock_json_path()
    p = Path(path)
    try:
        mtime = p.stat().st_mtime
    except Exception:
        return {}

    if _MOCK_DB_CACHE.get("path") == str(p) and _MOCK_DB_CACHE.get("mtime") == mtime:
        return _MOCK_DB_CACHE.get("data") or {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    _MOCK_DB_CACHE.update({"path": str(p), "mtime": mtime, "data": data})
    return data or {}


class _MockRow:
    def __init__(self, mapping: Dict[str, Any], order: List[str]):
        self._mapping = mapping
        self._order = order

    def __getitem__(self, idx):
        if isinstance(idx, int):
            key = self._order[idx]
            return self._mapping.get(key)
        return self._mapping.get(idx)

    def __iter__(self):
        for k in self._order:
            yield self._mapping.get(k)

    def __len__(self):
        return len(self._order)

    def __getattr__(self, name: str) -> Any:
        return self._mapping.get(name)


def _mock_rows_from_list(rows: List[Dict[str, Any]], order: List[str]) -> List[_MockRow]:
    return [_MockRow(r, order) for r in (rows or [])]


def _pick_mock_record(data: Dict[str, Any], grsno: str = "") -> Dict[str, Any]:
    records = data.get("records") if isinstance(data.get("records"), list) else []
    if grsno and records:
        for r in records:
            meta = r.get("meta") or {}
            if str(meta.get("grsno") or "") == str(grsno):
                return r
    if isinstance(data.get("latest"), dict):
        return data.get("latest") or {}
    return records[-1] if records else data


def _extract_td_format_filters(sql: str) -> Optional[set[str]]:
    m = re.search(r"TD(?:\s*\.\s*)?TD_FORMAT\s+IN\s*\((.*?)\)", sql or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    inside = m.group(1) or ""
    literals = re.findall(r"N?'([^']*)'", inside, flags=re.IGNORECASE)
    if literals:
        return {x.strip() for x in literals if str(x).strip()}
    vals: set[str] = set()
    for part in inside.split(","):
        s = part.strip().strip('"').strip("'").strip()
        if s:
            vals.add(s)
    return vals


def _mock_sybase(sql: str, params: Any, data: Dict[str, Any]) -> List[Any]:
    s = (sql or "").upper()
    params_list = list(params or [])
    has_tm_grsno_like = ("TM_GRSNO" in s and "LIKE ?" in s)
    has_grsno_eq = ("EM_GRSNO = ?" in s or "EM_GRSNO=?" in s or "TM_GRSNO = ?" in s or "TM_GRSNO=?" in s)

    def _normalize_like_token(v: Any) -> str:
        return str(v or "").strip().strip("%")

    def _sql_like_match(value: Any, pattern: str) -> bool:
        raw = str(pattern or "")
        val = str(value or "")
        if not raw:
            return True
        if "%" in raw or "_" in raw:
            rx = "^" + re.escape(raw).replace("%", ".*").replace("_", ".") + "$"
            return re.match(rx, val, flags=re.IGNORECASE) is not None
        return val == raw

    if has_grsno_eq:
        if len(params_list) >= 3:
            grsno = str(params_list[-1])
        elif len(params_list) >= 2:
            grsno = str(params_list[1])
        else:
            grsno = str(params_list[0]) if len(params_list) >= 1 else ""
    elif has_tm_grsno_like and len(params_list) >= 1:
        grsno = str(params_list[0])
    else:
        grsno = ""
    grsno_any = grsno
    record = _pick_mock_record(data, _normalize_like_token(grsno_any))

    def _b64_to_bytes(b64: Any) -> bytes:
        if not b64:
            return b""
        try:
            return base64.b64decode(b64, validate=True)
        except Exception:
            try:
                return base64.b64decode(b64)
            except Exception:
                return b""

    if "@@CHARSET" in s or "SYSCHARSETS" in s:
        q = data.get("sybase_charset", {}).get("queries", []) or []
        for item in q:
            if (item.get("sql") or "").strip().upper() in (sql or "").strip().upper():
                rows = item.get("rows") or []
                return [tuple(r) for r in rows]
        return []

    if "DCS3_TRST_MST" in s and "DCS3_TRST_DAT" in s:
        td_format_filters = _extract_td_format_filters(sql or "")
        out = []

        # Parse optional filters from params in the same order as docService.search_trst_advanced.
        pidx = 0
        subj_like = ""
        psid_set = set()
        if ("TM.TM_GRSNO) LIKE ?" in s or "TM_GRSNO) LIKE ?" in s) and pidx < len(params_list):
            pidx += 1
        if ("TD.TD_SUBJ) LIKE ?" in s or "TD_SUBJ) LIKE ?" in s) and pidx < len(params_list):
            subj_like = str(params_list[pidx] or "")
            pidx += 1
        if "TM.TM_PSID) IN (" in s or "TM_PSID) IN (" in s:
            for v in params_list[pidx:]:
                x = str(v or "").strip().upper()
                if x:
                    psid_set.add(x)
        elif ("TM.TM_PSID) = ?" in s or "TM_PSID) = ?" in s or "TM.TM_PSID = ?" in s) and pidx < len(params_list):
            x = str(params_list[pidx] or "").strip().upper()
            if x:
                psid_set.add(x)

        all_recs = data.get("records", [data]) if isinstance(data.get("records"), list) else [data]
        use_all_recs = (not grsno_any) or ("%" in grsno_any) or ("_" in grsno_any)
        src_recs = all_recs if use_all_recs else [record]

        for src in src_recs:
            docs = src.get("official_docs", []) or []
            for d in docs:
                if grsno_any and not _sql_like_match(d.get("tm_grsno"), grsno_any):
                    continue
                if subj_like and not _sql_like_match(d.get("td_subj"), subj_like):
                    continue
                if psid_set:
                    tm_psid = str(d.get("tm_psid") or "").strip().upper()
                    if tm_psid not in psid_set:
                        continue
                if td_format_filters is not None and str(d.get("td_format") or "").strip() not in td_format_filters:
                    continue

                row_map = {
                    "TM_GRSNO": d.get("tm_grsno"),
                    "TM_RSTP": d.get("tm_rstp"),
                    "TD_FORMAT": d.get("td_format"),
                    "TD_SUBJ": d.get("td_subj"),
                    "TM_DATE": d.get("tm_date"),
                    "TM_PSID": d.get("tm_psid"),
                    "TM_NAME": d.get("tm_name"),
                    "DF_DATA": _b64_to_bytes(d.get("df_data_b64")),
                    "TD_PATH": d.get("td_path"),
                    "DF_NAME": d.get("df_name"),
                    "DF_DATA_LEN": d.get("df_data_len") or 0,
                    "EF_ID": d.get("ef_id"),
                    "EF_NAME": d.get("ef_name"),
                    "EF_DATA": _b64_to_bytes(d.get("ef_data_b64")),
                    "EF_DATA_LEN": d.get("ef_data_len") or 0,
                    "EF_PAGE": d.get("ef_page"),
                }

                is_sybase_trst_advanced = (
                    "SELECT TOP" in s
                    and "TM.TM_GRSNO" in s
                    and "TM.TM_DATE" in s
                    and "TM.TM_PSID" in s
                    and "TD.TD_PATH" in s
                    and "DATALENGTH(DF.DF_DATA)" in s
                    and "EF_ID" not in s
                )

                if is_sybase_trst_advanced:
                    # docService.search_trst_advanced (Sybase) shape
                    order = ["TM_GRSNO", "TM_DATE", "TM_PSID", "TM_NAME", "TM_RSTP", "TD_FORMAT", "TD_SUBJ", "TD_PATH", "DF_NAME", "DF_DATA_LEN"]
                elif (
                    "TM_DATE AS TM_DATE" in s
                    and "TM_PSID AS TM_PSID" in s
                    and "TM_NAME) AS TM_NAME" in s
                    and "TD_FORMAT) AS TD_FORMAT" in s
                    and "DF_DATA_LEN" in s
                    and "DF.DF_DATA AS DF_DATA" not in s
                    and "EF_ID" not in s
                ):
                    # docService.SEARCH_TRST_BASE_SQL shape
                    order = ["TM_GRSNO", "TM_DATE", "TM_PSID", "TM_NAME", "TM_RSTP", "TD_FORMAT", "TD_SUBJ", "TD_PATH", "DF_NAME", "DF_DATA_LEN"]
                elif "TM_GRSNO" in s and "TM_RSTP" in s and "DF_DATA" in s and "EF_ID" not in s:  # docService.SYB_OFFICIAL_DOC_BY_GRSNO_SQL shape
                    # Keep column order aligned with SQLTEST.py variants (with/without TD_PATH/DF_NAME/DF_DATA_LEN).
                    if "TD_PATH" in s or "DF_NAME" in s or "DF_DATA_LEN" in s:
                        order = ["TM_GRSNO", "TM_RSTP", "TD_FORMAT", "TD_SUBJ", "TM_DATE", "TM_PSID", "TM_NAME", "TD_PATH", "DF_NAME", "DF_DATA", "DF_DATA_LEN"]
                    elif "EF_NAME" in s or "EF_DATA" in s:
                        order = ["TM_GRSNO", "TM_RSTP", "TD_FORMAT", "TD_SUBJ", "TM_DATE", "TM_PSID", "TM_NAME", "DF_DATA", "EF_NAME", "EF_DATA"]
                    else:
                        order = ["TM_GRSNO", "TM_RSTP", "TD_FORMAT", "TD_SUBJ", "TM_DATE", "TM_PSID", "TM_NAME", "DF_DATA"]
                elif "EF_ID" in s:  # SQLTEST attachment variant
                    if "DF_DATA_LEN" in s or "EF_DATA_LEN" in s:
                        order = ["TM_GRSNO", "TM_RSTP", "TD_FORMAT", "TD_SUBJ", "TM_DATE", "TM_PSID", "TM_NAME", "TD_PATH", "DF_NAME", "DF_DATA", "DF_DATA_LEN", "EF_ID", "EF_NAME", "EF_DATA", "EF_DATA_LEN", "EF_PAGE"]
                    else:
                        order = ["TM_GRSNO", "TM_RSTP", "TD_FORMAT", "TD_SUBJ", "TM_DATE", "TM_PSID", "TM_NAME", "TD_PATH", "DF_NAME", "DF_DATA", "EF_ID", "EF_NAME", "EF_DATA", "EF_PAGE"]
                else:
                    order = list(row_map.keys())

                out.append(_MockRow(row_map, order))
        return out

    if "TM_SUBJ LIKE ?" in s and "TM_TDATE" in s:  # SEARCH_OFFICIAL_DOCS_SQL shape
        results = record.get("search_results", []) or []
        out = []
        for r in results:
            order = ["TM_GRSNO", "TM_TDATE", "TM_PSID", "TM_NAME", "EM_SNO", "TM_RSTP", "TD_FORMAT", "DOC_DATA", "DOC_NAME", "TD_SUBJ", "ATTACH_KEY"]
            # Convert base64 data back to bytes if present
            row_map = dict(r)
            if isinstance(row_map.get("DOC_DATA"), str) and len(row_map["DOC_DATA"]) > 100:
                 row_map["DOC_DATA"] = _b64_to_bytes(row_map["DOC_DATA"])
            out.append(_MockRow(row_map, order))
        return out

    # Legacy SQL_3 pattern:
    # SELECT ... FROM DCS1_EMAL_FILE EF WHERE EF.EF_ID IN (
    #   SELECT EM.EM_FID FROM DCS1_EMAL_TMP EM WHERE EM.EM_GRSNO = ?
    # )
    # Prefer q3 rows from JSON to avoid EF_ID/GRSNO over-filtering in generic join branch.
    if "DCS1_EMAL_FILE" in s and "EF_ID IN (" in s and "EM_FID" in s and "DCS1_EMAL_TMP" in s:
        q = record.get("queries", {}) or {}
        q3_rows = (q.get("q3", {}) or {}).get("rows") or []
        if q3_rows:
            return [tuple(r.values()) for r in q3_rows]

        out = []
        for a in (record.get("attachments", []) or []):
            out.append(
                (
                    a.get("ef_id"),
                    a.get("ef_name"),
                    a.get("ef_data_len") or 0,
                    a.get("ef_page"),
                )
            )
        return out

    if "DCS1_EMAL_TMP" in s and "DCS1_EMAL_FILE" in s:
        # Aggregate attachments across records; if grsno is exact-match mode, use current-record attachments only.
        all_recs = data.get("records", [data]) if isinstance(data.get("records"), list) else [data]
        if record not in all_recs:
            all_recs.insert(0, record)
        
        grsno_exact = _normalize_like_token(grsno)
        attachments = []
        if grsno_exact and any(str(r.get("meta",{}).get("grsno")) == grsno_exact for r in all_recs):
            attachments = record.get("attachments", []) or []
        else:
            for r in all_recs:
                attachments.extend(r.get("attachments", []) or [])
        
        out = []
        has_psid_eq = (
            "IM.IM_PSID) = ?" in s
            or "EM.EM_PSID) = ?" in s
            or "IM.IM_PSID = ?" in s
            or "EM.EM_PSID = ?" in s
        )
        is_keyword_search = ("LIKE ?" in s and not has_grsno_eq)
        psid = str(params_list[0]) if (has_psid_eq and len(params_list) >= 1) else ""
        q = str(params_list[0]) if (is_keyword_search and len(params_list) >= 1) else ""
        q = q.strip().strip("%").lower()
        for a in attachments:
            if psid:
                em_p = str(a.get("em_psid") or "")
                im_p = str(a.get("im_psid") or "")
                if (em_p and em_p != psid) and (im_p and im_p != psid):
                    continue
            if ("EM_GRSNO = ?" in s or "EM_GRSNO=?" in s) and grsno_exact and str(a.get("em_grsno") or "") != grsno_exact:
                continue
            if ("EF_ID" in s and "= ?" in s and "WHERE" in s and s.rfind("EF_ID") > s.find("WHERE")) and grsno and str(a.get("ef_id") or "") != grsno:
                continue
            if q:
                fields = [
                    str(a.get("em_grsno") or ""),
                    str(a.get("td_subj") or ""),
                    str(a.get("ef_name") or ""),
                ]
                if not any(q in f.lower() for f in fields):
                    continue
            
            # Existence-style query: return a single tuple (1,).
            if "SELECT TOP 1 1" in s or "SELECT 1" in s:
                out.append((1,))
                continue

            ef_data = _b64_to_bytes(a.get("ef_data_b64"))
            
            row_map = {
                "EM_GRSNO": a.get("em_grsno"),
                "EM_PSID": a.get("em_psid"),
                "IM_GRSNO": a.get("em_grsno"),
                "IM_PSID": a.get("em_psid"),
                "TD_SUBJ": a.get("td_subj"),
                "EF_ID": a.get("ef_id"),
                "EF_NAME": a.get("ef_name"),
                "EF_DATA": ef_data,
                "EF_DATA_LEN": a.get("ef_data_len") or 0,
                "EM_SUBJ_LEN": a.get("em_subj_len") or 0,
                "TM_SUBJ_LEN": a.get("tm_subj_len") or 0,
                "EF_NAME_LEN": a.get("ef_name_len") or 0,
                "EF_PAGE": a.get("ef_page"),
            }
            
            if "EM_PSID" in s:  # SQL_1 / SYB_INCOMING_LOOKUP_SQL shape
                if "EM_SUBJ_LEN" in s or "TM_SUBJ_LEN" in s or "EF_NAME_LEN" in s:
                    order = ["EM_GRSNO", "EM_PSID", "TD_SUBJ", "EF_ID", "EF_NAME", "EF_DATA", "EF_DATA_LEN", "EM_SUBJ_LEN", "TM_SUBJ_LEN", "EF_NAME_LEN", "EF_PAGE"]
                elif "EF_DATA" in s or "EF_DATA_LEN" in s:
                    order = ["EM_GRSNO", "EM_PSID", "TD_SUBJ", "EF_ID", "EF_NAME", "EF_DATA", "EF_DATA_LEN", "EF_PAGE"]
                else:
                    order = ["EM_GRSNO", "EM_PSID", "TD_SUBJ", "EF_ID", "EF_NAME", "EF_PAGE"]
            else: # legacy lookup
                order = ["EM_GRSNO", "TD_SUBJ", "EF_ID", "EF_NAME", "EF_PAGE"]
            
            out.append(_MockRow(row_map, order))
        return out

    q = record.get("queries", {}) or {}
    if "DCS1_EMAL_TMP" in s and "EM_FID" in s:
        return [tuple(r.values()) for r in (q.get("q2", {}).get("rows") or [])]
    if "DCS1_EMAL_FILE" in s and "EF_ID" in s and "DCS1_EMAL_TMP" not in s:
        ef_id = str(params_list[0]) if len(params_list) >= 1 else ""
        ef_page = str(params_list[1]) if len(params_list) >= 2 else ""
        select_part = s.split("FROM", 1)[0] if "FROM" in s else s
        select_has_ef_id = "EF_ID" in select_part
        out = []
        all_recs = data.get("records", [data]) if isinstance(data.get("records"), list) else [data]
        sources = []
        for r in all_recs:
            sources.extend(r.get("attachments", []) or [])
        if not sources:
            for r in all_recs:
                sources.extend(r.get("official_docs", []) or [])
        for a in sources:
            if ef_id and str(a.get("ef_id") or "") != ef_id:
                continue
            if ef_page and str(a.get("ef_page") or "") != ef_page:
                continue
            ef_name = a.get("ef_name")
            ef_data = _b64_to_bytes(a.get("ef_data_b64"))
            if "EF_NAME" in s and "EF_DATA" in s:
                if select_has_ef_id:
                    out.append((a.get("ef_id"), ef_name, ef_data))
                else:
                    out.append((ef_name, ef_data))
            else:
                out.append((a.get("ef_id"), ef_name, ef_data))
        return out
    if "DCS1_EMAL_FILE" in s and "EF_ID" in s:
        return [tuple(r.values()) for r in (q.get("q3", {}).get("rows") or [])]
    if "DCS1_EMAL_TMP" in s and "EM_PSID" in s and "EM_GRSNO" in s:
        return [tuple(r.values()) for r in (q.get("q4", {}).get("rows") or [])]
    if "DCS0_DOC_FILE" in s and "DF_PATH" in s:
        df_path = str(params_list[0]) if len(params_list) >= 1 else ""
        target_path = df_path.strip()
        out = []

        # DF file lookup can be executed without grsno filter.
        # Search across all mock records, then fall back to official_docs.
        all_recs = data.get("records", [data]) if isinstance(data.get("records"), list) else [data]
        sources = []
        for r in all_recs:
            sources.extend(r.get("df_files", []) or [])
        if not sources:
            for r in all_recs:
                sources.extend(r.get("official_docs", []) or [])

        for d in sources:
            path = str(d.get("df_path") or d.get("td_path") or "").strip()
            if target_path and path != target_path:
                continue
            df_name = d.get("df_name") or d.get("td_subj") or ""
            df_data = _b64_to_bytes(d.get("df_data_b64"))
            if "DF_NAME" in s and "DF_DATA" in s:
                out.append((df_name, df_data))
            elif "DF_DATA" in s:
                out.append((df_data,))
            else:
                out.append((df_name, df_data))
            if target_path:
                break
        return out

    return []


def _mock_oracle(sql: str, params: Any, data: Dict[str, Any]) -> List[Any]:
    s = (sql or "").upper()
    params_dict = params or {}
    record = _pick_mock_record(data)

    if "CT_EMPLOY" in s and ("IDNO" in s or "FACTORY_PLANT" in s):
        emp = record.get("oracle_emp", {}) or {}
        emp_login_id = str(emp.get("login_user") or "")
        emp_login_name = str(emp.get("login_user_name") or "")
        emp_factory = str(emp.get("factory_plant") or "MPC")

        # NAME/NAM -> IDNO lookup (for handler name query)
        if ("NAME" in s or "NAM" in s) and any(k in params_dict for k in ("emp_name", "emp_name_like")):
            name_eq = str(params_dict.get("emp_name") or "").strip()
            name_like = str(params_dict.get("emp_name_like") or "").strip()
            target = name_eq or name_like
            if not target:
                return []
            if "%" in target or "_" in target:
                rx = "^" + re.escape(target).replace("%", ".*").replace("_", ".") + "$"
                if re.match(rx, emp_login_name, flags=re.IGNORECASE):
                    if "FACTORY_PLANT" in s:
                        return [_MockRow({"FACTORY_PLANT": emp_factory}, ["FACTORY_PLANT"])]
                    return [_MockRow({"IDNO": emp_login_id}, ["IDNO"])]
                return []
            if emp_login_name == target:
                if "FACTORY_PLANT" in s:
                    return [_MockRow({"FACTORY_PLANT": emp_factory}, ["FACTORY_PLANT"])]
                return [_MockRow({"IDNO": emp_login_id}, ["IDNO"])]
            return []

        # IDNO -> NAME/NAM lookup
        emp_id = str(params_dict.get("emp_id") or "")
        if not emp_id or emp_id == emp_login_id:
            if "FACTORY_PLANT" in s:
                return [_MockRow({"FACTORY_PLANT": emp_factory}, ["FACTORY_PLANT"])]
            name = emp_login_name or ""
            if "EMP_NAME" in s:
                return [_MockRow({"EMP_NAME": name}, ["EMP_NAME"])]
            if "NAM" in s and "NAME" not in s:
                return [_MockRow({"NAM": name}, ["NAM"])]
            return [_MockRow({"NAME": name}, ["NAME"])]
        return []

    # Oracle ACL group lookup (mock)
    acl = record.get("oracle_acl", {}) or {}
    if acl and "FROM" in s and "WHERE" in s:
        acl_table = str(acl.get("table") or "").upper()
        acl_group_col = str(acl.get("group_col") or "GROUP_NAME").upper()
        if ("GROUP_NAME" in s or acl_group_col in s) and (not acl_table or acl_table in s):
            groups = acl.get("groups", []) or []
            return [_MockRow({"GROUP_NAME": g}, ["GROUP_NAME"]) for g in groups]

    return []


def _mock_db_query_all(db_type: DBType, sql: str, params: Params) -> List[Any]:
    data = _load_mock_db()
    if not data:
        return []
    if db_type == "sybase":
        return _mock_sybase(sql, params, data)
    if db_type == "oracle":
        return _mock_oracle(sql, params, data)
    return []


def _env_int(k: str, d: int) -> int:
    try:
        return int(_env(k, str(d)))
    except Exception:
        return d


def _env_float(k: str, d: float) -> float:
    try:
        return float(_env(k, str(d)))
    except Exception:
        return d


def _env_bool(k: str, d: bool = False) -> bool:
    v = (_env(k, "1" if d else "0") or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _oracle_thick_mode_setting() -> str:
    """
    ORA_THICK_MODE:
    - AUTO (default): thin first, fallback to thick on thin-incompatible DB.
    - THICK: force thick mode.
    - THIN: force thin mode (no fallback).
    """
    raw = (_env("ORA_THICK_MODE", "AUTO") or "AUTO").strip().upper()
    if raw in ("1", "TRUE", "YES", "Y", "ON"):
        return "THICK"
    if raw in ("0", "FALSE", "NO", "N", "OFF"):
        return "THIN"
    if raw in ("AUTO", "THICK", "THIN"):
        return raw
    return "AUTO"


def _ensure_oracle_thick_mode(oracledb_module: Any) -> None:
    global _ORA_THICK_INIT_DONE
    if _ORA_THICK_INIT_DONE:
        return

    with _ORA_THICK_INIT_LOCK:
        if _ORA_THICK_INIT_DONE:
            return

        lib_dir = (_env("ORA_CLIENT_LIB_DIR", "") or _env("ORACLE_CLIENT_LIB_DIR", "")).strip()
        config_dir = (_env("ORA_TNS_ADMIN", "") or _env("TNS_ADMIN", "")).strip()

        kwargs: Dict[str, Any] = {}
        if lib_dir:
            kwargs["lib_dir"] = lib_dir
        if config_dir:
            kwargs["config_dir"] = config_dir

        try:
            if kwargs:
                oracledb_module.init_oracle_client(**kwargs)
            else:
                oracledb_module.init_oracle_client()
        except Exception as e:
            msg = str(e or "")
            if "DPY-2019" in msg:
                raise RuntimeError(
                    "Oracle thick mode init failed with DPY-2019: thin mode is already active in this process. "
                    "Set ORA_THICK_MODE=THICK and restart the whole Django/IIS process before connecting."
                    f" ORA_CLIENT_LIB_DIR={lib_dir or '(empty)'}"
                    f" ORA_TNS_ADMIN={config_dir or '(empty)'}"
                    f" err={e}"
                ) from e
            raise RuntimeError(
                "Oracle thick mode init failed. Please verify Oracle Instant Client settings."
                f" ORA_CLIENT_LIB_DIR={lib_dir or '(empty)'}"
                f" ORA_TNS_ADMIN={config_dir or '(empty)'}"
                f" err={e}"
            ) from e

        _ORA_THICK_INIT_DONE = True


def _list_odbc_drivers() -> List[str]:
    if pyodbc is None:
        return []
    try:
        return list(pyodbc.drivers())
    except Exception:
        return []


def _require_pyodbc(db_type: str) -> None:
    if pyodbc is not None:
        return
    raise RuntimeError(
        f"{db_type} requires pyodbc, but pyodbc is not installed in current Python environment."
    )


# ============================================================
# Driver pickers
# ============================================================
def _pick_sqlserver_driver(prefer: str = "") -> str:
    drivers = _list_odbc_drivers()
    if prefer and prefer in drivers:
        return prefer
    for cand in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        if cand in drivers:
            return cand
    for d in drivers:
        if "sql server" in d.lower():
            return d
    raise RuntimeError(
        "No SQL Server ODBC Driver found.\n"
        f"installed_drivers={drivers!r}\n"
        "Please install ODBC Driver 17/18, or set SQL_SERVER_DRIVER explicitly."
    )


def _pick_sybase_driver(prefer: str = "") -> str:
    drivers = _list_odbc_drivers()
    if prefer and prefer in drivers:
        return prefer

    common = (
        "Sybase ASE ODBC Driver",
        "Sybase ASE",
        "Adaptive Server Enterprise",
        "Sybase ODBC Driver",
    )
    for cand in common:
        if cand in drivers:
            return cand

    keys = ("sybase", "adaptive server", "ase", "iq odbc", "sap iq")
    for d in drivers:
        dl = d.lower()
        # avoid matching Microsoft dBase driver by the "ase" substring
        if "dbase" in dl:
            continue
        if any(k in dl for k in keys):
            return d

    raise RuntimeError(
        "No Sybase ODBC Driver found.\n"
        f"installed_drivers={drivers!r}\n"
        "Please install Sybase ASE ODBC Driver, or set SYBASE_DRIVER explicitly."
    )


def _normalize_charset(cs: str) -> str:
    """
    Normalize charset name for pyodbc decoding.
    - Sybase: BIG5/BIG-5/CP950 -> cp950
    """
    c = (cs or "").strip()
    if not c:
        return ""
    upper = c.upper()
    if upper in ("BIG5", "BIG-5", "CP950"):
        return "cp950"
    return c



# ============================================================
# Config
# ============================================================
@dataclass(frozen=True)
class DBConfig:
    db_type: DBType

    # SQL Server
    sql_host: str = ""
    sql_instance: str = ""
    sql_port: int = 1433
    sql_db: str = ""
    sql_user: str = ""
    sql_pass: str = ""
    sql_dsn: str = ""
    sql_driver: str = "ODBC Driver 17 for SQL Server"

    # Oracle (oracledb Thin)
    ora_host: str = ""
    ora_port: int = 1521
    ora_service: str = ""
    ora_user: str = ""
    ora_pass: str = ""

    # Sybase (pyodbc)
    syb_host: str = ""
    syb_port: int = 5000
    syb_db: str = ""
    syb_user: str = ""
    syb_pass: str = ""
    syb_dsn: str = ""
    syb_driver: str = ""
    syb_charset: str = ""
    syb_tds_version: str = ""

    # PostgreSQL (psycopg2)
    pg_host: str = ""
    pg_port: int = 5432
    pg_db: str = ""
    pg_user: str = ""
    pg_pass: str = ""


def _normalize_profile(profile: str) -> str:
    p = (profile or "").strip().upper()
    if not p:
        return ""
    return re.sub(r"[^A-Z0-9_]+", "_", p)


_PROFILE_ENV_PREFIXES = (
    "CIM_DB",
    "ERP_DB",
    "DOC_DB",
)


def _profile_env_prefixes_and_name(profile: str) -> tuple[tuple[str, ...], str]:
    p = _normalize_profile(profile)
    if p.startswith("CIM_"):
        return (("CIM_DB",), p[4:])
    if p.startswith("ERP_"):
        return (("ERP_DB",), p[4:])
    if p.startswith("DOC_"):
        return (("DOC_DB",), p[4:])
    return (_PROFILE_ENV_PREFIXES, p)


def _profile_env_key(profile: str, key: str) -> str:
    p = _normalize_profile(profile)
    if not p:
        return key
    return f"DOC_DB_{p}_{key}"


def _profile_env_keys(profile: str, key: str) -> List[str]:
    prefixes, p = _profile_env_prefixes_and_name(profile)
    if not p:
        return [key]
    keys: List[str] = []
    for prefix in prefixes:
        keys.append(f"{prefix}_{p}_{key}")
        if key.startswith("ORA_"):
            keys.append(f"{prefix}_{p}_{key[4:]}")
        if key == "ORA_SERVICE_NAME":
            keys.append(f"{prefix}_{p}_ORA_DB")
            keys.append(f"{prefix}_{p}_DB")
    return keys


def _env_profile(profile: str, key: str, default: str = "") -> str:
    md_overrides = _load_db_factory_md_overrides()
    for prof_key in _profile_env_keys(profile, key):
        md_val = (md_overrides.get(prof_key) or "").strip()
        if md_val:
            return md_val
        env_val = (os.getenv(prof_key) or "").strip()
        if env_val:
            return env_val
    # Keep global key fallback for compatibility.
    return _env(key, default)


def _env_int_profile(profile: str, key: str, default: int) -> int:
    md_overrides = _load_db_factory_md_overrides()
    for prof_key in _profile_env_keys(profile, key):
        raw_val = (md_overrides.get(prof_key) or os.getenv(prof_key) or "").strip()
        if raw_val:
            try:
                return int(raw_val)
            except Exception:
                pass
    # Keep global key fallback for compatibility.
    return _env_int(key, default)


def _env_float_profile(profile: str, key: str, default: float) -> float:
    md_overrides = _load_db_factory_md_overrides()
    for prof_key in _profile_env_keys(profile, key):
        raw_val = (md_overrides.get(prof_key) or os.getenv(prof_key) or "").strip()
        if raw_val:
            try:
                return float(raw_val)
            except Exception:
                pass
    return _env_float(key, default)


def load_db_config(db_type: DBType, profile: str = "") -> DBConfig:
    if db_type == "sqlserver":
        return DBConfig(
            db_type="sqlserver",
            sql_driver=_env_profile(profile, "SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server"),
            sql_host=_env_profile(profile, "SQL_SERVER_HOST", "mssql1.mpc.mil.tw"),
            sql_instance=_env_profile(profile, "SQL_SERVER_INSTANCE", ""),
            sql_port=_env_int_profile(profile, "SQL_SERVER_PORT", 1433),
            sql_db=_env_profile(profile, "SQL_SERVER_DB", "CaseManager"),
            sql_user=_env_profile(profile, "SQL_SERVER_USER", ""),
            sql_pass=_env_profile(profile, "SQL_SERVER_PASS", ""),
            sql_dsn=_env_profile(profile, "SQL_SERVER_DSN", ""),
        )

    if db_type == "oracle":
        return DBConfig(
            db_type="oracle",
            ora_host=_env_profile(profile, "ORA_HOST", ""),
            ora_port=_env_int_profile(profile, "ORA_PORT", 1521),
            ora_service=_env_profile(profile, "ORA_SERVICE_NAME", ""),
            ora_user=_env_profile(profile, "ORA_USER", ""),
            ora_pass=_env_profile(profile, "ORA_PASS", ""),
        )

    if db_type == "postgresql":
        return DBConfig(
            db_type="postgresql",
            pg_host=_env_profile(profile, "PG_HOST", "127.0.0.1"),
            pg_port=_env_int_profile(profile, "PG_PORT", 5432),
            pg_db=_env_profile(profile, "PG_DB", ""),
            pg_user=_env_profile(profile, "PG_USER", "postgres"),
            pg_pass=_env_profile(profile, "PG_PASS", ""),
        )

    return DBConfig(
        db_type="sybase",
        syb_driver=_env_profile(profile, "SYBASE_DRIVER", ""),
        syb_host=_env_profile(profile, "SYBASE_HOST", ""),
        syb_port=_env_int_profile(profile, "SYBASE_PORT", 5000),
        syb_db=_env_profile(profile, "SYBASE_DB", ""),
        syb_user=_env_profile(profile, "SYBASE_USER", ""),
        syb_pass=_env_profile(profile, "SYBASE_PASS", ""),
        syb_dsn=_env_profile(profile, "SYBASE_DSN", ""),
        syb_charset=_env_profile(profile, "SYBASE_CHARSET", _env_profile(profile, "SYBASE_CHAR", "")),
        syb_tds_version=_env_profile(profile, "SYBASE_TDS_VERSION", ""),
    )


def _db_factory_md_path() -> Path:
    """
    DB profile override file for DOC plant routing.
    Priority:
    1) DB_FACTORY_MD_PATH env
    2) <project_root>/.env_DB_factory
    3) webapps/database/.env_DB_factory
    """
    custom = (os.getenv("DB_FACTORY_MD_PATH") or "").strip()
    if custom:
        return Path(custom)

    root_candidate = Path.cwd() / ".env_DB_factory"
    if root_candidate.exists():
        return root_candidate
    return Path(__file__).resolve().parent / ".env_DB_factory"


def _unquote_env_value(v: str) -> str:
    s = (v or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _is_db_factory_key_supported(key: str) -> bool:
    k = (key or "").strip().upper()
    if not k:
        return False
    return (
        k.startswith("DOC_DB_")
        or k.startswith("CIM_DB_")
        or k.startswith("ERP_DB_")
        or k.startswith("ORA_")
        or k.startswith("SQL_SERVER_")
        or k.startswith("SYBASE_")
        or k.startswith("PG_")
        or k == "TEXT_MAX_CHARS"
    )


def _load_db_factory_md_overrides() -> Dict[str, str]:
    """
    Parse DB-related key/value lines from .env_DB_factory.
    Supports plain env-style lines anywhere in markdown:
      CIM_DB_MPC_ORA_HOST=10.29.136.198
      ERP_DB_MPC_HOST=10.29.136.198
      DOC_DB_205_ORA_HOST=10.29.136.198
      ORA_HOST=10.29.136.198
      SQL_SERVER_HOST=mssql1.mpc.mil.tw
      SQL_SERVER_INSTANCE=mpcsqlserver
    """
    p = _db_factory_md_path()
    try:
        mtime = p.stat().st_mtime
    except Exception:
        return {}

    if _DB_FACTORY_MD_CACHE.get("path") == str(p) and _DB_FACTORY_MD_CACHE.get("mtime") == mtime:
        return _DB_FACTORY_MD_CACHE.get("data") or {}

    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""

    data: Dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = (raw or "").strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not m:
            continue
        key = (m.group(1) or "").strip().upper()
        if not _is_db_factory_key_supported(key):
            continue
        val = _unquote_env_value(m.group(2) or "")
        data[key] = val

    _DB_FACTORY_MD_CACHE.update({"path": str(p), "mtime": mtime, "data": data})
    return data


def _apply_db_factory_md_env_overrides() -> None:
    """
    Promote .env_DB_factory values into process env so modules that call
    os.getenv directly (outside db_factory) can read the same values.
    """
    data = _load_db_factory_md_overrides()
    if not data:
        return
    for k, v in data.items():
        if not k:
            continue
        # .env_DB_factory has higher priority than .env for DB keys.
        os.environ[k] = str(v or "")


_apply_db_factory_md_env_overrides()


# ============================================================
# DB implementations
# ============================================================
class BaseDB:
    def connect(self) -> Any:
        raise NotImplementedError


class SQLServerDB(BaseDB):
    def __init__(self, config: Optional[DBConfig] = None, profile: str = "") -> None:
        self.cfg = config or load_db_config("sqlserver", profile=profile)
        self._conn_str = self._build_conn_str()

    @property
    def connection_string(self) -> str:
        return self._conn_str

    def _build_conn_str(self) -> str:
        c = self.cfg

        # DSN mode
        if c.sql_dsn:
            parts = [f"DSN={c.sql_dsn}"]
            if c.sql_user:
                parts.append(f"UID={c.sql_user}")
            if c.sql_pass:
                parts.append(f"PWD={c.sql_pass}")
            if c.sql_db:
                parts.append(f"DATABASE={c.sql_db}")
            return ";".join(parts)

        driver = _pick_sqlserver_driver(c.sql_driver)

        # SQL Server server token normalization:
        # - If SQL_SERVER_HOST already contains "\instance", treat it as final.
        # - Otherwise, append SQL_SERVER_INSTANCE when provided.
        # - Fallback to host,port.
        host = (c.sql_host or "").strip().replace("\\\\", "\\")
        instance = (c.sql_instance or "").strip().lstrip("\\")

        if "\\" in host:
            server = host
        elif instance:
            server = f"{host}\\{instance}"
        else:
            server = f"{host},{int(c.sql_port)}"

        base = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={c.sql_db};"
        )

        if c.sql_user:
            base += f"UID={c.sql_user};PWD={c.sql_pass};"

        return base

    def connect(self) -> pyodbc.Connection:
        _require_pyodbc("sqlserver")
        try:
            return pyodbc.connect(
                self.connection_string,
                timeout=_env_int("SQLSERVER_CONNECT_TIMEOUT", 10),  # connect timeout (sec)
                autocommit=True,
            )
        except Exception as e:
            raise RuntimeError(
                "SQL Server connect failed. "
                f"err={e}\n"
                f"conn_str={self.connection_string}\n"
                f"drivers={_list_odbc_drivers()}"
            ) from e


class SybaseDB(BaseDB):
    def __init__(self, config: Optional[DBConfig] = None, profile: str = "") -> None:
        self.cfg = config or load_db_config("sybase", profile=profile)
        self._conn_str = self._build_conn_str()

    @property
    def connection_string(self) -> str:
        return self._conn_str

    def _build_conn_str(self) -> str:
        c = self.cfg

        # DSN mode
        if c.syb_dsn:
            parts = [f"DSN={c.syb_dsn}"]
            if c.syb_user:
                parts.append(f"UID={c.syb_user}")
            if c.syb_pass:
                parts.append(f"PWD={c.syb_pass}")
            if c.syb_db:
                parts.append(f"DATABASE={c.syb_db}")
            if c.syb_charset:
                parts.append(f"CHARSET={c.syb_charset}")
            if c.syb_tds_version:
                parts.append(f"TDS_VERSION={c.syb_tds_version}")
            return ";".join(parts)

        driver = _pick_sybase_driver(c.syb_driver)

        if not (c.syb_host and c.syb_user and c.syb_pass):
            raise RuntimeError(
                "Sybase connection config incomplete. Set SYBASE_HOST/SYBASE_USER/SYBASE_PASS, or set SYBASE_DSN."
            )

        base = (
            f"DRIVER={{{driver}}};"
            f"SERVER={c.syb_host};"
            f"PORT={int(c.syb_port)};"
        )
        if c.syb_db:
            base += f"DATABASE={c.syb_db};"
        base += f"UID={c.syb_user};PWD={c.syb_pass};"
        if c.syb_charset:
            base += f"CHARSET={c.syb_charset};"
        if c.syb_tds_version:
            base += f"TDS_VERSION={c.syb_tds_version};"
        return base

    def connect(self) -> pyodbc.Connection:
        _require_pyodbc("sybase")
        try:
            conn = pyodbc.connect(
                self.connection_string,
                timeout=_env_int("SYBASE_CONNECT_TIMEOUT", 10),  # connect timeout (sec)
                autocommit=True,
            )
            cs = _normalize_charset(self.cfg.syb_charset)
            if cs:
                try:
                    # Explicit decoding/encoding to avoid mojibake on BIG5 text columns.
                    conn.setdecoding(pyodbc.SQL_CHAR, encoding=cs)
                    conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-16le")
                    conn.setencoding(encoding=cs)
                except Exception:
                    pass
            return conn
        except Exception as e:
            raise RuntimeError(
                "Sybase connect failed. "
                f"err={e}\n"
                f"conn_str={self.connection_string}\n"
                f"drivers={_list_odbc_drivers()}"
            ) from e


class OracleDB(BaseDB):
    """
    Oracle connection via python-oracledb (thin/thick).
    - No Oracle ODBC driver is required.
    - Install with: pip install oracledb
    """

    def __init__(self, config: Optional[DBConfig] = None, profile: str = "") -> None:
        self.cfg = config or load_db_config("oracle", profile=profile)
        self.profile = profile

    def connect(self):
        try:
            import oracledb  # type: ignore
        except Exception as e:
            raise RuntimeError("OracleDB requires oracledb. Run: pip install oracledb") from e
        # Oracle path: fetch LOB columns as bytes/str immediately (not detached locators).
        try:
            if hasattr(oracledb, "defaults"):
                setattr(oracledb.defaults, "fetch_lobs", True)
        except Exception:
            pass

        c = self.cfg
        if not (c.ora_host and c.ora_service and c.ora_user and c.ora_pass):
            raise RuntimeError(
                "Oracle config incomplete. Set ORA_HOST / ORA_SERVICE_NAME / ORA_USER / ORA_PASS."
            )

        dsn = f"{c.ora_host}:{int(c.ora_port)}/{c.ora_service}"

        connect_timeout = _env_float_profile(self.profile, "ORA_CONNECT_TIMEOUT_SEC", 8.0)  # sec
        call_timeout_ms = _env_int_profile(self.profile, "ORA_CALL_TIMEOUT_MS", 15000)      # ms
        connect_retry_count = _env_int_profile(self.profile, "ORA_CONNECT_RETRY_COUNT", 1)
        connect_retry_delay = _env_int_profile(self.profile, "ORA_CONNECT_RETRY_DELAY", 1)

        def _do_connect():
            try:
                return oracledb.connect(
                    user=c.ora_user,
                    password=c.ora_pass,
                    dsn=dsn,
                    timeout=connect_timeout,
                    retry_count=max(0, int(connect_retry_count)),
                    retry_delay=max(0, int(connect_retry_delay)),
                )
            except TypeError:
                # Older python-oracledb may not support timeout/retry kwargs.
                return oracledb.connect(user=c.ora_user, password=c.ora_pass, dsn=dsn)

        mode = _oracle_thick_mode_setting()
        thin_hint = "not supported by python-oracledb in thin mode"
        client_lib_dir = (_env("ORA_CLIENT_LIB_DIR", "") or _env("ORACLE_CLIENT_LIB_DIR", "")).strip()
        auto_prefer_thick = _env_bool("ORA_AUTO_PREFER_THICK", bool(client_lib_dir))

        if mode == "THICK":
            _ensure_oracle_thick_mode(oracledb)
            try:
                conn = _do_connect()
            except Exception as e:
                raise RuntimeError(f"Oracle thick connect failed. dsn={dsn}, err={e}") from e
        elif mode == "THIN":
            try:
                conn = _do_connect()
            except Exception as e:
                raise RuntimeError(f"Oracle thin connect failed. dsn={dsn}, err={e}") from e
        else:
            # AUTO:
            # - default prefer thick when ORA_CLIENT_LIB_DIR is configured.
            # - avoids DPY-2019 (cannot switch to thick after thin is active).
            if auto_prefer_thick:
                thick_err: Exception | None = None
                try:
                    _ensure_oracle_thick_mode(oracledb)
                    conn = _do_connect()
                except Exception as e:
                    thick_err = e
                    try:
                        conn = _do_connect()
                    except Exception as e2:
                        msg2 = str(e2 or "")
                        if ("DPY-3010" in msg2) or (thin_hint in msg2.lower()):
                            raise RuntimeError(
                                "Oracle AUTO connect failed: thin mode does not support this DB version, "
                                "and thick mode was not available. "
                                "Check ORA_CLIENT_LIB_DIR, set ORA_THICK_MODE=THICK, then restart process."
                                f" dsn={dsn}, thick_err={thick_err}, thin_err={e2}"
                            ) from e2
                        raise RuntimeError(
                            f"Oracle AUTO connect failed (thick-first then thin). dsn={dsn}, thick_err={thick_err}, thin_err={e2}"
                        ) from e2
            else:
                # thin-first fallback path (legacy behavior)
                try:
                    conn = _do_connect()
                except Exception as e:
                    msg = str(e or "")
                    if ("DPY-3010" in msg) or (thin_hint in msg.lower()):
                        _ensure_oracle_thick_mode(oracledb)
                        try:
                            conn = _do_connect()
                        except Exception as e2:
                            raise RuntimeError(
                                f"Oracle AUTO connect failed (thin->thick). dsn={dsn}, thin_err={e}, thick_err={e2}"
                            ) from e2
                    else:
                        raise RuntimeError(f"Oracle connect failed. dsn={dsn}, err={e}") from e

        if int(call_timeout_ms) > 0:
            try:
                conn.call_timeout = int(call_timeout_ms)
            except Exception:
                pass

        return conn


class PostgreSQLDB(BaseDB):
    def __init__(self, config: Optional[DBConfig] = None, profile: str = "") -> None:
        self.profile = (profile or "").strip()
        self.cfg = config or load_db_config("postgresql", profile=profile)

    def connect(self) -> Any:
        try:
            import psycopg2  # type: ignore
        except Exception as e:
            raise RuntimeError("PostgreSQLDB requires psycopg2. Run pip install psycopg2-binary") from e
        
        c = self.cfg
        host, port, dbname, user, password = c.pg_host, c.pg_port, c.pg_db, c.pg_user, c.pg_pass

        # Prefer global DATABASE_URL. Per-profile PostgreSQL should use PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASS.
        db_url = _env("DATABASE_URL", "").strip()
        if db_url.startswith("postgres://") or db_url.startswith("postgresql://"):
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(db_url)
                host = parsed.hostname or host
                port = parsed.port or port
                dbname = (parsed.path or "").lstrip("/") or dbname
                user = parsed.username or user
                password = parsed.password or password
            except Exception:
                pass

        if not (host and dbname and user):
            raise RuntimeError("PostgreSQL config incomplete. Set DATABASE_URL or PG_HOST, PG_DB, PG_USER.")
            
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=_env_int("PG_CONNECT_TIMEOUT", 10)
            )
            # Typically psycopg2 needs autocommit=True for seamless DB_FACTORY behavior
            conn.autocommit = True
            return conn
        except Exception as e:
            raise RuntimeError(f"PostgreSQL connect failed. host={host}, db={dbname}, err={e}") from e



# ============================================================
# Factory helpers
# ============================================================
def get_db(db_type: DBType = "sqlserver", profile: str = "") -> BaseDB:
    if db_type == "sqlserver":
        return SQLServerDB(profile=profile)
    if db_type == "oracle":
        return OracleDB(profile=profile)
    if db_type == "sybase":
        return SybaseDB(profile=profile)
    if db_type == "postgresql":
        return PostgreSQLDB(profile=profile)
    raise ValueError(f"Unsupported db_type={db_type!r}")


def db_connect(db_type: DBType = "sqlserver", profile: str = ""):
    return get_db(db_type, profile=profile).connect()


# ============================================================
# Query helpers
# ============================================================
def _normalize_params(db_type: DBType, params: Params) -> Any:
    """
    - params=None: pass through None.
    - pyodbc (SQLServer/Sybase): use positional params (list/tuple), not dict.
    - oracledb (Oracle): supports dict or positional sequence.
    """
    if params is None:
        return None
    if db_type in ("sqlserver", "sybase") and isinstance(params, dict):
        raise TypeError(f"{db_type} with pyodbc requires positional params (list/tuple), not dict.")
    return params


def _normalize_sql(sql: Any) -> str:
    if sql is None:
        return ""
    if isinstance(sql, bytes):
        return sql.decode("utf-8", errors="ignore")
    return str(sql)


def _normalize_param_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, bytes):
        return _strip_ctrl(val.decode("utf-8", errors="ignore"))
    if isinstance(val, bytearray):
        return _strip_ctrl(bytes(val).decode("utf-8", errors="ignore"))
    if isinstance(val, memoryview):
        return _strip_ctrl(val.tobytes().decode("utf-8", errors="ignore"))
    if isinstance(val, str):
        return _strip_ctrl(val)
    return val


def _strip_ctrl(s: str) -> str:
    if not s:
        return ""
    out = []
    for ch in s:
        o = ord(ch)
        if ch in ("\n", "\r", "\t") or o >= 32:
            out.append(ch)
    return "".join(out)


def _normalize_params_for_db(db_type: DBType, params: Params) -> Any:
    params = _normalize_params(db_type, params)
    if params is None:
        return None
    if isinstance(params, dict):
        return {k: _normalize_param_value(v) for k, v in params.items()}
    if isinstance(params, (list, tuple)):
        return [_normalize_param_value(v) for v in params]
    return params


def _apply_query_timeout(db_type: DBType, cursor: Any) -> None:
    """
    pyodbc cursor.timeout depends on driver support and can be ignored by some drivers.
    Oracle timeout is mainly controlled by conn.call_timeout.
    """
    try:
        if db_type == "sqlserver":
            cursor.timeout = int(_env_int("SQLSERVER_QUERY_TIMEOUT", 10))
        elif db_type == "sybase":
            cursor.timeout = int(_env_int("SYBASE_QUERY_TIMEOUT", 10))
    except Exception:
        pass


def _apply_sybase_textsize(db_type: DBType, cursor: Any) -> None:
    """
    Ensure large Sybase LOB/BLOB values are not truncated by session TEXTSIZE.
    Default uses max 2GB-1; can override with SYBASE_TEXTSIZE.
    """
    if db_type != "sybase":
        return
    try:
        textsize = int(_env_int("SYBASE_TEXTSIZE", 2147483647))
        if textsize <= 0:
            return
        cursor.execute(f"set textsize {textsize}")
    except Exception:
        # Keep query path resilient even if driver/session doesn't accept SET TEXTSIZE.
        pass


def _is_oracle_retryable_error(err: Exception) -> bool:
    msg = str(err or "")
    if not msg:
        return False
    u = msg.upper()
    markers = (
        "DPY-1001",            # not connected to database
        "DPY-4011",            # network/session interrupted
        "DPI-1067",            # call timeout exceeded
        "ORA-03156",           # OCI call timed out
        "ORA-03113",           # end-of-file on communication channel
        "ORA-03114",           # not connected to ORACLE
        "CALL TIMEOUT OF",     # python-oracledb call timeout text
    )
    return any(m in u for m in markers)


def _materialize_oracle_lob_value(v: Any) -> Any:
    """
    Oracle LOB locators are connection-bound in thin mode.
    Materialize them before cursor/connection close to avoid DPY-1001 on later access.
    """
    if v is None:
        return None
    # oracledb LOB objects expose read(); non-LOB values usually do not.
    if hasattr(v, "read"):
        try:
            return v.read()
        except Exception:
            return v
    return v


def _materialize_oracle_row(row: Any) -> Any:
    if row is None:
        return None
    try:
        vals = list(row)
    except Exception:
        return row
    return tuple(_materialize_oracle_lob_value(v) for v in vals)


def db_query_one(db_type: DBType, sql: str, params: Params = None, *, profile: str = "") -> Any:
    if _external_db_disabled(db_type):
        rows = _mock_db_query_all(db_type, sql, params)
        return rows[0] if rows else None
    sql = _normalize_sql(sql)
    retry = 1
    retry_delay_ms = 250
    if db_type == "oracle":
        retry = max(1, _env_int_profile(profile, "ORA_QUERY_RETRY", 2))
        retry_delay_ms = max(0, _env_int_profile(profile, "ORA_QUERY_RETRY_DELAY_MS", 300))

    last_err: Exception | None = None
    for attempt in range(1, retry + 1):
        conn = db_connect(db_type, profile=profile)
        cur = None
        try:
            cur = conn.cursor()
            _apply_query_timeout(db_type, cur)
            _apply_sybase_textsize(db_type, cur)
            cur.execute(sql, _normalize_params_for_db(db_type, params))
            row = cur.fetchone()
            if row is None:
                return None
            if db_type == "oracle":
                row = _materialize_oracle_row(row)
            return row
        except Exception as e:
            last_err = e
            can_retry = (db_type == "oracle") and _is_oracle_retryable_error(e) and (attempt < retry)
            if not can_retry:
                raise
            if retry_delay_ms > 0:
                time.sleep(retry_delay_ms / 1000.0)
        finally:
            try:
                if cur is not None:
                    cur.close()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    if last_err is not None:
        raise last_err
    return None


def db_query_all(
    db_type: DBType,
    sql: str,
    params: Params = None,
    *,
    limit: int = 0,
    profile: str = "",
) -> List[Any]:
    if _external_db_disabled(db_type):
        rows = _mock_db_query_all(db_type, sql, params)
        if limit and limit > 0:
            return list(rows)[: int(limit)]
        return list(rows)
    sql = _normalize_sql(sql)
    retry = 1
    retry_delay_ms = 250
    if db_type == "oracle":
        retry = max(1, _env_int_profile(profile, "ORA_QUERY_RETRY", 2))
        retry_delay_ms = max(0, _env_int_profile(profile, "ORA_QUERY_RETRY_DELAY_MS", 300))

    last_err: Exception | None = None
    for attempt in range(1, retry + 1):
        conn = db_connect(db_type, profile=profile)
        cur = None
        try:
            cur = conn.cursor()
            _apply_query_timeout(db_type, cur)
            _apply_sybase_textsize(db_type, cur)
            cur.execute(sql, _normalize_params_for_db(db_type, params))
            if limit and limit > 0:
                rows = list(cur.fetchmany(int(limit)))
            else:
                rows = list(cur.fetchall())
            if db_type == "oracle":
                rows = [_materialize_oracle_row(r) for r in rows]
            return rows
        except Exception as e:
            last_err = e
            can_retry = (db_type == "oracle") and _is_oracle_retryable_error(e) and (attempt < retry)
            if not can_retry:
                raise
            if retry_delay_ms > 0:
                time.sleep(retry_delay_ms / 1000.0)
        finally:
            try:
                if cur is not None:
                    cur.close()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    if last_err is not None:
        raise last_err
    return []


def db_execute(db_type: DBType, sql: str, params: Params = None, *, profile: str = "") -> int:
    if _external_db_disabled(db_type):
        return 0
    conn = db_connect(db_type, profile=profile)
    cur = None
    try:
        cur = conn.cursor()
        _apply_query_timeout(db_type, cur)
        cur.execute(sql, _normalize_params(db_type, params))
        try:
            conn.commit()
        except Exception:
            pass
        try:
            return int(cur.rowcount or 0)
        except Exception:
            return 0
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            try:
                conn.close()
            except Exception:
                pass



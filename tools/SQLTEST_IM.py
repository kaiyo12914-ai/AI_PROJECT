# SQLTEST.py
import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Tuple, List

try:
    from webapps.database.db_factory import db_query_all, db_connect
except Exception:
    db_query_all = None  # type: ignore[assignment]
    db_connect = None  # type: ignore[assignment]

SQL_1 = """
SELECT TOP 60
    COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS IM_GRSNO,
    COALESCE(IM.IM_PSID, EM.EM_PSID) AS IM_PSID,
    CONVERT(VARBINARY(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ,
    CONVERT(VARCHAR(64), EF.EF_ID) AS EF_ID,
    CONVERT(VARBINARY(4000), EF.EF_NAME) AS EF_NAME,
    EF.EF_DATA,
    DATALENGTH(EF.EF_DATA) AS EF_DATA_LEN,
    DATALENGTH(EM.EM_SUBJ) AS EM_SUBJ_LEN,
    DATALENGTH(IM.IM_SUBJ) AS IM_SUBJ_LEN,
    DATALENGTH(EF.EF_NAME) AS EF_NAME_LEN,
    EF.EF_PAGE
FROM mnda.dbo.DCS1_EMAL_TMP EM
LEFT JOIN mnda.dbo.DCS1_IN_MAST IM ON EM.EM_GRSNO = IM.IM_GRSNO
LEFT JOIN mnda.dbo.DCS1_EMAL_FILE EF ON EM.EM_FID = EF.EF_ID
WHERE 1=1
  AND (CONVERT(VARCHAR(64), IM.IM_PSID) = ? OR CONVERT(VARCHAR(64), EM.EM_PSID) = ?)
  AND EM.EM_GRSNO = ?
ORDER BY EF.EF_PAGE
"""

SQL_2 = """
SELECT
    EM.EM_GRSNO,
    CONVERT(VARCHAR(64), EM.EM_FID) AS EM_FID
FROM mnda.dbo.DCS1_EMAL_TMP EM
WHERE EM.EM_GRSNO = ?
"""

SQL_3 = """
SELECT
    CONVERT(VARCHAR(64), EF.EF_ID) AS EF_ID,
    CONVERT(VARBINARY(400),EF.EF_NAME) AS EF_NAME,
    DATALENGTH(EF.EF_DATA) AS EF_DATA_LEN,
    EF.EF_PAGE
FROM mnda.dbo.DCS1_EMAL_FILE EF
WHERE EF.EF_ID IN (
    SELECT EM.EM_FID
    FROM mnda.dbo.DCS1_EMAL_TMP EM
    WHERE EM.EM_GRSNO = ?
)
"""

SQL_4 = """
SELECT
    EM.EM_GRSNO,
    EM.EM_PSID
FROM mnda.dbo.DCS1_EMAL_TMP EM
WHERE EM.EM_GRSNO = ?
"""

SQL_5_OFFICIAL = """
SELECT
    TM.TM_GRSNO AS TM_GRSNO,
    CONVERT(VARBINARY(400), TM.TM_RSTP) AS TM_RSTP,
    CONVERT(VARBINARY(400), TD.TD_FORMAT) AS TD_FORMAT,
    CONVERT(VARBINARY(4000), TD.TD_SUBJ) AS TD_SUBJ,
    TM.TM_DATE AS TM_DATE,
    TM.TM_PSID AS TM_PSID,
    CONVERT(VARBINARY(400), TM.TM_NAME) AS TM_NAME,
    TD.TD_PATH AS TD_PATH,
    CONVERT(VARBINARY(400), DF.DF_NAME) AS DF_NAME,
    DF.DF_DATA AS DF_DATA,
    DATALENGTH(DF.DF_DATA) AS DF_DATA_LEN
FROM mnda.dbo.DCS3_TRST_MST TM
LEFT JOIN mnda.dbo.DCS3_TRST_DAT TD ON TM.TM_SNO = TD.TD_SNO
LEFT JOIN mnda.dbo.DCS0_DOC_FILE DF ON DF.DF_PATH = TD.TD_PATH
WHERE TM.TM_GRSNO = ?
  AND TM.TM_DATE = (
      SELECT MAX(TM_DATE)
      FROM mnda.dbo.DCS3_TRST_MST DT
      WHERE DT.TM_GRSNO = TM.TM_GRSNO
  )
ORDER BY TD.TD_FORMAT
"""

SQL_CHARSET_1 = "SELECT @@charset AS SERVER_CHARSET"
SQL_CHARSET_2 = """
SELECT name, id
FROM syscharsets
WHERE id = (SELECT value FROM sysconfigures WHERE name = 'default character set id')
"""

SQL_ORA_EMP = """
SELECT NAME
FROM CT_EMPLOY
WHERE IDNO = :emp_id
"""


def _read_env_file(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.lower().startswith("export "):
                s = s[7:].strip()
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("\"").strip("'")
            out[k] = v
    return out


def _load_env_map() -> Dict[str, str]:
    env_path = os.path.join(os.getcwd(), ".env")
    env_map = _read_env_file(env_path)
    for k, v in os.environ.items():
        if k not in env_map and v is not None:
            env_map[k] = v
    return env_map


def _blob_to_text_preview(blob: Any, limit: int = 1000) -> Tuple[str, int]:
    if blob is None:
        return "", 0
    if isinstance(blob, memoryview):
        b = blob.tobytes()
    elif isinstance(blob, bytearray):
        b = bytes(blob)
    elif isinstance(blob, bytes):
        b = blob
    else:
        try:
            b = bytes(blob)
        except Exception:
            return "", 0

    if not b:
        return "", 0

    if b.startswith(b"%PDF"):
        try:
            head = b[: min(len(b), limit)].decode("latin-1", errors="ignore")
        except Exception:
            head = "%PDF"
        return head + "\n[END OF FILE]", len(b)

    hex_preview = b[: min(len(b), limit)].hex()
    return hex_preview + "\n[END OF FILE]", len(b)


def _clean_text(val: Any, charset: str = "") -> str:
    if val is None:
        return ""
    if isinstance(val, (bytes, bytearray, memoryview)):
        b = val.tobytes() if isinstance(val, memoryview) else bytes(val)
        if not b:
            return ""
        candidates = []
        if b.count(0) >= max(2, len(b) // 4):
            candidates.append("utf-16le")
        for c in (charset, "cp950", "utf-8", "latin-1"):
            if c and c not in candidates:
                candidates.append(c)
        for enc in candidates:
            try:
                s = b.decode(enc, errors="ignore")
                break
            except Exception:
                s = ""
        else:
            s = ""
    else:
        s = str(val)
    return "".join(ch for ch in s if ch in ("\n", "\r", "\t") or ord(ch) >= 32)


def _blob_full_base64(blob: Any) -> Tuple[str, str, int]:
    if blob is None:
        return "", "", 0
    if isinstance(blob, memoryview):
        b = blob.tobytes()
    elif isinstance(blob, bytearray):
        b = bytes(blob)
    elif isinstance(blob, bytes):
        b = blob
    else:
        try:
            b = bytes(blob)
        except Exception:
            return "", "", 0
    if not b:
        return "", "", 0
    b64 = base64.b64encode(b).decode("ascii")
    sha256 = hashlib.sha256(b).hexdigest()
    return b64, sha256, len(b)

def _contains_sub(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return "\u001a" in val
    if isinstance(val, (bytes, bytearray, memoryview)):
        b = val.tobytes() if isinstance(val, memoryview) else bytes(val)
        return b.find(b"\x1a") >= 0
    if isinstance(val, dict):
        return any(_contains_sub(v) for v in val.values())
    if isinstance(val, (list, tuple)):
        return any(_contains_sub(v) for v in val)
    return _contains_sub(str(val))


def _mask_secret(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 4:
        return "*" * len(val)
    return val[:2] + "*" * (len(val) - 4) + val[-2:]


def _rows_to_lists(rows):
    out = []
    for r in rows or []:
        try:
            out.append(list(r))
        except Exception:
            out.append([str(r)])
    return out


def _row_get(row: Any, idx: int, key: str):
    try:
        if hasattr(row, "_mapping"):
            m = row._mapping
            if key in m:
                return m.get(key)
            k2 = key.upper()
            if k2 in m:
                return m.get(k2)
            k3 = key.lower()
            if k3 in m:
                return m.get(k3)
    except Exception:
        pass
    try:
        return row[idx]
    except Exception:
        return ""


def _first_row_value(rows, idx: int = 0) -> str:
    if not rows:
        return ""
    r = rows[0]
    try:
        if hasattr(r, "_mapping"):
            vals = list(r._mapping.values())
            return str(vals[idx]) if vals else ""
    except Exception:
        pass
    try:
        return str(r[idx])
    except Exception:
        return ""


def _oracle_emp_lookup(emp_id: str) -> str:
    if not emp_id:
        return ""
    if db_query_all is None:
        return ""
    try:
        rows = db_query_all("oracle", SQL_ORA_EMP, {"emp_id": emp_id}) or []
        return _first_row_value(rows, 0).strip()
    except Exception:
        return ""


def _sybase_query_all(sql: str, params: list | tuple | None = None):
    """
    Sybase 專用：強制拉大 TEXTSIZE，避免 EF_DATA/DF_DATA 被 32KB 截斷。
    每次 query 使用同一連線先執行 SET TEXTSIZE。
    """
    if db_connect is None:
        raise RuntimeError("db driver unavailable: please install pyodbc and configure DB env")
    conn = db_connect("sybase")
    cur = None
    try:
        cur = conn.cursor()
        # ASE/ODBC: default TEXTSIZE 32KB，需手動放大
        cur.execute("set textsize 2147483647")
        cur.execute(sql, params or [])
        return list(cur.fetchall())
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            try:
                conn.close()
            except Exception:
                pass


def _oracle_acl_lookup(username: str, env_map: Dict[str, str]) -> Dict[str, Any]:
    table = (env_map.get("ORA_ACL_TABLE") or "VIEW_ZZ_USER_GROUP_ACL").strip()
    user_col = (env_map.get("ORA_ACL_USER_COL") or "USERNAME").strip()
    group_col = (env_map.get("ORA_ACL_GROUP_COL") or "GROUP_NAME").strip()
    sql = f"SELECT {group_col} AS GROUP_NAME FROM {table} WHERE {user_col} = :username"
    groups: List[str] = []
    if db_query_all is None:
        return {
            "table": table,
            "user_col": user_col,
            "group_col": group_col,
            "groups": groups,
        }
    try:
        rows = db_query_all("oracle", sql, {"username": username}) or []
        for r in rows:
            try:
                if hasattr(r, "_mapping"):
                    v = r._mapping.get("GROUP_NAME")
                else:
                    v = r[0]
                if v:
                    groups.append(str(v))
            except Exception:
                continue
    except Exception:
        groups = []
    return {
        "table": table,
        "user_col": user_col,
        "group_col": group_col,
        "groups": groups,
    }


def _make_attach_key(ef_id_val: str, ef_page_val: Any) -> str:
    page = str(ef_page_val or "").strip()
    base = str(ef_id_val or "").strip()
    return f"EF:{base}@{page}" if page else f"EF:{base}"


def _dedupe_rows_by_key(rows: List[Any], key_fn):
    out: List[Any] = []
    seen = set()
    dropped = 0
    for i, r in enumerate(rows or []):
        try:
            k = key_fn(r)
        except Exception:
            k = ("__ERR__", i)
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        out.append(r)
    return out, {
        "input_count": len(rows or []),
        "output_count": len(out),
        "dropped_count": dropped,
    }


def _dedupe_left_join_rows1(rows: List[Any], charset: str = ""):
    def _key(r: Any):
        ef_name = _row_get(r, 4, "EF_NAME")
        ef_data_len = _row_get(r, 6, "EF_DATA_LEN")
        # blob-level dedupe key: EF_NAME + EF_DATA_LEN
        return (
            _clean_text(ef_name, charset).strip(),
            int(ef_data_len or 0),
        )

    return _dedupe_rows_by_key(rows, _key)


def _dedupe_left_join_rows5(rows: List[Any], charset: str = ""):
    def _key(r: Any):
        df_name = _row_get(r, 8, "DF_NAME")
        df_data_len = _row_get(r, 10, "DF_DATA_LEN")
        ef_name = _row_get(r, 12, "EF_NAME")
        ef_data_len = _row_get(r, 14, "EF_DATA_LEN")
        # blob-level dedupe key: EF_NAME + EF_DATA_LEN + DF_NAME + DF_DATA_LEN
        return (
            _clean_text(ef_name, charset).strip(),
            int(ef_data_len or 0),
            _clean_text(df_name, charset).strip(),
            int(df_data_len or 0),
        )

    return _dedupe_rows_by_key(rows, _key)


def _export(grsno: str, out_path: str, env_map: Dict[str, str], left_join_dedupe: bool = False) -> int:
    env_out: Dict[str, str] = {}
    for k in (
        "ENV",
        "DEV_LOGIN_USER",
        "DEV_LOGIN_NAME",
        "SYBASE_HOST",
        "SYBASE_PORT",
        "SYBASE_DB",
        "SYBASE_USER",
        "SYBASE_PASS",
        "SYBASE_CHARSET",
        "ORACLE_ENABLED",
        "ORACLE_EMP_ENABLED",
    ):
        if k in env_map:
            if k == "SYBASE_PASS":
                env_out[f"{k}_MASKED"] = _mask_secret(env_map.get(k, ""))
                env_out[f"{k}_LEN"] = str(len(env_map.get(k, "")))
            else:
                env_out[k] = env_map.get(k, "")

    if "SYBASE_CHARSET" in env_out:
        env_out["SYBASE_CHARSET"] = str(env_out["SYBASE_CHARSET"]).upper()

    login_user = env_out.get("DEV_LOGIN_USER", "")
    login_user_name = env_out.get("DEV_LOGIN_NAME", "")
    syb_charset = (env_map.get("SYBASE_CHARSET") or env_map.get("SYBASE_CHAR") or "").strip()

    rows1 = _sybase_query_all(SQL_1, [login_user, login_user, grsno]) or []
    rows2 = _sybase_query_all(SQL_2, [grsno]) or []
    rows3 = _sybase_query_all(SQL_3, [grsno]) or []
    rows4 = _sybase_query_all(SQL_4, [grsno]) or []
    rows5 = _sybase_query_all(SQL_5_OFFICIAL, [grsno]) or []
    rows1_raw_count = len(rows1)
    rows5_raw_count = len(rows5)
    left_join_dedupe_stats = {
        "enabled": bool(left_join_dedupe),
        "rows1": {"input_count": rows1_raw_count, "output_count": rows1_raw_count, "dropped_count": 0},
        "rows5": {"input_count": rows5_raw_count, "output_count": rows5_raw_count, "dropped_count": 0},
    }
    if left_join_dedupe:
        rows1, s1 = _dedupe_left_join_rows1(rows1, syb_charset)
        rows5, s5 = _dedupe_left_join_rows5(rows5, syb_charset)
        left_join_dedupe_stats["rows1"] = s1
        left_join_dedupe_stats["rows5"] = s5

    if rows1:
        try:
            r0 = rows1[0]
            if hasattr(r0, "_mapping"):
                print("[DEBUG] rows1[0] columns:", list(r0._mapping.keys()))
        except Exception:
            pass
    if rows5:
        try:
            r0 = rows5[0]
            if hasattr(r0, "_mapping"):
                print("[DEBUG] rows5[0] columns:", list(r0._mapping.keys()))
        except Exception:
            pass

    charset_queries = [
        ("server_charset", SQL_CHARSET_1),
        ("default_charset_id", SQL_CHARSET_2),
    ]
    charset_results = []
    for name, sql in charset_queries:
        try:
            rows = _sybase_query_all(sql, ()) or []
            charset_results.append({"name": name, "sql": sql.strip(), "rows": _rows_to_lists(rows)})
        except Exception as e:
            charset_results.append({"name": name, "sql": sql.strip(), "error": str(e)})

    def row_to_dict(row):
        try:
            return dict(row._mapping)
        except AttributeError:
            keys = [col[0] for col in row.description] if hasattr(row, "description") else []
            values = list(row) if isinstance(row, tuple) or isinstance(row, list) else []
            return dict(zip(keys, values))

    attachments = []
    for r in rows1:
        grsno_val = _row_get(r, 0, "IM_GRSNO")
        if not grsno_val:
            grsno_val = _row_get(r, 0, "EM_GRSNO")
        psid_val = _row_get(r, 1, "IM_PSID")
        if not psid_val:
            psid_val = _row_get(r, 1, "EM_PSID")
        td_subj = _row_get(r, 2, "TD_SUBJ")
        ef_id = _row_get(r, 3, "EF_ID")
        ef_name = _row_get(r, 4, "EF_NAME")
        ef_data = _row_get(r, 5, "EF_DATA")
        ef_data_len = _row_get(r, 6, "EF_DATA_LEN")
        em_subj_len = _row_get(r, 7, "EM_SUBJ_LEN")
        im_subj_len = _row_get(r, 8, "IM_SUBJ_LEN")
        ef_name_len = _row_get(r, 9, "EF_NAME_LEN")
        ef_page = _row_get(r, 10, "EF_PAGE")

        if not psid_val:
            psid_val = login_user

        if not ef_id:
            continue

        preview, decoded_len = _blob_to_text_preview(ef_data, 1000)
        ef_data_b64, ef_data_sha256, ef_data_len_b64 = _blob_full_base64(ef_data)
        td_subj_clean = _clean_text(td_subj, syb_charset)
        ef_name_clean = _clean_text(ef_name, syb_charset)
        attachments.append(
            {
                "em_grsno": grsno_val,
                "em_psid": psid_val,
                "im_grsno": grsno_val,
                "im_psid": psid_val,
                "td_subj": td_subj_clean,
                "ef_id": ef_id,
                "ef_name": ef_name_clean,
                "ef_name_len": ef_name_len,
                "ef_page": ef_page,
                "ef_data_len": ef_data_len,
                "em_subj_len": em_subj_len,
                "im_subj_len": im_subj_len,
                "tm_subj_len": im_subj_len,  # backward-compatible key for mock parser
                "ef_data_b64": ef_data_b64,
                "ef_data_sha256": ef_data_sha256,
                "ef_data_len_b64": ef_data_len_b64,
                "ef_data_len_match": (int(ef_data_len or 0) == int(ef_data_len_b64 or 0)),
                "blob_preview_text": preview,
                "blob_decoded_text_len": decoded_len,
            }
        )

    mock_attachments = []
    for a in attachments:
        filename = _clean_text(a.get("ef_name") or "", syb_charset) or str(a.get("ef_id") or "").strip() or "attachment.bin"
        mock_attachments.append(
            {
                "attach_key": _make_attach_key(a.get("ef_id"), a.get("ef_page")),
                "filename": filename,
                "page": a.get("ef_page") or "",
                "source": "EF",
            }
        )

    subject = ""
    if attachments:
        subject = _clean_text(attachments[0].get("td_subj") or attachments[0].get("ef_name") or "", syb_charset)
    if not subject:
        subject = grsno
    mock_items = [
        {
            "grsno": grsno,
            "im_grsno": grsno,
            "tm_grsno": grsno,
            "im_psid": login_user,
            "tm_psid": login_user,
            "td_subj": subject,
            "subject": subject,
            "attachments": mock_attachments,
        }
    ]

    # Official docs (DCS3 + DCS0/DF + optional EF)
    official_docs = []
    df_files: List[Dict[str, Any]] = []
    for r in rows5:
        tm_grsno = _row_get(r, 0, "TM_GRSNO")
        tm_rstp = _row_get(r, 1, "TM_RSTP")
        td_format = _row_get(r, 2, "TD_FORMAT")
        td_subj = _row_get(r, 3, "TD_SUBJ")
        tm_date = _row_get(r, 4, "TM_DATE")
        tm_psid = _row_get(r, 5, "TM_PSID")
        tm_name = _row_get(r, 6, "TM_NAME")
        td_path = _row_get(r, 7, "TD_PATH")
        df_name = _row_get(r, 8, "DF_NAME")
        df_data = _row_get(r, 9, "DF_DATA")
        df_data_len = _row_get(r, 10, "DF_DATA_LEN")
        ef_id = _row_get(r, 11, "EF_ID")
        ef_name = _row_get(r, 12, "EF_NAME")
        ef_data = _row_get(r, 13, "EF_DATA")
        ef_data_len = _row_get(r, 14, "EF_DATA_LEN")
        ef_page = _row_get(r, 15, "EF_PAGE")

        df_b64, df_sha256, df_len_b64 = _blob_full_base64(df_data)
        ef_b64, ef_sha256, ef_len_b64 = _blob_full_base64(ef_data)

        td_path_norm = str(_clean_text(td_path, syb_charset) or "").strip()
        ef_id_norm = str(_clean_text(ef_id, syb_charset) or "").strip()
        ef_page_norm = str(_clean_text(ef_page, syb_charset) or "").strip()
        td_subj_norm = str(_clean_text(td_subj, syb_charset) or "").strip()
        df_name_norm = str(_clean_text(df_name, syb_charset) or "").strip()

        official_docs.append(
            {
                "tm_grsno": _clean_text(tm_grsno, syb_charset),
                "tm_rstp": _clean_text(tm_rstp, syb_charset),
                "td_format": _clean_text(td_format, syb_charset),
                "td_subj": td_subj_norm,
                "tm_date": _clean_text(tm_date, syb_charset),
                "tm_psid": _clean_text(tm_psid, syb_charset),
                "tm_name": _clean_text(tm_name, syb_charset),
                "td_path": td_path_norm,
                "df_name": df_name_norm,
                "df_data_len": df_data_len,
                "df_data_b64": df_b64,
                "df_data_sha256": df_sha256,
                "df_data_len_b64": df_len_b64,
                "df_data_len_match": (int(df_data_len or 0) == int(df_len_b64 or 0)),
                "ef_id": ef_id_norm,
                "ef_name": _clean_text(ef_name, syb_charset),
                "ef_page": ef_page_norm,
                "ef_data_len": ef_data_len,
                "ef_data_b64": ef_b64,
                "ef_data_sha256": ef_sha256,
                "ef_data_len_b64": ef_len_b64,
                "ef_data_len_match": (int(ef_data_len or 0) == int(ef_len_b64 or 0)),
            }
        )

        if td_path_norm:
            df_files.append(
                {
                "df_path": td_path_norm,
                "df_name": df_name_norm,
                "df_data_len": df_data_len,
                "df_data_b64": df_b64,
                "df_data_sha256": df_sha256,
                "df_data_len_b64": df_len_b64,
                "df_data_len_match": (int(df_data_len or 0) == int(df_len_b64 or 0)),
                }
            )

    # Fallback: synthesize official docs from attachments when DCS3 has no rows
    if not official_docs and attachments:
        formats = ["簽呈", "令", "呈", "函", "便籤"]
        for i, a in enumerate(attachments):
            fmt = formats[i % len(formats)]
            td_subj = a.get("td_subj") or a.get("ef_name") or grsno
            td_path = f"DFPATH:{grsno}:{i + 1}"
            ef_id = a.get("ef_id") or ""
            ef_name = a.get("ef_name") or ""
            ef_page = a.get("ef_page") or ""
            ef_b64 = a.get("ef_data_b64") or ""
            ef_sha256 = a.get("ef_data_sha256") or ""
            data_len = a.get("ef_data_len") or 0
            data_len_b64 = a.get("ef_data_len_b64") or 0

            official_docs.append(
                {
                    "tm_grsno": grsno,
                    "tm_rstp": "簽呈",
                    "td_format": fmt,
                    "td_subj": _clean_text(td_subj, syb_charset),
                    "tm_date": datetime.now().isoformat(timespec="seconds"),
                    "tm_psid": login_user,
                    "tm_name": login_user_name,
                    "td_path": td_path,
                    "df_name": _clean_text(ef_name, syb_charset) or f"{fmt}_{i + 1}.pdf",
                    "df_data_len": data_len,
                    "df_data_b64": ef_b64,
                    "df_data_sha256": ef_sha256,
                    "df_data_len_b64": data_len_b64,
                    "df_data_len_match": (int(data_len or 0) == int(data_len_b64 or 0)),
                    "ef_id": _clean_text(ef_id, syb_charset),
                    "ef_name": _clean_text(ef_name, syb_charset),
                    "ef_page": _clean_text(ef_page, syb_charset),
                    "ef_data_len": data_len,
                    "ef_data_b64": ef_b64,
                    "ef_data_sha256": ef_sha256,
                    "ef_data_len_b64": data_len_b64,
                    "ef_data_len_match": (int(data_len or 0) == int(data_len_b64 or 0)),
                }
            )

        for d in official_docs:
            td_path = d.get("td_path") or ""
            if td_path:
                df_files.append(
                    {
                    "df_path": td_path,
                    "df_name": d.get("df_name") or "",
                    "df_data_len": d.get("df_data_len") or 0,
                    "df_data_b64": d.get("df_data_b64") or "",
                    "df_data_sha256": d.get("df_data_sha256") or "",
                    "df_data_len_b64": d.get("df_data_len_b64") or 0,
                    "df_data_len_match": bool(d.get("df_data_len_match")),
                    }
                )

    oracle_emp_name = _oracle_emp_lookup(login_user) or login_user_name
    oracle_acl = _oracle_acl_lookup(login_user, env_map)

    record = {
        "meta": {
            "grsno": grsno,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "env": env_out.get("ENV", ""),
            "left_join_dedupe": left_join_dedupe_stats,
        },
        "env": env_out,
        "oracle_emp": {
            "login_user": login_user,
            "login_user_name": oracle_emp_name,
        },
        "oracle_acl": oracle_acl,
        "acl_simple": {
            "allowed": bool(oracle_acl.get("groups")),
            "groups": oracle_acl.get("groups", []),
        },
        "sybase_charset": {"queries": charset_results},
        "queries": {
            "q1": {"sql": SQL_1.strip(), "rows_count": len(rows1), "rows_raw_count": rows1_raw_count},
            "q2": {"sql": SQL_2.strip(), "rows": [row_to_dict(row) for row in rows2] if rows2 else []},
            "q3": {"sql": SQL_3.strip(), "rows": [row_to_dict(row) for row in rows3] if rows3 else []},
            "q4": {"sql": SQL_4.strip(), "rows": [row_to_dict(row) for row in rows4] if rows4 else []},
            "q5": {"sql": SQL_5_OFFICIAL.strip(), "rows_count": len(rows5), "rows_raw_count": rows5_raw_count},
        },
        "attachments": attachments,
        "official_docs": official_docs,
        "df_files": df_files,
        "mock_api": {
            "incoming_lookup": {
                "ok": True,
                "items": mock_items,
                "meta": {
                    "login_user": login_user,
                    "grsno": grsno,
                    "im_grsno": grsno,
                    "tm_grsno": grsno,
                    "rows_total": len(mock_items),
                },
            },
            "incoming_files": {
                "ok": True,
                "grsno": grsno,
                "im_grsno": grsno,
                "tm_grsno": grsno,
                "attachments": mock_attachments,
                "items": mock_items,
            },
            "incoming_file_examples": [
                {
                    "attach_key": _make_attach_key(a.get("ef_id"), a.get("ef_page")),
                    "filename": a.get("ef_name") or "",
                    "data_len": a.get("ef_data_len") or 0,
                    "content_type_hint": "application/pdf",
                }
                for a in attachments
            ],
        },
    }
    has_sub = _contains_sub(record)
    record["meta"]["has_sub_0x1a"] = bool(has_sub)
    if has_sub:
        print("[WARN] Detected \\u001a (SUB) in output; DB likely contains corrupted data.")
    # append record to existing JSON (multi-record)
    existing = {}
    records = []
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                existing = json.load(f) or {}
            if isinstance(existing.get("records"), list):
                records = existing.get("records")
        except Exception:
            existing = {}
            records = []

    records.append(record)

    out = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "env": env_out.get("ENV", ""),
            "records_count": len(records),
        },
        "env": env_out,
        "records": records,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote: {out_path}")
    return 0


def _simulate(json_path: str, login_user: str, node: str, grsno: str) -> int:
    if not os.path.exists(json_path):
        print(f"JSON not found: {json_path}")
        return 2

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records") if isinstance(data.get("records"), list) else []
    record = data.get("latest") or (records[-1] if records else data)
    if grsno and records:
        for r in records:
            if str((r.get("meta") or {}).get("grsno") or "") == str(grsno):
                record = r
                break

    emp = record.get("oracle_emp", {}) or {}
    acl = record.get("oracle_acl", {}) or {}
    acl_simple = record.get("acl_simple", {}) or {}
    meta = record.get("meta", {}) or {}

    use_user = login_user or emp.get("login_user") or ""
    user_name = emp.get("login_user_name") or ""
    groups = acl.get("groups", []) if isinstance(acl.get("groups", []), list) else []
    allowed = bool(groups)

    if acl_simple.get("allowed") in (True, False):
        allowed = bool(acl_simple.get("allowed"))

    print("[SIM] login_user:", use_user)
    print("[SIM] login_user_name:", user_name)
    print("[SIM] oracle_acl_groups:", groups)
    if node:
        print(f"[SIM] ACL simple check for node={node}: {allowed}")

    if grsno:
        meta_grsno = str(meta.get("grsno") or "")
        ok = (meta_grsno == grsno)
        print(f"[SIM] sybase grsno match: {ok} (json={meta_grsno}, input={grsno})")
        attachments = record.get("attachments", []) or []
        print(f"[SIM] attachments: {len(attachments)}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLTEST export/simulate for EXT")
    parser.add_argument("grsno", nargs="?", help="EM_GRSNO / TM_GRSNO")
    parser.add_argument("--grsno", dest="grsno_opt", default="", help="EM_GRSNO / TM_GRSNO (optional named arg)")
    parser.add_argument("--out", default="SQLTEST_output.json", help="output JSON path")
    parser.add_argument("--json", default="SQLTEST_output.json", help="input JSON path for simulate")
    parser.add_argument("--simulate", action="store_true", help="simulate mode (EXT) using JSON")
    parser.add_argument("--login_user", default="", help="login_user for simulate")
    parser.add_argument("--node", default="doc", help="ACL node name for simulate")
    parser.add_argument("--left_join_dedupe", action="store_true", help="dedupe rows expanded by LEFT JOIN (SQL_1/SQL_5)")
    args = parser.parse_args()
    use_grsno = (args.grsno_opt or args.grsno or "").strip()

    env_map = _load_env_map()
    env_name = (env_map.get("ENV") or "").strip().upper()
    env_lj_dedupe = str(env_map.get("SQLTEST_LEFT_JOIN_DEDUPE") or "").strip().lower() in ("1", "true", "yes", "on")
    use_left_join_dedupe = bool(args.left_join_dedupe or env_lj_dedupe)

    if args.simulate or env_name == "EXT":
        return _simulate(args.json, args.login_user, args.node, use_grsno)

    if not use_grsno:
        print("Usage: python SQLTEST.py <EM_GRSNO>")
        return 2

    if db_connect is None:
        print("DB driver unavailable. Install pyodbc in this runtime before export.")
        return 2

    return _export(use_grsno, args.out, env_map, left_join_dedupe=use_left_join_dedupe)


if __name__ == "__main__":
    raise SystemExit(main())

# 使用方式
# 內網產生 JSON：產生的 JSON 改為多筆累積
# H:\AI\AI_TOOLS\venv3.12\Scripts\python.exe H:\AI\AI_TOOLS\SQLtest.py 1150001261 --out SQLTEST_output.json
# H:\AI\AI_TOOLS\venv3.12\Scripts\python.exe H:\AI\AI_TOOLS\SQLtest.py 1150000712 --out SQLTEST_output.json


# 外網模擬（ENV=EXT 或加 --simulate）：
# H:\AI\AI_TOOLS\venv3.12\Scripts\python.exe H:\AI\AI_TOOLS\SQLtest.py --simulate --json SQLTEST_output.json --login_user A123456789 --node doc --grsno 1150001261
 

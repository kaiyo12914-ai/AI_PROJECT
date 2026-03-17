# webapps/excelproc/services.py
from __future__ import annotations

import os
import re
from io import BytesIO
from typing import Dict, Any, List, Optional, Union

import pandas as pd
import oracledb  # ✅ 只用來抓錯誤型別/錯誤碼（不再自己 connect）

from webapps.database.db_factory import db_connect  # ✅ 統一由 DBFactory 建立連線


DEFAULT_TEL_FILE = "MPC電話表.xls"
DEFAULT_CONTACT_FILE = "單位人員連絡冊.xlsx"
DEFAULT_EXPORT_FILE = "中心計資組人事資訊.xlsx"

ALLOWED_EXTS = {".xlsx", ".xls", ".xlsm"}
ExcelInput = Union[str, BytesIO]


# ============================================================
# Excel helpers
# ============================================================
def _read_excel_safely_any(excel: ExcelInput, *, filename: str = "", dtype: Optional[type] = None) -> pd.DataFrame:
    if isinstance(excel, str):
        ext = os.path.splitext(excel)[1].lower()
    else:
        ext = os.path.splitext(filename or "")[1].lower()

    if ext not in ALLOWED_EXTS:
        raise ValueError(f"僅支援 Excel 檔：{', '.join(sorted(ALLOWED_EXTS))}")

    if ext == ".xls":
        return pd.read_excel(excel, dtype=dtype, engine="xlrd")
    return pd.read_excel(excel, dtype=dtype, engine="openpyxl")


def _read_excel_safely(excel_path: str, *, dtype: Optional[type] = None) -> pd.DataFrame:
    return _read_excel_safely_any(excel_path, filename=excel_path, dtype=dtype)


# ============================================================
# Oracle helpers
# ============================================================
def oracle_friendly_message(code, msg: str) -> str:
    s = (msg or "").strip()
    if code in (1017,):
        return "資料庫連線失敗：帳號或密碼錯誤（ORA-01017）"
    if code in (12154,):
        return "資料庫連線失敗：無法解析服務名稱（請檢查 ORA_SERVICE_NAME / DNS / tns 解析）（ORA-12154）"
    if code in (12514,):
        return "資料庫連線失敗：Listener 找不到服務（請檢查 ORA_SERVICE_NAME）（ORA-12514）"
    if code in (12541,):
        return "資料庫連線失敗：無 Listener / Port 不通（請檢查 ORA_HOST/ORA_PORT、防火牆）（ORA-12541）"
    if code in (12545,):
        return "資料庫連線失敗：主機或服務不存在（請檢查 ORA_HOST/DNS）（ORA-12545）"
    if code in (12543,):
        return "資料庫連線失敗：目標主機無法連線（請檢查網路/防火牆）（ORA-12543）"

    if code:
        return f"資料庫連線失敗：ORA-{code} {s}"
    return f"資料庫連線失敗：{s or '未知錯誤'}"


def get_conn():
    """
    ✅ 統一由 db_factory 建立連線（符合你的專案規範）
    - 你 db_factory 內部會讀 .env / ENV_PATH / pyodbc/oracle 等設定
    """
    try:
        return db_connect("oracle")
    except Exception as e:
        # 盡量把 Oracle Error 轉成友善訊息
        if isinstance(e, oracledb.Error):
            err = e.args[0] if e.args else None
            code = getattr(err, "code", None)
            msg = getattr(err, "message", None) or str(e)
            raise RuntimeError(oracle_friendly_message(code, msg))
        raise RuntimeError(f"資料庫連線失敗：{e}")


# ============================================================
# Cleaners
# ============================================================
def clean_phone(phone_str):
    if pd.isna(phone_str) or not phone_str:
        return ""
    str_val = str(phone_str).strip()
    try:
        if "e" in str_val.lower():
            num_value = float(str_val)
            return f"{num_value:.0f}"[:20]
        elif "." in str_val:
            integer_part, *_ = str_val.split(".")
            return clean_phone(integer_part)[:20]
    except ValueError:
        pass
    cleaned = "".join(re.findall(r"\d+", str_val))
    return cleaned[:10]


def process_value(value):
    if pd.isna(value) or value is None:
        return ""
    try:
        if isinstance(value, float) and "e" in str(value).lower():
            num_value = float(str(value))
            return clean_phone(f"{num_value:.0f}")
        elif isinstance(value, float):
            return f"{int(value)}"
    except ValueError:
        pass

    if isinstance(value, (str, int)):
        return str(value).strip()
    try:
        return str(float(value)).strip()
    except (ValueError, TypeError):
        return ""


def clean_name(name):
    if pd.isna(name) or not name:
        return ""
    has_chinese = any(char in '。，、；：？（）《》“”【】{}[]<>;:?"' for char in str(name))
    if has_chinese:
        return str(name).replace(" ", "")
    return " ".join(str(name).split())


def clean_phone_v2(phone_str):
    if pd.isna(phone_str) or not phone_str:
        return ""
    cleaned = "".join(re.findall(r"\d+", str(phone_str)))
    if "." in str(phone_str):
        integer_part = cleaned.split(".")[0]
    else:
        integer_part = cleaned
    return (integer_part + "0" * 6)[:6]


# ============================================================
# 保留：若你其他地方還在呼叫也不會壞
# ============================================================
def update_db_name(name, phone) -> bool:
    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT INNERTELE, NAME FROM CT_EMPLOY WHERE TRIM(NAME) = :name_param",
            name_param=name,
        )
        db_result = cursor.fetchone()
        if not db_result:
            return False

        cursor.execute(
            "UPDATE CT_EMPLOY SET INNERTELE = :phone_param WHERE TRIM(NAME) = :name_param",
            phone_param=phone,
            name_param=name,
        )
        cursor.execute(
            "UPDATE CT_EMPLOY_SIMPLE SET INNERTELE = :phone_param WHERE TRIM(NAME) = :name_param",
            phone_param=phone,
            name_param=name,
        )
        conn.commit()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except Exception:
            pass


# ============================================================
# ✅ 不落地：回傳 bytes
# ============================================================
def import_contact_data_bytes(excel_bytes: bytes, *, filename: str = DEFAULT_CONTACT_FILE) -> Dict[str, Any]:
    try:
        excel_df = _read_excel_safely_any(BytesIO(excel_bytes), filename=filename, dtype=str)

        conn = get_conn()
        results: List[Dict[str, str]] = []
        cursor = conn.cursor()

        update_sql = """
            UPDATE CT_EMPLOY SET
                IDNO = :id,
                NAME = :name,
                ADRSS = :adrss,
                TELNO = TO_CHAR(:telno),
                HANDTELE = TO_CHAR(:handtele),
                CNTPSN = :cntpsn,
                CHTELNO = TO_CHAR(:chtele),
                CARNO = :carno,
                MOTONO = :motono,
                BLOODTYPE = :bloodtype,
                ENGLISH_NAME = :english_name
            WHERE IDNO = :id
        """

        try:
            for index, row in excel_df.iterrows():
                data = {
                    "id": process_value(row.get("ID", "")),
                    "name": process_value(row.get("姓名", "")),
                    "adrss": process_value(row.get("住址", ""))[:250],
                    "telno": clean_phone(process_value(row.get("電話", ""))) if "電話" in row else "",
                    "handtele": clean_phone(process_value(row.get("手機", ""))) if "手機" in row else "",
                    "cntpsn": process_value(row.get("連絡人", ""))[:100],
                    "chtele": clean_phone(process_value(row.get("連絡電話", ""))) if "連絡電話" in row else "",
                    "carno": process_value(row.get("汽車車號", ""))[:20],
                    "motono": process_value(row.get("機車車號", ""))[:20],
                    "bloodtype": process_value(row.get("血型", ""))[:20],
                    "english_name": process_value(row.get("英文姓名", ""))[:20],
                }

                if not data["id"]:
                    results.append({"ID": "", "姓名": data["name"], "結果": f"第 {index+1} 筆缺少ID，已跳過"})
                    continue

                cursor.execute("SELECT COUNT(*) FROM CT_EMPLOY WHERE IDNO = :id", id=data["id"])
                exists = cursor.fetchone()[0] > 0

                row_result = {"ID": data["id"], "姓名": data["name"], "結果": ""}

                if not exists:
                    row_result["結果"] = "ID不存在"
                    results.append(row_result)
                    continue

                try:
                    cursor.execute(update_sql, data)
                    row_result["結果"] = "更新成功"
                except oracledb.DatabaseError as e:
                    err = e.args[0] if e.args else None
                    code = getattr(err, "code", None)
                    msg = getattr(err, "message", None) or str(e)
                    if code == 2049:
                        row_result["結果"] = "更新失敗（欄位值過長）"
                    else:
                        row_result["結果"] = f"更新失敗（ORA-{code} {msg}）" if code else f"更新失敗（{msg}）"
                        conn.rollback()

                results.append(row_result)

            conn.commit()
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass

        out = BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            pd.DataFrame(results).to_excel(writer, sheet_name="更新結果", index=False)
            excel_df.to_excel(writer, sheet_name="原始資料", index=False)
        out.seek(0)
        return {"ok": True, "filename": "匯入資料更新結果.xlsx", "content": out.getvalue()}

    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"匯入失敗：{e!r}"}


def compare_data_bytes(excel_bytes: bytes, *, filename: str = DEFAULT_TEL_FILE) -> Dict[str, Any]:
    output_list: List[Dict[str, Any]] = []

    try:
        excel_df = _read_excel_safely_any(BytesIO(excel_bytes), filename=filename)

        conn = get_conn()
        cursor = conn.cursor()

        try:
            for index in range(1, len(excel_df)):
                row_data = excel_df.iloc[index]

                for i in [1, 4, 7, 10, 13]:
                    level_col = excel_df.columns[i - 1] if (i - 1) < len(excel_df.columns) else None
                    name_col = excel_df.columns[i] if i < len(excel_df.columns) else None
                    phone_col = excel_df.columns[i + 1] if (i + 1) < len(excel_df.columns) else None
                    if not all([level_col, name_col, phone_col]):
                        continue

                    level = process_value(row_data[level_col]) if pd.notna(row_data[level_col]) else ""
                    raw_name = process_value(row_data[name_col]) if pd.notna(row_data[name_col]) else ""
                    name = clean_name(raw_name) if raw_name else ""
                    phone = clean_phone_v2(row_data[phone_col]) if pd.notna(row_data[phone_col]) else ""

                    if not name:
                        continue

                    cursor.execute(
                        """
                        SELECT INNERTELE, NAME
                        FROM CT_EMPLOY
                        WHERE TRIM(NAME) = :name_param
                        """,
                        name_param=name,
                    )
                    db_result = cursor.fetchone()

                    if db_result:
                        db_phone = str(db_result[0]) if db_result[0] else ""
                        db_name = db_result[1] or ""

                        if name == db_name and phone and phone != db_phone:
                            cursor.execute(
                                "UPDATE CT_EMPLOY SET INNERTELE = :p WHERE TRIM(NAME) = :n",
                                p=phone, n=name,
                            )
                            cursor.execute(
                                "UPDATE CT_EMPLOY_SIMPLE SET INNERTELE = :p WHERE TRIM(NAME) = :n",
                                p=phone, n=name,
                            )

                        output_list.append({
                            "階級": level,
                            "附件姓名": name,
                            "DB姓名": db_name if db_name else "無此人",
                            "附件電話": phone,
                            "DB電話": db_phone if db_phone else "未找到",
                            "比對狀態": "相符" if str(phone).isdigit() and phone == db_phone else "不相符",
                        })
                    else:
                        output_list.append({
                            "階級": level,
                            "附件姓名": name,
                            "DB姓名": "無此人",
                            "附件電話": phone,
                            "DB電話": "未找到",
                            "比對狀態": "不相符",
                        })

            conn.commit()
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass

        out = BytesIO()
        pd.DataFrame(output_list).to_excel(out, index=False)
        out.seek(0)
        return {"ok": True, "filename": "人員電話比對結果.xlsx", "content": out.getvalue()}

    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"比對失敗：{e!r}"}


def export_mpc_employee_data_bytes() -> Dict[str, Any]:
    try:
        conn = get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT
                   d.DEPT_NAME AS "單位",
                   r.RANK AS "編階",
                   j.JOB AS "職稱",
                   e.NAME AS "姓名",
                   TO_CHAR(e.DTE_BTH, 'YYYY/MM/DD') AS "生日",
                   e.IDNO AS "ID",
                   TO_CHAR(e.DTE_ARMY, 'YYYY/MM/DD') AS "入伍日期",
                   e.ADRSS AS "住址",
                   e.TELNO AS "電話",
                   e.HANDTELE AS "手機",
                   e.CNTPSN AS "連絡人",
                   e.CHTELNO AS "連絡電話",
                   e.CARNO AS "汽車車號",
                   e.MOTONO AS "機車車號",
                   s.ORDERCODE AS "ORDERCODE",
                   r.SEQ AS "ORDERSEQ"
                FROM
                   CT_EMPLOY e
                LEFT JOIN TT_DEPT_CODE d ON e.DEPTNO = d.DEPT_CODE
                LEFT JOIN CT_RANK r ON e.RNKNO = r.RNKNO
                LEFT JOIN CT_JOB j ON e.JOBNO = j.JOBNO
                LEFT JOIN CT_SPECIALID s ON e.IDNO = s.IDNO
                WHERE
                   e.SVCTNO = '00'
                   AND e.FACTORY_PLANT = 'MPC'
                   AND e.DEPTNO = 'EA'
                   AND LENGTH(TRIM(e.IDNO))=10
                ORDER BY
                   r.SEQ, s.ORDERCODE
                """
            )
            results = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            df = pd.DataFrame(results, columns=columns)

            out = BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="人員資料", index=False)
            out.seek(0)

            return {"ok": True, "filename": DEFAULT_EXPORT_FILE, "content": out.getvalue()}

        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass

    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"匯出失敗：{e!r}"}


# ============================================================
# 舊 API：保留
# ============================================================
def import_contact_data(excel_path: str) -> Dict[str, Any]:
    try:
        with open(excel_path, "rb") as f:
            b = f.read()
        return import_contact_data_bytes(b, filename=os.path.basename(excel_path) or DEFAULT_CONTACT_FILE)
    except Exception as e:
        return {"ok": False, "error": f"匯入失敗：{e!r}"}


def compare_data(excel_path: str) -> Dict[str, Any]:
    try:
        with open(excel_path, "rb") as f:
            b = f.read()
        return compare_data_bytes(b, filename=os.path.basename(excel_path) or DEFAULT_TEL_FILE)
    except Exception as e:
        return {"ok": False, "error": f"比對失敗：{e!r}"}


def export_mpc_employee_data() -> Dict[str, Any]:
    return export_mpc_employee_data_bytes()

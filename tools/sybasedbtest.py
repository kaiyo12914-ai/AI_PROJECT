# sybasedbtest.py
from __future__ import annotations

from typing import List

# ✅ 相容：若 db_factory 有 get_connection 就用；沒有就 fallback db_connect
try:
    from webapps.database.db_factory import get_connection as _get_conn  # type: ignore
except Exception:
    _get_conn = None  # type: ignore

from webapps.database.db_factory import db_connect, db_query_all


def get_connection(db_type: str):
    """
    相容舊寫法：get_connection("sybase")
    - 若 db_factory 本來就有 get_connection -> 用原本的
    - 否則 fallback db_connect
    """
    if _get_conn is not None:
        return _get_conn(db_type)  # type: ignore
    return db_connect(db_type)  # type: ignore


def get_available_drivers() -> List[str]:
    try:
        import pyodbc  # type: ignore

        return list(pyodbc.drivers())
    except Exception as e:
        return [str(e)]


def test_sybase_connection():
    try:
        # 1) 測試資料庫連線
        conn = get_connection("sybase")
        if conn:
            print("資料庫連接成功！")
            conn.close()  # 關閉連線

        # 2) 測試簡單查詢（先跑小的，快又好判斷）
        query = "SELECT TOP 1 TM_GRSNO AS 呈文文號, TM_NAME AS 承辦人姓名 FROM mnda.dbo.DCS3_TRST_MST"
        small_results = db_query_all("sybase", query)  # ✅ 參數順序修正
        if small_results:
            print("\n簡單查詢成功（TOP 1）:")
            print(small_results[0])

        # 3) 測試大查詢
        raw_query = """
            SELECT TOP 200
                TM.TM_GRSNO '呈文文號',
                CONVERT(VARCHAR(10), TM.TM_TDATE, 23) AS '呈核日',
                TM.TM_PSID '承辦人ID',
                TM.TM_NAME '承辦人姓名',
                EM.EM_GRSNO '相關號',
                TM.TM_RSTP '案別',
                TD.TD_MEMO '文稿類別',
                CASE
                    WHEN TD.TD_FORMAT NOT IN ('檔案','來文(檔案)') AND TM.TM_RSTP NOT IN ('創','會')
                    THEN EF.EF_NAME
                    ELSE TD.TD_SUBJ
                END '附件名稱',
                CASE
                    WHEN TD.TD_FORMAT NOT IN ('檔案','來文(檔案)') AND TM.TM_RSTP NOT IN ('創','會')
                    THEN EF.EF_DATA
                    ELSE DF.DF_DATA
                END '附件內容',
                TD.TD_FORMAT '簽核文件類別'
            FROM mnda.dbo.DCS3_TRST_MST TM
            LEFT JOIN mnda.dbo.DCS3_TRST_DAT TD ON TM.TM_SNO = TD.TD_SNO
            LEFT JOIN mnda.dbo.DCS0_DOC_FILE DF ON DF.DF_PATH = TD.TD_PATH
            LEFT JOIN mnda.dbo.DCS1_EMAL_TMP EM ON TM.TM_GRSNO = EM.EM_GRSNO
            LEFT JOIN mnda.dbo.DCS1_EMAL_FILE EF ON EM.EM_FID = EF.EF_ID
            WHERE TM.TM_RSTP in ('收')
              AND TM.TM_TDATE >= DATEADD(DAY, -1, GETDATE())  -- 最近1天內的資料
        """

        results = db_query_all("sybase", raw_query)  # ✅ 參數順序修正

        if results:
            print(f"\n查詢成功，返回 {len(results)} 行數據")
            for i, row in enumerate(results[:2]):  # 只顯示前兩行
                print(f"\n第 {i+1} 筆記錄:")
                print(row)
        else:
            print("\n查詢成功，但沒有資料（0 rows）")

    except Exception as e:
        msg = str(e)
        print("\n連接或查詢失敗:", msg)

        # 常見 driver/DSN 問題
        if "pyodbc" in msg.lower() or "im002" in msg.lower() or "driver" in msg.lower():
            print("可能是 ODBC 驅動/DSN 問題")
            print("請確認已安裝 Sybase ODBC 驅動，或設定正確 SYBASE_DRIVER / SYBASE_DSN")
            print(f"安裝的 ODBC 驅動有: {get_available_drivers()}")

        # 常見 timeout / 網路
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            print("連接超時，可能是網路問題 / 防火牆 / 主機或 port 不通 / 伺服器忙碌")

        # 常見登入失敗
        if "login failed" in msg.lower() or "password" in msg.lower():
            print("登入失敗：請確認 SYBASE_USER / SYBASE_PASS 是否正確，或該帳號是否有權限")


if __name__ == "__main__":
    print("開始測試 Sybase 連接...")
    test_sybase_connection()

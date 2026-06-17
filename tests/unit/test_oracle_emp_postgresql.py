import pytest
from unittest.mock import MagicMock, patch
from webapps.portal import oracle_emp


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    # 強制將 ENV 設為 EXT，以便 _is_oracle_emp_enabled() 回傳 False
    monkeypatch.setenv("ENV", "EXT")
    # 確保每次測試前快取都是乾淨的
    oracle_emp.clear_cache()


def test_pg_query_one_param_conversion():
    # 測試 _pg_query_one 是否能正確將 Oracle 的 :var 參數轉換成 PostgreSQL 的 %(var)s 格式
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    
    # 模擬資料庫傳回欄位 description 與資料
    mock_cur.description = [("emp_name", None)]
    mock_cur.fetchone.return_value = ("張三",)

    with patch("webapps.portal.oracle_emp.db_connect", return_value=mock_conn) as mock_connect:
        sql = "SELECT NAME AS EMP_NAME FROM CT_EMPLOY WHERE IDNO = :emp_id"
        res = oracle_emp._pg_query_one(sql, {"emp_id": "F123456789"})
        
        # 驗證傳回格式是否大寫化
        assert isinstance(res, dict)
        assert res.get("EMP_NAME") == "張三"
        
        # 驗證傳入資料庫的 SQL 參數格式是否已被正確替換成 %(emp_id)s
        mock_cur.execute.assert_called_once_with(
            "SELECT NAME AS EMP_NAME FROM CT_EMPLOY WHERE IDNO = %(emp_id)s",
            {"emp_id": "F123456789"}
        )


def test_get_emp_name_postgresql_success():
    # 測試 get_emp_name 正常從 PostgreSQL 查詢成功的流程
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.description = [("emp_name", None)]
    mock_cur.fetchone.return_value = ("李四",)

    with patch("webapps.portal.oracle_emp.db_connect", return_value=mock_conn):
        name = oracle_emp.get_emp_name("F987654321")
        assert name == "李四"


def test_get_emp_name_postgresql_fallback_to_mock():
    # 測試當 PostgreSQL 查詢失敗 (拋出 Exception) 時，是否能正確 fallback 到 Mock JSON
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    # 讓執行查詢時直接拋出連線或語法錯誤
    mock_cur.execute.side_effect = Exception("DB Connection Lost")

    # 模擬 mock JSON 回傳的資料
    mock_emp_data = {"name": "王五", "plant": "HQ"}

    with patch("webapps.portal.oracle_emp.db_connect", return_value=mock_conn):
        with patch("webapps.portal.oracle_emp._mock_emp_info", return_value=mock_emp_data) as mock_info:
            name = oracle_emp.get_emp_name("F999999999")
            # 應成功 fallback 並取得王五
            assert name == "王五"
            mock_info.assert_called_once_with("F999999999")


def test_get_emp_full_info_postgresql_success():
    # 測試 get_emp_full_info 正常從 PostgreSQL 查詢成功的流程
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.description = [
        ("emp_name", None),
        ("plant", None),
        ("dept", None),
        ("title", None),
    ]
    mock_cur.fetchone.return_value = ("趙六", "PLANT_A", "DEPT_B", "TITLE_C")

    with patch("webapps.portal.oracle_emp.db_connect", return_value=mock_conn):
        info = oracle_emp.get_emp_full_info("F888888888")
        assert info == {
            "EMP_NAME": "趙六",
            "PLANT": "PLANT_A",
            "DEPT": "DEPT_B",
            "TITLE": "TITLE_C"
        }

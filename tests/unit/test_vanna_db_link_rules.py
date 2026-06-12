from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from webapps.vanna.vanna_adapter import (
    build_generate_prompt,
    get_or_create_data_source,
    oracle_db_link_for_profile,
    oracle_profile_for_question,
    sql_uses_required_oracle_db_link,
)


def _oracle_source(profile: str = "ERP_MPC"):
    return SimpleNamespace(db_type="oracle", db_profile=profile)


def test_oracle_db_link_mapping_for_erp_and_cim_profiles():
    assert oracle_db_link_for_profile("ERP_MPC") == "MPCDB"
    assert oracle_db_link_for_profile("ERP_202") == "DBLT202DB"
    assert oracle_db_link_for_profile("ERP_205") == "DBLT205DB"
    assert oracle_db_link_for_profile("ERP_209") == "DBLT209DB"
    assert oracle_db_link_for_profile("ERP_401") == "DBLT401DB"
    assert oracle_db_link_for_profile("CIM_MPC") == "DBLCIMMPC"
    assert oracle_db_link_for_profile("CIM_202") == "DBLCIM202A"
    assert oracle_db_link_for_profile("CIM_205") == "DBLCIM205A"
    assert oracle_db_link_for_profile("CIM_209") == "DBLCIM209A"
    assert oracle_db_link_for_profile("CIM_401") == "DBLCIM401A"


def test_oracle_data_source_defaults_to_erp_mpc_profile():
    with patch("webapps.vanna.vanna_adapter.DataSource.objects.update_or_create") as mock_update:
        mock_update.return_value = (_oracle_source("ERP_MPC"), True)

        data_source = get_or_create_data_source(code="legacy_vanna_chroma", db_type="oracle", db_profile="")

        assert data_source.db_profile == "ERP_MPC"
        assert mock_update.call_args.kwargs["defaults"]["db_profile"] == "ERP_MPC"


def test_question_factory_format_selects_erp_profile_by_default():
    assert oracle_profile_for_question("[人事]205廠 查詢在職人員", "ERP_MPC") == "ERP_205"
    assert oracle_profile_for_question("[採購]209廠 查詢未交物料", "ERP_MPC") == "ERP_209"
    assert oracle_profile_for_question("[物料]401廠 查詢安全庫存", "ERP_MPC") == "ERP_401"
    assert oracle_profile_for_question("[人事]MPC 查詢在職人員", "ERP_202") == "ERP_MPC"


def test_question_accounting_format_selects_cim_profile():
    assert oracle_profile_for_question("[主計]MPC 查詢成本資料", "ERP_MPC") == "CIM_MPC"
    assert oracle_profile_for_question("[主計]202廠 查詢成本資料", "ERP_MPC") == "CIM_202"
    assert oracle_profile_for_question("[主計]205廠 查詢成本資料", "ERP_MPC") == "CIM_205"
    assert oracle_profile_for_question("[主計]209廠 查詢成本資料", "ERP_MPC") == "CIM_209"
    assert oracle_profile_for_question("[主計]401廠 查詢成本資料", "ERP_MPC") == "CIM_401"


def test_generate_prompt_requires_profile_db_link():
    prompt = build_generate_prompt(
        _oracle_source("ERP_209"),
        "查詢 209 廠採購資料",
        {"tables": [{"ddl": "CREATE TABLE LEGACY.PO_HEADERS (PO_NO VARCHAR2(20));"}], "examples": []},
    )

    assert "ERP_209" in prompt
    assert "DBLT209DB" in prompt
    assert "@DBLT209DB" in prompt
    assert "Oracle DB LINK 規則優先於 approved examples" in prompt


def test_generate_prompt_uses_question_specific_cim_db_link():
    prompt = build_generate_prompt(
        _oracle_source("ERP_MPC"),
        "[主計]202廠 查詢成本資料",
        {"tables": [{"ddl": "CREATE TABLE LEGACY.GL_COST (ACCT_NO VARCHAR2(20));"}], "examples": []},
    )

    assert "CIM_202" in prompt
    assert "DBLCIM202A" in prompt
    assert "@DBLCIM202A" in prompt


def test_generate_prompt_injects_schema_embedding_chunks_when_table_ddl_is_empty():
    prompt = build_generate_prompt(
        _oracle_source("ERP_202"),
        "[人事]202廠 列出前10筆員工姓名、工號與所屬單位",
        {
            "tables": [
                {
                    "schema": "LEGACY",
                    "name": "VANNA_LEGACY_DOCUMENTATION",
                    "ddl": "",
                    "columns": [],
                }
            ],
            "schema_chunks": [
                {
                    "schema": "LEGACY",
                    "name": "VANNA_LEGACY_DOCUMENTATION",
                    "chunk_type": "documentation",
                    "chunk_text": "[人事]人事主檔為CT_EMPLOY，所屬單位可關聯CT_DEPARTMENT。",
                    "distance": 0.12,
                }
            ],
            "examples": [],
        },
    )

    assert "(no schema context)" not in prompt
    assert "VANNA_LEGACY_DOCUMENTATION (documentation)" in prompt
    assert "CT_EMPLOY" in prompt
    assert "CT_DEPARTMENT" in prompt


def test_generate_prompt_injects_ddl_and_columns_context():
    prompt = build_generate_prompt(
        _oracle_source("ERP_202"),
        "[人事]202廠 查詢員工",
        {
            "tables": [
                {
                    "schema": "LEGACY",
                    "name": "CT_EMPLOY",
                    "ddl": "CREATE TABLE CT_EMPLOY (EMPNO VARCHAR2(20), NAME VARCHAR2(80));",
                    "columns": [
                        {"name": "EMPNO", "data_type": "VARCHAR2", "description": "工號"},
                        {"name": "NAME", "data_type": "VARCHAR2", "description": "姓名"},
                    ],
                }
            ],
            "schema_chunks": [],
            "examples": [],
        },
    )

    assert "CREATE TABLE CT_EMPLOY" in prompt
    assert "CT_EMPLOY (columns)" in prompt
    assert "EMPNO: VARCHAR2 工號" in prompt
    assert "NAME: VARCHAR2 姓名" in prompt


def test_generated_oracle_sql_without_required_db_link_is_blocked():
    ok, error = sql_uses_required_oracle_db_link("SELECT * FROM CT_EMPLOY", _oracle_source("ERP_MPC"))

    assert not ok
    assert "@MPCDB" in error


def test_generated_oracle_sql_with_required_db_link_passes():
    ok, error = sql_uses_required_oracle_db_link("SELECT * FROM CT_EMPLOY@MPCDB", _oracle_source("ERP_MPC"))

    assert ok
    assert error == ""


def test_generated_sql_guard_uses_question_specific_db_link():
    ok, error = sql_uses_required_oracle_db_link(
        "SELECT * FROM GL_COST@DBLCIM202A",
        _oracle_source("ERP_MPC"),
        "[主計]202廠 查詢成本資料",
    )

    assert ok
    assert error == ""

    ok, error = sql_uses_required_oracle_db_link(
        "SELECT * FROM GL_COST@MPCDB",
        _oracle_source("ERP_MPC"),
        "[主計]202廠 查詢成本資料",
    )

    assert not ok
    assert "@DBLCIM202A" in error


def test_need_more_context_does_not_require_db_link():
    ok, error = sql_uses_required_oracle_db_link("-- NEED_MORE_CONTEXT", _oracle_source("ERP_MPC"))

    assert ok
    assert error == ""


def test_extract_sql_removes_trailing_semicolon():
    from webapps.vanna.vanna_adapter import extract_sql
    assert extract_sql("SELECT * FROM emp;") == "SELECT * FROM emp"
    assert extract_sql("SELECT * FROM emp;;;") == "SELECT * FROM emp"
    assert extract_sql("SELECT * FROM emp; \n") == "SELECT * FROM emp"
    assert extract_sql("```sql\nSELECT * FROM emp;\n```") == "SELECT * FROM emp"


@patch("webapps.portal.decorators._is_authenticated_user")
@patch("webapps.portal.decorators.can_access")
@patch("webapps.vanna.api._resolve_data_source")
@patch("webapps.vanna.sql_guard.validate_sql")
@patch("webapps.database.db_factory.db_connect")
@patch("webapps.vanna.api._is_int_env")
def test_execute_api_removes_oracle_trailing_semicolon(mock_is_int, mock_connect, mock_validate, mock_resolve, mock_can_access, mock_is_auth):
    from webapps.vanna.api import execute_api
    from django.test import RequestFactory
    import json

    mock_is_auth.return_value = True
    mock_can_access.return_value = True
    mock_is_int.return_value = True
    mock_resolve.return_value = SimpleNamespace(code="test_oracle", db_type="oracle", enabled=True, db_profile="ERP_MPC")
    mock_validate.return_value = (True, "")
    
    # Mock connection and cursor
    mock_conn = mock_connect.return_value
    mock_cur = mock_conn.cursor.return_value.__enter__.return_value
    
    rf = RequestFactory()
    req = rf.post("/api/execute/", json.dumps({
        "code": "test_oracle",
        "sql": "SELECT * FROM CT_EMPLOY@MPCDB;"
    }), content_type="application/json")
    
    # 呼叫 execute_api
    resp = execute_api(req)
    assert resp.status_code == 200
    
    # 驗證傳給 cur.execute 的 SQL 是否已去除分號
    mock_cur.execute.assert_called_once_with("SELECT * FROM CT_EMPLOY@MPCDB")


@patch("webapps.portal.decorators._is_authenticated_user")
@patch("webapps.portal.decorators.can_access")
@patch("webapps.vanna.api._resolve_data_source")
@patch("webapps.vanna.sql_guard.validate_sql")
@patch("webapps.database.db_factory.db_connect")
@patch("webapps.vanna.api._is_int_env")
@patch("webapps.vanna.api.is_vanna_admin")
def test_admin_sql_execute_api_removes_oracle_trailing_semicolon(mock_is_admin, mock_is_int, mock_connect, mock_validate, mock_resolve, mock_can_access, mock_is_auth):
    from webapps.vanna.api import admin_sql_execute_api
    from django.test import RequestFactory
    import json

    mock_is_auth.return_value = True
    mock_can_access.return_value = True
    mock_is_int.return_value = True
    mock_is_admin.return_value = True
    mock_resolve.return_value = SimpleNamespace(code="test_oracle", db_type="oracle", enabled=True, db_profile="ERP_MPC")
    mock_validate.return_value = (True, "")
    
    # Mock connection and cursor
    mock_conn = mock_connect.return_value
    mock_cur = mock_conn.cursor.return_value.__enter__.return_value
    
    rf = RequestFactory()
    req = rf.post("/api/vanna/admin-sql-execute/", json.dumps({
        "code": "test_oracle",
        "sql": "SELECT * FROM CT_EMPLOY@MPCDB;"
    }), content_type="application/json")
    
    # 呼叫 admin_sql_execute_api
    resp = admin_sql_execute_api(req)
    assert resp.status_code == 200
    
    # 驗證傳給 cur.execute 的 SQL 是否已去除分號
    mock_cur.execute.assert_called_once_with("SELECT * FROM CT_EMPLOY@MPCDB")


@patch("webapps.portal.decorators._is_authenticated_user")
@patch("webapps.portal.decorators.can_access")
@patch("webapps.vanna.api._resolve_data_source")
@patch("webapps.vanna.sql_guard.validate_sql")
@patch("webapps.database.db_factory.db_connect")
@patch("webapps.vanna.api._is_int_env")
def test_execute_api_records_failed_query_in_db(mock_is_int, mock_connect, mock_validate, mock_resolve, mock_can_access, mock_is_auth):
    from webapps.vanna.api import execute_api
    from webapps.vanna.models import QueryLog, FailedQueryRecord, DataSource
    from django.test import RequestFactory
    import json

    mock_is_auth.return_value = True
    mock_can_access.return_value = True
    mock_is_int.return_value = True
    
    # 建立測試用的 DataSource 和 QueryLog，注意交易隔離
    ds, _ = DataSource.objects.get_or_create(code="test_failed_ds", defaults={"name": "Failed DS", "db_type": "oracle", "enabled": True})
    qlog = QueryLog.objects.create(
        data_source=ds,
        user_id="test_user",
        question="Select all users",
        generated_sql="SELECT * FROM users",
        cleaned_sql="SELECT * FROM users",
        guard_status="passed",
        execution_status="not_executed"
    )

    mock_resolve.return_value = ds
    mock_validate.return_value = (True, "")
    
    # 模擬連線執行拋出 Exception
    mock_connect.side_effect = RuntimeError("Oracle DB connection timeout!")

    rf = RequestFactory()
    req = rf.post("/api/execute/", json.dumps({
        "query_log_id": qlog.id
    }), content_type="application/json")
    
    resp = execute_api(req)
    assert resp.status_code == 500
    
    # 驗證 FailedQueryRecord 是否已被建立且包含正確資訊
    record = FailedQueryRecord.objects.filter(query_log=qlog).first()
    assert record is not None
    assert record.question == "Select all users"
    assert record.failed_sql == "SELECT * FROM users"
    assert "Oracle DB connection timeout!" in record.error_message
    assert record.status == "pending"
    
    # 清理測試資料
    qlog.delete()
    ds.delete()


@patch("webapps.portal.decorators._is_authenticated_user")
@patch("webapps.portal.decorators.can_access")
@patch("webapps.vanna.api.is_vanna_admin")
def test_training_dataset_api_failed_query_operations(mock_is_admin, mock_can_access, mock_is_auth):
    from webapps.vanna.api import training_dataset_api
    from webapps.vanna.models import DataSource, QueryLog, FailedQueryRecord
    from django.test import RequestFactory
    import json

    mock_is_auth.return_value = True
    mock_can_access.return_value = True
    mock_is_admin.return_value = True

    ds, _ = DataSource.objects.get_or_create(code="test_failed_ds_ops", defaults={"name": "Failed DS Ops", "db_type": "oracle", "enabled": True})
    qlog = QueryLog.objects.create(
        data_source=ds,
        user_id="test_user",
        question="Select all employees",
        generated_sql="SELECT * FROM emp",
        cleaned_sql="SELECT * FROM emp",
        guard_status="passed"
    )
    
    # 建立 FailedQueryRecord
    record = FailedQueryRecord.objects.create(
        query_log=qlog,
        question="Select all employees",
        failed_sql="SELECT * FROM emp",
        error_message="ORA-00942: table or view does not exist",
        data_source_code=ds.code,
        status="pending"
    )

    rf = RequestFactory()

    # 1. 測試 GET 請求
    req_get = rf.get(f"/api/vanna/training-dataset/?code={ds.code}")
    resp_get = training_dataset_api(req_get)
    assert resp_get.status_code == 200
    data_get = json.loads(resp_get.content.decode("utf-8"))
    assert data_get["ok"] is True
    failed_list = data_get["result"]["failed_queries"]
    assert len(failed_list) > 0
    assert failed_list[0]["id"] == record.id
    assert failed_list[0]["question"] == "Select all employees"

    # 2. 測試 PUT 請求
    req_put = rf.put("/api/vanna/training-dataset/", json.dumps({
        "code": ds.code,
        "training_type": "failed",
        "id": record.id,
        "question": "Select all employees (updated)",
        "sql": "SELECT * FROM emp_fixed",
        "analysis": "Table name typo",
        "action_taken": "Renamed table in query",
        "status": "optimized"
    }), content_type="application/json")
    resp_put = training_dataset_api(req_put)
    assert resp_put.status_code == 200
    data_put = json.loads(resp_put.content.decode("utf-8"))
    assert data_put["ok"] is True
    assert data_put["result"]["question"] == "Select all employees (updated)"
    assert data_put["result"]["status"] == "optimized"

    # 再次從 DB 確認修改
    record.refresh_from_db()
    assert record.question == "Select all employees (updated)"
    assert record.failed_sql == "SELECT * FROM emp_fixed"
    assert record.analysis == "Table name typo"
    assert record.action_taken == "Renamed table in query"
    assert record.status == "optimized"

    # 3. 測試 DELETE 請求
    req_del = rf.delete("/api/vanna/training-dataset/", json.dumps({
        "code": ds.code,
        "training_type": "failed",
        "id": record.id
    }), content_type="application/json")
    resp_del = training_dataset_api(req_del)
    assert resp_del.status_code == 200
    data_del = json.loads(resp_del.content.decode("utf-8"))
    assert data_del["ok"] is True

    # 驗證 DB 是否已無該筆 record
    assert not FailedQueryRecord.objects.filter(id=record.id).exists()

    # 清理
    qlog.delete()
    ds.delete()




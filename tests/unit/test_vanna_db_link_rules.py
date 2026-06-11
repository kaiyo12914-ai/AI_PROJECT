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

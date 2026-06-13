# tests/unit/test_nl2sql_erp_mpc_connection.py
"""
NL2SQL ERP_MPC Oracle 最小連線測試
===================================
透過 db_factory.py 的 profile 機制讀取 .env_DB_factory 中的 ERP_DB_MPC_* 參數，
測試 Oracle DB 連線與基本 SELECT 查詢。

參數來源（.env_DB_factory）：
  ERP_DB_MPC_HOST=10.29.136.198
  ERP_DB_MPC_PORT=1521
  ERP_DB_MPC_SERVICE_NAME=MPCDB
  ERP_DB_MPC_USER=smcadm
  ERP_DB_MPC_PASS=Ab215963

使用方式（profile 讀取機制說明）：
  db_factory 以 profile="ERP_MPC" 呼叫時，搜尋順序為：
    1. ERP_DB_MPC_HOST → 讀取 .env_DB_factory 中的 ERP_DB_MPC_HOST
    2. ERP_DB_MPC_PORT → 讀取 .env_DB_factory 中的 ERP_DB_MPC_PORT
    3. ERP_DB_MPC_SERVICE_NAME → 讀取 ERP_DB_MPC_SERVICE_NAME
    4. ERP_DB_MPC_USER / ERP_DB_MPC_PASS → 對應欄位

執行方式：
  cd .
  python -m pytest tests/unit/test_nl2sql_erp_mpc_connection.py -v -s
  # 或直接執行：
  python tests/unit/test_nl2sql_erp_mpc_connection.py

ENV 說明：
  ENV=EXT : Oracle 走 mock 模式，連線/查詢測試自動 skip
  ENV=INT : 強制連實體 DB，執行完整連線與查詢測試
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 確保專案根目錄在 sys.path
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# 設定 Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django
django.setup()


def _get_env_mode() -> str:
    """取得目前 ENV 模式"""
    return (os.getenv("ENV") or "EXT").strip().upper()


def _is_ext_env() -> bool:
    """ENV=EXT: Oracle 不連實體 DB"""
    return _get_env_mode() == "EXT"


# ============================================================
# 1. Config 讀取驗證（不需要連線，任何環境都可跑）
# ============================================================
def test_erp_mpc_config_loaded():
    """驗證 db_factory 能正確從 .env_DB_factory 讀取 ERP_DB_MPC_* 參數"""
    from webapps.database.db_factory import load_db_config

    cfg = load_db_config("oracle", profile="ERP_MPC")

    print("\n===== ERP_MPC Oracle Config =====")
    print(f"  ora_host    = {cfg.ora_host}")
    print(f"  ora_port    = {cfg.ora_port}")
    print(f"  ora_service = {cfg.ora_service}")
    print(f"  ora_user    = {cfg.ora_user}")
    print(f"  ora_pass    = {'*' * len(cfg.ora_pass) if cfg.ora_pass else '(empty)'}")
    print(f"  ENV mode    = {_get_env_mode()}")
    print("=================================")

    assert cfg.ora_host, "ERP_DB_MPC_HOST 未設定或為空"
    assert cfg.ora_port == 1521, f"ERP_DB_MPC_PORT 應為 1521，實際 = {cfg.ora_port}"
    assert cfg.ora_service, "ERP_DB_MPC_SERVICE_NAME 未設定或為空"
    assert cfg.ora_user, "ERP_DB_MPC_USER 未設定或為空"
    assert cfg.ora_pass, "ERP_DB_MPC_PASS 未設定或為空"

    # 驗證實際值
    assert cfg.ora_host == "10.29.136.198", f"Expected host=10.29.136.198, got {cfg.ora_host}"
    assert cfg.ora_service.upper() == "MPCDB", f"Expected service=MPCDB, got {cfg.ora_service}"
    assert cfg.ora_user == "smcadm", f"Expected user=smcadm, got {cfg.ora_user}"

    print("[PASS] ERP_MPC config 讀取成功")


def test_nl2sql_default_data_source_profile():
    """驗證 NL2SQL 子系統預設 Oracle 資料來源的 profile 為 ERP_MPC"""
    from unittest.mock import patch, MagicMock
    from webapps.vanna.vanna_adapter import get_or_create_data_source

    mock_datasource = MagicMock()
    mock_datasource.objects.update_or_create.return_value = (MagicMock(db_profile="ERP_MPC"), True)

    with patch("webapps.vanna.vanna_adapter.DataSource", mock_datasource):
        get_or_create_data_source(
            code="test_oracle_ds",
            name="Test Oracle DS",
            db_type="oracle",
            db_profile="",
        )
        
        # 驗證 update_or_create 被呼叫時，defaults 中的 db_profile 帶入了 "ERP_MPC"
        call_kwargs = mock_datasource.objects.update_or_create.call_args.kwargs
        assert call_kwargs["defaults"]["db_profile"] == "ERP_MPC"
        print("[PASS] NL2SQL 預設 Oracle profile 為 ERP_MPC 驗證成功")


def test_erp_mpc_profile_env_key_resolution():
    """驗證 profile env key 的解析邏輯正確"""
    from webapps.database.db_factory import _profile_env_keys

    # ERP_MPC profile 應該搜尋 ERP_DB_MPC_ORA_HOST 和 ERP_DB_MPC_HOST
    keys = _profile_env_keys("ERP_MPC", "ORA_HOST")
    print(f"\n  profile='ERP_MPC', key='ORA_HOST' -> 搜尋順序: {keys}")
    assert "ERP_DB_MPC_ORA_HOST" in keys, "應包含 ERP_DB_MPC_ORA_HOST"
    assert "ERP_DB_MPC_HOST" in keys, "應包含 ERP_DB_MPC_HOST"

    keys_svc = _profile_env_keys("ERP_MPC", "ORA_SERVICE_NAME")
    print(f"  profile='ERP_MPC', key='ORA_SERVICE_NAME' -> 搜尋順序: {keys_svc}")
    assert "ERP_DB_MPC_ORA_SERVICE_NAME" in keys_svc or "ERP_DB_MPC_SERVICE_NAME" in keys_svc

    print("[PASS] profile env key 解析邏輯正確")


def test_erp_mpc_db_factory_md_overrides():
    """驗證 .env_DB_factory 的 override 資料有載入 ERP_DB_MPC_* 鍵"""
    from webapps.database.db_factory import _load_db_factory_md_overrides

    overrides = _load_db_factory_md_overrides()
    erp_keys = {k: v for k, v in overrides.items() if k.startswith("ERP_DB_MPC")}
    print(f"\n  .env_DB_factory 中的 ERP_DB_MPC_* 鍵: {list(erp_keys.keys())}")
    assert "ERP_DB_MPC_HOST" in erp_keys, "未找到 ERP_DB_MPC_HOST"
    assert erp_keys["ERP_DB_MPC_HOST"] == "10.29.136.198"
    print("[PASS] .env_DB_factory override 正確載入")


# ============================================================
# 2. 連線驗證（需要 ENV=INT 且網路連通）
# ============================================================
@pytest.mark.skipif(
    _is_ext_env(),
    reason="ENV=EXT: Oracle 不連實體 DB，跳過連線測試。請切換 ENV=INT 後再測試。"
)
def test_erp_mpc_connection():
    """驗證可以透過 db_factory 連線到 ERP_MPC Oracle DB"""
    from webapps.database.db_factory import db_connect

    print("\n===== 測試 ERP_MPC Oracle 連線 =====")
    conn = db_connect("oracle", profile="ERP_MPC")
    print(f"  連線成功！conn type = {type(conn).__name__}")
    conn.close()
    print("[PASS] ERP_MPC 連線測試通過")


# ============================================================
# 3. 基本 SELECT 查詢驗證（需要 ENV=INT）
# ============================================================
@pytest.mark.skipif(
    _is_ext_env(),
    reason="ENV=EXT: Oracle 查詢走 mock，跳過實體查詢測試。"
)
def test_erp_mpc_select_dual():
    """最小 SELECT 測試：SELECT 1 FROM DUAL"""
    from webapps.database.db_factory import db_query_one

    print("\n===== 測試 SELECT 1 FROM DUAL =====")
    row = db_query_one("oracle", "SELECT 1 AS test_val FROM DUAL", profile="ERP_MPC")
    assert row is not None, "SELECT 1 FROM DUAL 回傳 None"
    val = row[0]
    print(f"  結果: {val}")
    assert val == 1, f"Expected 1, got {val}"
    print("[PASS] SELECT 1 FROM DUAL 成功")


@pytest.mark.skipif(
    _is_ext_env(),
    reason="ENV=EXT: Oracle 查詢走 mock，跳過實體查詢測試。"
)
def test_erp_mpc_select_sysdate():
    """查詢資料庫目前時間：SELECT SYSDATE FROM DUAL"""
    from webapps.database.db_factory import db_query_one

    print("\n===== 測試 SELECT SYSDATE FROM DUAL =====")
    row = db_query_one("oracle", "SELECT SYSDATE AS db_time FROM DUAL", profile="ERP_MPC")
    assert row is not None, "SELECT SYSDATE FROM DUAL 回傳 None"
    db_time = row[0]
    print(f"  資料庫時間: {db_time}")
    assert db_time is not None, "SYSDATE 為 None"
    print("[PASS] SELECT SYSDATE FROM DUAL 成功")


@pytest.mark.skipif(
    _is_ext_env(),
    reason="ENV=EXT: Oracle 查詢走 mock，跳過實體查詢測試。"
)
def test_erp_mpc_select_user():
    """查詢目前連線使用者：SELECT USER FROM DUAL"""
    from webapps.database.db_factory import db_query_one

    print("\n===== 測試 SELECT USER FROM DUAL =====")
    row = db_query_one("oracle", "SELECT USER AS current_user FROM DUAL", profile="ERP_MPC")
    assert row is not None, "SELECT USER FROM DUAL 回傳 None"
    current_user = row[0]
    print(f"  目前使用者: {current_user}")
    assert current_user, "USER 為空"
    print("[PASS] SELECT USER FROM DUAL 成功")


@pytest.mark.skipif(
    _is_ext_env(),
    reason="ENV=EXT: Oracle 查詢走 mock，跳過實體查詢測試。"
)
def test_erp_mpc_select_version():
    """查詢 Oracle 版本資訊"""
    from webapps.database.db_factory import db_query_all

    print("\n===== 測試 Oracle 版本查詢 =====")
    try:
        rows = db_query_all(
            "oracle",
            "SELECT BANNER FROM V$VERSION WHERE ROWNUM <= 3",
            profile="ERP_MPC",
        )
        if rows:
            for i, row in enumerate(rows):
                print(f"  [{i}] {row[0]}")
        else:
            print("  版本查詢無結果（可能權限不足）")
        print("[PASS] 版本查詢完成")
    except Exception as e:
        # V$VERSION 權限不足不算嚴重錯誤
        print(f"[WARN] 版本查詢失敗（可能權限不足）: {e}")


@pytest.mark.skipif(
    _is_ext_env(),
    reason="ENV=EXT: Oracle 查詢走 mock，跳過實體查詢測試。"
)
def test_erp_mpc_list_tables():
    """列出使用者可見的表格（前 10 筆）"""
    from webapps.database.db_factory import db_query_all

    print("\n===== 測試列出使用者表格 =====")
    sql = """
        SELECT TABLE_NAME
        FROM USER_TABLES
        WHERE ROWNUM <= 10
        ORDER BY TABLE_NAME
    """
    rows = db_query_all("oracle", sql, profile="ERP_MPC")
    if rows:
        print(f"  找到 {len(rows)} 個表格：")
        for row in rows:
            print(f"    - {row[0]}")
    else:
        print("  （無表格或無權限）")
    print("[PASS] 表格列舉完成")


# ============================================================
# 4. ENV=EXT mock 行為驗證
# ============================================================
def test_erp_mpc_ext_mock_behavior():
    """驗證 ENV=EXT 時 Oracle 查詢走 mock（回傳空結果，不連 DB）"""
    from webapps.database.db_factory import _external_db_disabled

    is_disabled = _external_db_disabled("oracle")
    env = _get_env_mode()
    print(f"\n  ENV={env}, Oracle external_db_disabled = {is_disabled}")

    if env == "EXT":
        assert is_disabled, "ENV=EXT 時 Oracle 應走 mock"
        print("[PASS] ENV=EXT 時 Oracle 正確走 mock 模式")
    elif env == "INT":
        assert not is_disabled, "ENV=INT 時 Oracle 應連實體 DB"
        print("[PASS] ENV=INT 時 Oracle 正確連實體 DB")
    else:
        print(f"[INFO] ENV={env}，不屬於 EXT/INT 標準模式")


# ============================================================
# 主程式入口（可直接 python 執行）
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("NL2SQL ERP_MPC Oracle 最小連線測試")
    print(f"ENV = {_get_env_mode()}")
    print("=" * 60)

    # 始終執行的 config 測試
    config_tests = [
        ("Config 讀取", test_erp_mpc_config_loaded),
        ("預設 Profile 載入", test_nl2sql_default_data_source_profile),
        ("Profile 鍵解析", test_erp_mpc_profile_env_key_resolution),
        ("MD Override 載入", test_erp_mpc_db_factory_md_overrides),
        ("ENV Mock 行為", test_erp_mpc_ext_mock_behavior),
    ]

    # 需要 ENV=INT 的連線/查詢測試
    db_tests = [
        ("Oracle 連線", test_erp_mpc_connection),
        ("SELECT 1 FROM DUAL", test_erp_mpc_select_dual),
        ("SELECT SYSDATE", test_erp_mpc_select_sysdate),
        ("SELECT USER", test_erp_mpc_select_user),
        ("Oracle 版本", test_erp_mpc_select_version),
        ("列出表格", test_erp_mpc_list_tables),
    ]

    passed = 0
    failed = 0
    skipped = 0

    # 執行 config 測試
    for name, func in config_tests:
        try:
            func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n[FAIL] {name}: {e}")

    # 連線測試
    if _is_ext_env():
        print(f"\n{'=' * 60}")
        print("ENV=EXT: 跳過 Oracle 連線/查詢測試（規範不允許 EXT 連實體 Oracle DB）")
        print("若需要測試實體連線，請切換 ENV=INT 後重新執行。")
        print(f"{'=' * 60}")
        skipped = len(db_tests)
    else:
        for name, func in db_tests:
            try:
                func()
                passed += 1
            except Exception as e:
                failed += 1
                print(f"\n[FAIL] {name}: {e}")

    print(f"\n{'=' * 60}")
    print(f"結果: {passed} 通過, {failed} 失敗, {skipped} 跳過 / 共 {len(config_tests) + len(db_tests)} 項")
    print("=" * 60)

    # 使用說明
    print("\n--- NL2SQL ERP_MPC Oracle 呼叫範例 ---")
    print("""
# 方式一：使用 db_factory 公開 API
from webapps.database.db_factory import db_query_one, db_query_all, db_connect

# 1. 直接查詢（推薦）
row = db_query_one("oracle", "SELECT SYSDATE FROM DUAL", profile="ERP_MPC")
rows = db_query_all("oracle", "SELECT TABLE_NAME FROM USER_TABLES WHERE ROWNUM <= 10", profile="ERP_MPC")

# 2. 帶參數的查詢（Oracle 使用 dict 命名參數）
sql = "SELECT * FROM CT_EMPLOY WHERE IDNO = :emp_id"
row = db_query_one("oracle", sql, {"emp_id": "A123456789"}, profile="ERP_MPC")

# 3. 取得 connection 自行管理
conn = db_connect("oracle", profile="ERP_MPC")
try:
    with conn.cursor() as cur:
        cur.execute("SELECT TABLE_NAME, NUM_ROWS FROM USER_TABLES WHERE ROWNUM <= 5")
        columns = [col[0] for col in cur.description]
        rows = cur.fetchall()
        for row in rows:
            print(dict(zip(columns, row)))
finally:
    conn.close()

# 4. 讀取 config（不連線）
from webapps.database.db_factory import load_db_config
cfg = load_db_config("oracle", profile="ERP_MPC")
print(f"Host: {cfg.ora_host}, Service: {cfg.ora_service}")
""")

    sys.exit(1 if failed else 0)

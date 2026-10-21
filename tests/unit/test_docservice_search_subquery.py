from webapps.doc.services.docService import docService


def _make_service(db_type="sybase"):
    svc = object.__new__(docService)
    svc.db_type = db_type
    svc._tbl = lambda name: f"mnda.dbo.{name}"
    calls = []

    def _query_all(sql, params=None):
        calls.append((sql, params))
        return []

    svc._query_all = _query_all
    return svc, calls


def test_search_trst_advanced_sybase_master_subquery():
    svc, calls = _make_service(db_type="sybase")
    svc.search_trst_advanced(
        grsno="1150000712",
        subject="測試",
        start_date="2026-09-01",
        end_date="2026-09-10",
        limit=50,
    )
    assert len(calls) == 1
    sql, params = calls[0]
    # 驗證包含主檔子查詢 TOP_TM 與 GROUP BY
    assert "SELECT TOP 50 TM.TM_SNO, TM.TM_DATE" in sql
    assert "GROUP BY TM.TM_SNO, TM.TM_DATE" in sql
    assert ") TOP_TM" in sql
    assert "JOIN mnda.dbo.DCS3_TRST_MST TM ON TM.TM_SNO = TOP_TM.TM_SNO" in sql
    assert "JOIN mnda.dbo.DCS3_TRST_DAT TD ON TM.TM_SNO = TD.TD_SNO" in sql
    assert "LEFT JOIN mnda.dbo.DCS0_DOC_FILE DF ON DF.DF_PATH = TD.TD_PATH" in sql


def test_search_trst_advanced_oracle_master_subquery():
    svc, calls = _make_service(db_type="oracle")
    svc.search_trst_advanced(
        grsno="1150000712",
        subject="測試",
        start_date="2026-09-01",
        end_date="2026-09-10",
        limit=50,
    )
    assert len(calls) == 1
    sql, params = calls[0]
    assert "GROUP BY TM.TM_SNO, TM.TM_DATE" in sql
    assert "ROWNUM <= :limit" in sql
    assert ") TOP_TM" in sql
    assert params.get("limit") == 50


def test_search_incoming_advanced_sybase_master_subquery():
    svc, calls = _make_service(db_type="sybase")
    svc.search_incoming_advanced(
        grsno="1150001261",
        start_date="2026-09-01",
        end_date="2026-09-10",
        limit=30,
    )
    assert len(calls) == 1
    sql, params = calls[0]
    assert "SELECT TOP 30" in sql
    assert "GROUP BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)" in sql
    assert ") TOP_DOCS" in sql
    assert "JOIN mnda.dbo.DCS1_EMAL_TMP EM ON EM.EM_GRSNO = TOP_DOCS.TOP_GRSNO" in sql


def test_search_incoming_advanced_oracle_master_subquery():
    svc, calls = _make_service(db_type="oracle")
    svc.search_incoming_advanced(
        grsno="1150001261",
        start_date="2026-09-01",
        end_date="2026-09-10",
        limit=30,
    )
    assert len(calls) == 1
    sql, params = calls[0]
    assert "GROUP BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)" in sql
    assert "ROWNUM <= :limit" in sql
    assert ") TOP_DOCS" in sql
    assert params.get("limit") == 30

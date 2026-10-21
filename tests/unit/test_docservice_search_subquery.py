from webapps.doc.services.docService import docService


def _make_service(db_type="sybase", responses=None):
    svc = object.__new__(docService)
    svc.db_type = db_type
    svc._tbl = lambda name: f"mnda.dbo.{name}"
    calls = []
    resp_list = list(responses or [])

    def _query_all(sql, params=None):
        calls.append((sql, params))
        if resp_list:
            return resp_list.pop(0)
        return []

    svc._query_all = _query_all
    return svc, calls


def test_search_trst_advanced_sybase_two_phase_success():
    # Phase 1 回傳 2 筆 TM_SNO，Phase 2 回傳明細列
    svc, calls = _make_service(
        db_type="sybase",
        responses=[
            [("SNO_001", "2026-09-02"), ("SNO_002", "2026-09-01")],
            [
                ("GRS_01", "2026-09-02", "U1", b"Name1", b"Rstp1", b"Fmt1", b"Subj1", "path1", b"file1.pdf", 100),
                ("GRS_01", "2026-09-02", "U1", b"Name1", b"Rstp1", b"Fmt2", b"Subj1", "path2", b"file2.pdf", 200),
                ("GRS_02", "2026-09-01", "U2", b"Name2", b"Rstp2", b"Fmt1", b"Subj2", "path3", b"file3.pdf", 300),
            ]
        ]
    )
    rows = svc.search_trst_advanced(
        grsno="1150000712",
        subject="測試",
        start_date="2026-09-01",
        end_date="2026-09-10",
        limit=50,
    )
    assert len(calls) == 2
    # Phase 1: 查主檔 SNO
    sql1, params1 = calls[0]
    assert "SELECT DISTINCT TOP 50 TM.TM_SNO, TM.TM_DATE" in sql1
    assert "FROM mnda.dbo.DCS3_TRST_MST TM" in sql1
    # Phase 2: 依 SNO IN 查明細
    sql2, params2 = calls[1]
    assert "WHERE TM.TM_SNO IN (?,?)" in sql2
    assert params2 == ["SNO_001", "SNO_002"]
    assert len(rows) == 3


def test_search_trst_advanced_sybase_two_phase_empty_phase1():
    # Phase 1 查無資料，直接返回空，不執行 Phase 2
    svc, calls = _make_service(db_type="sybase", responses=[[]])
    rows = svc.search_trst_advanced(grsno="9999999999", limit=50)
    assert len(calls) == 1
    assert rows == []


def test_search_trst_advanced_oracle_two_phase_success():
    svc, calls = _make_service(
        db_type="oracle",
        responses=[
            [("SNO_001", "2026-09-02")],
            [("GRS_01", "2026-09-02", "U1", "Name1", "Rstp1", "Fmt1", "Subj1", "path1", "file1.pdf", 100)]
        ]
    )
    rows = svc.search_trst_advanced(grsno="1150000712", limit=50)
    assert len(calls) == 2
    sql1, params1 = calls[0]
    assert "ROWNUM <= :limit" in sql1
    assert params1.get("limit") == 50
    sql2, params2 = calls[1]
    assert "WHERE TM.TM_SNO IN (:sno0)" in sql2
    assert params2.get("sno0") == "SNO_001"
    assert len(rows) == 1


def test_search_incoming_advanced_sybase_two_phase_success():
    svc, calls = _make_service(
        db_type="sybase",
        responses=[
            [("GRS_IN_01",), ("GRS_IN_02",)],
            [
                ("GRS_IN_01", "U1", b"Subj1", "F1", b"attach1.pdf", "1"),
                ("GRS_IN_01", "U1", b"Subj1", "F2", b"attach2.pdf", "2"),
                ("GRS_IN_02", "U2", b"Subj2", "F3", b"attach3.pdf", "1"),
            ]
        ]
    )
    rows = svc.search_incoming_advanced(grsno="1150001261", limit=30)
    assert len(calls) == 2
    sql1, params1 = calls[0]
    assert "SELECT DISTINCT TOP 30" in sql1
    assert "COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)" in sql1
    sql2, params2 = calls[1]
    assert "WHERE COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) IN (?,?)" in sql2
    assert params2 == ["GRS_IN_01", "GRS_IN_02"]
    assert len(rows) == 3


def test_search_incoming_advanced_oracle_two_phase_success():
    svc, calls = _make_service(
        db_type="oracle",
        responses=[
            [("GRS_IN_01",)],
            [("GRS_IN_01", "U1", "Subj1", "F1", "attach1.pdf", "1")]
        ]
    )
    rows = svc.search_incoming_advanced(grsno="1150001261", limit=30)
    assert len(calls) == 2
    sql1, params1 = calls[0]
    assert "ROWNUM <= :limit" in sql1
    assert params1.get("limit") == 30
    sql2, params2 = calls[1]
    assert "WHERE COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) IN (:g0)" in sql2
    assert params2.get("g0") == "GRS_IN_01"
    assert len(rows) == 1

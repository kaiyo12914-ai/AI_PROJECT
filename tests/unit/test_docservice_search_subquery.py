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


def test_get_debug_sql_statements_structure_and_categories():
    svc, _ = _make_service(db_type="sybase")
    res = svc.get_debug_sql_statements(
        grsno="1150000712",
        subject="測試公文",
        psids=["108012", "108013"],
        limit=100,
        start_date="2026-09-01",
        end_date="2026-09-10",
        handler_name="王小明",
        executed_snos=["SNO_1", "SNO_2"],
        executed_grsnos=["GRS_1"],
    )
    # 必須包含四個指定類別
    assert "draft_docs" in res
    assert "draft_attachments" in res
    assert "incoming_docs" in res
    assert "incoming_attachments" in res

    # 1) 簽、稿主檔
    cat1 = res["draft_docs"]
    assert "1) 簽、稿主檔清單（DF BLOB）" in cat1["title"]
    assert "DCS3_TRST_MST" in cat1["phase1_sql"]
    assert "DCS0_DOC_FILE" in cat1["phase2_sql"]
    assert "SNO_1" in cat1["phase2_sql"]
    assert "SELECT DF_DATA" in cat1["blob_sql"]
    assert "王小明" in cat1["full_text"]

    # 2) 簽、稿附件
    cat2 = res["draft_attachments"]
    assert "2) 簽、稿附件清單（DF BLOB）" in cat2["title"]
    assert "SELECT DF_DATA" in cat2["blob_sql"]

    # 3) 來文主旨
    cat3 = res["incoming_docs"]
    assert "3) 來文主旨清單" in cat3["title"]
    assert "COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)" in cat3["phase1_sql"]
    assert "GRS_1" in cat3["phase2_sql"]

    # 4) 來文附件
    cat4 = res["incoming_attachments"]
    assert "4) 來文附件清單（EF BLOB）" in cat4["title"]
    assert "DCS3_EDOC_FILE" in cat4["phase2_sql"]
    assert "SELECT EF_DATA" in cat4["blob_sql"]


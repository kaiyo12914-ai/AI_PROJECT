from webapps.doc.services.docService import docService


def _make_service(query_results):
    svc = object.__new__(docService)
    svc.db_type = "sybase"
    svc._tbl = lambda name: f"mnda.dbo.{name}"
    calls = []

    def _query_one(sql, params=None):
        calls.append((sql, params))
        if query_results:
            return query_results.pop(0)
        return None

    svc._query_one = _query_one
    return svc, calls


def test_get_file_by_df_path_sybase_exact_match_first():
    svc, calls = _make_service([("a.doc", b"123")])
    row = svc.get_file_by_df_path("mnda-abc")
    assert row == ("a.doc", b"123")
    assert len(calls) == 1
    assert "DF.DF_PATH = ?" in calls[0][0]
    assert calls[0][1] == ["mnda-abc"]


def test_get_file_by_df_path_sybase_trim_fallback():
    svc, calls = _make_service([None, ("b.doc", b"456")])
    row = svc.get_file_by_df_path("  mnda-abc  ")
    assert row == ("b.doc", b"456")
    assert len(calls) == 2
    assert "DF.DF_PATH = ?" in calls[0][0]
    assert "LTRIM(RTRIM" in calls[1][0]
    assert calls[1][1] == ["mnda-abc"]


def test_get_file_by_df_path_sybase_slash_normalize_fallback():
    svc, calls = _make_service([None, None, ("c.doc", b"789")])
    row = svc.get_file_by_df_path(r"mnda\abc\file")
    assert row == ("c.doc", b"789")
    assert len(calls) == 3
    assert "REPLACE(LTRIM(RTRIM" in calls[2][0]
    assert calls[2][1] == ["mnda/abc/file"]

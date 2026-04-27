from webapps.projectnotes.citation_guard import ensure_sentence_citations, detect_citation_conflicts


def test_ensure_sentence_citations_happy_path():
    ans = "巨額採購係指達門檻之採購案件。應依規定程序辦理。"
    out = ensure_sentence_citations(ans, [{"ref": "C1"}, {"ref": "C2"}])
    assert "[C1]" in out
    assert "[C2]" in out


def test_ensure_sentence_citations_boundary_already_tagged():
    ans = "巨額採購係指達門檻之採購案件 [C1]"
    out = ensure_sentence_citations(ans, [{"ref": "C1"}])
    assert out.count("[C1]") == 1


def test_detect_citation_conflicts_error_like_multi_version():
    cites = [
        {"source_title": "採購規範手冊 (v1)"},
        {"source_title": "採購規範手冊 (v2)"},
    ]
    warns = detect_citation_conflicts(cites)
    assert len(warns) >= 1
from webapps.projectnotes.query_rewrite import rewrite_query_for_retrieval


def test_rewrite_query_happy_path_definition():
    out = rewrite_query_for_retrieval("何謂巨額採購？")
    assert "巨額採購" in out
    assert "定義" in out


def test_rewrite_query_boundary_empty():
    assert rewrite_query_for_retrieval("") == ""


def test_rewrite_query_error_like_noisy_prefix():
    out = rewrite_query_for_retrieval("請問：限制性招標是什麼")
    assert "限制性招標" in out
    assert "招標方式" in out
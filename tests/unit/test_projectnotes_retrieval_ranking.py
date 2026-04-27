from webapps.projectnotes.retrieval_policy import (
    build_sparse_terms,
    definition_chunk_boost,
    generic_source_penalty,
    is_definition_query,
    rerank_candidates,
)


def test_definition_query_detect_happy_path():
    assert is_definition_query("what is ai") is True


def test_definition_chunk_boost_happy_path():
    assert definition_chunk_boost("The term means the definition of procurement.") > 0


def test_generic_source_penalty_error_handling_non_generic():
    p = generic_source_penalty("what is large procurement", "government procurement act article 22", "definition text")
    assert p == 0.0


def test_generic_source_penalty_boundary_generic_source():
    p = generic_source_penalty(
        "what is large procurement",
        "information service procurement general terms",
        "this contract includes party a and party b obligations and breach penalties",
    )
    assert p > 0.0


def test_build_sparse_terms_happy_path():
    out = build_sparse_terms(["ai", "procurement", "procurement", "law", "x"])
    assert out[0] == "procurement"
    assert "law" in out


def test_build_sparse_terms_boundary_empty():
    assert build_sparse_terms([]) == []


def test_rerank_candidates_happy_path_core_term_priority():
    ranked = [
        {
            "score": 1.0,
            "excerpt": "採購流程與契約管理",
            "source_title": "A",
            "kscore": 0.2,
            "match_score": 0.3,
            "quality_score": 0.8,
            "generic_penalty": 0.0,
        },
        {
            "score": 0.9,
            "excerpt": "巨額採購係指達到法定門檻之採購案件",
            "source_title": "B",
            "kscore": 0.7,
            "match_score": 0.9,
            "quality_score": 0.9,
            "generic_penalty": 0.0,
        },
    ]
    out = rerank_candidates("何謂巨額採購", ranked, top_k=2)
    assert out[0]["source_title"] == "B"


def test_rerank_candidates_boundary_empty():
    assert rerank_candidates("what is ai", [], top_k=5) == []


def test_rerank_candidates_error_like_generic_penalty_applied():
    ranked = [
        {
            "score": 1.4,
            "excerpt": "本契約甲乙雙方履約與違約責任",
            "source_title": "資訊服務採購契約通用條款",
            "kscore": 0.8,
            "match_score": 0.7,
            "quality_score": 0.9,
            "generic_penalty": 0.4,
        },
        {
            "score": 1.1,
            "excerpt": "巨額採購係指達查核金額以上之採購",
            "source_title": "採購法條文整理",
            "kscore": 0.7,
            "match_score": 0.9,
            "quality_score": 0.9,
            "generic_penalty": 0.0,
        },
    ]
    out = rerank_candidates("何謂巨額採購", ranked, top_k=2)
    assert out[0]["source_title"] == "採購法條文整理"

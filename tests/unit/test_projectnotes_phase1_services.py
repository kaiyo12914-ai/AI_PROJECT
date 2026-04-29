import json

from django.test import RequestFactory

from webapps.projectnotes.api_helpers import read_json_body, safe_text, to_int
from webapps.projectnotes.embedding_service import mock_embedding
from webapps.projectnotes.text_processing import build_chunks, decode_text_bytes_best_effort, preprocess_rag_text


def test_api_helpers_parse_utf8_json_body():
    req = RequestFactory().post(
        "/projectnotes/projects/",
        data=json.dumps({"name": "測試專案"}).encode("utf-8"),
        content_type="application/json",
    )

    assert read_json_body(req) == {"name": "測試專案"}
    assert safe_text(None) == ""
    assert to_int(" 12 ") == 12
    assert to_int("bad", 7) == 7


def test_text_processing_decodes_cp950_and_removes_structural_noise():
    raw = "標題\r\nshape_id: 1\r\n內容段落".encode("cp950")
    text, enc = decode_text_bytes_best_effort(raw)

    assert enc in {"cp950", "big5"}
    cleaned = preprocess_rag_text(text)
    assert "標題" in cleaned
    assert "內容段落" in cleaned
    assert "shape_id" not in cleaned


def test_build_chunks_and_mock_embedding_are_deterministic_shape():
    chunks = build_chunks("abcdef", max_chars=2)
    emb = mock_embedding("alpha beta", dim=8)

    assert chunks == ["ab", "cd", "ef"]
    assert len(emb) == 8
    assert abs(sum(x * x for x in emb) - 1.0) < 1e-9


import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from webapps.doc.views_sybase_query import api_sybase_query_search


@patch("webapps.portal.decorators.can_access", return_value=True)
@patch("webapps.doc.views_sybase_query.get_login_user_idno", return_value="H121356578")
@patch("webapps.doc.views_sybase_query._build_doc_service")
def test_api_sybase_query_search_without_handler_queries_end_date_only(mock_build_svc, mock_login, mock_can_access):
    mock_svc = MagicMock()
    mock_svc.target.plant = "MPC"
    mock_svc.search_incoming_advanced.return_value = []
    mock_svc.search_trst_advanced.return_value = []
    mock_build_svc.return_value = mock_svc

    rf = RequestFactory()
    req = rf.post(
        "/doc/api/sybase/query/search/",
        data=json.dumps({
            "grsno": "",
            "subject": "",
            "handler_name": "",
            "start_date": "2026-09-13",
            "end_date": "2026-10-12",
        }),
        content_type="application/json",
    )
    req.user = SimpleNamespace(is_authenticated=True, username="H121356578")

    resp = api_sybase_query_search(req)
    assert resp.status_code == 200
    data = json.loads(resp.content.decode("utf-8"))
    assert data["ok"] is True
    assert data["query"]["start_date"] == "2026-10-12"
    assert data["query"]["end_date"] == "2026-10-12"
    assert data["query"]["limit"] == 100

    # 驗證 service 調用時的日期參數為結束日期當日
    mock_svc.search_incoming_advanced.assert_called_once()
    _, in_kwargs = mock_svc.search_incoming_advanced.call_args
    assert in_kwargs["start_date"] == "2026-10-12"
    assert in_kwargs["end_date"] == "2026-10-12"
    assert in_kwargs["limit"] == 100

    mock_svc.search_trst_advanced.assert_called_once()
    _, trst_kwargs = mock_svc.search_trst_advanced.call_args
    assert trst_kwargs["start_date"] == "2026-10-12"
    assert trst_kwargs["end_date"] == "2026-10-12"
    assert trst_kwargs["limit"] == 100

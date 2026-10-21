import datetime as dt
import json
from unittest.mock import Mock

import pytest
from django.test import RequestFactory

from webapps.doc.views_sybase_query import _parse_search_args


def test_parse_search_args_with_handler_keeps_range():
    rf = RequestFactory()
    req = rf.post(
        "/doc/api/sybase/query/search/",
        data=json.dumps({
            "handler_name": "王小明",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "limit": 1000,
        }),
        content_type="application/json",
    )
    grsno, subject, handler_name, limit, plant, start_date, end_date, doc_category = _parse_search_args(req)
    assert handler_name == "王小明"
    assert start_date == "2026-09-01"
    assert end_date == "2026-09-10"
    assert limit == 1000


def test_parse_search_args_empty_criteria_falls_back_to_end_date():
    rf = RequestFactory()
    req = rf.post(
        "/doc/api/sybase/query/search/",
        data=json.dumps({
            "grsno": "",
            "subject": "",
            "handler_name": "",
            "start_date": "2026-09-01",
            "end_date": "2026-10-12",
        }),
        content_type="application/json",
    )
    grsno, subject, handler_name, limit, plant, start_date, end_date, doc_category = _parse_search_args(req)
    assert grsno == ""
    assert subject == ""
    assert handler_name == ""
    # 當未輸入承辦人、相關號、主旨時，改以結束日期當日查詢
    assert start_date == "2026-10-12"
    assert end_date == "2026-10-12"
    assert limit == 100


def test_parse_search_args_empty_criteria_no_end_date_uses_start_date():
    rf = RequestFactory()
    req = rf.post(
        "/doc/api/sybase/query/search/",
        data=json.dumps({
            "start_date": "2026-10-05",
            "end_date": "",
        }),
        content_type="application/json",
    )
    grsno, subject, handler_name, limit, plant, start_date, end_date, doc_category = _parse_search_args(req)
    assert start_date == "2026-10-05"
    assert end_date == "2026-10-05"
    assert limit == 100


def test_parse_search_args_empty_criteria_no_dates_defaults_to_today():
    rf = RequestFactory()
    req = rf.post(
        "/doc/api/sybase/query/search/",
        data=json.dumps({}),
        content_type="application/json",
    )
    today = dt.date.today().isoformat()
    grsno, subject, handler_name, limit, plant, start_date, end_date, doc_category = _parse_search_args(req)
    assert start_date == today
    assert end_date == today
    assert limit == 100

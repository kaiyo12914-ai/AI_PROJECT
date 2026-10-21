import json
from unittest import mock
import pytest
from django.test import RequestFactory

from webapps.portal.middleware import IISRemoteUserBridgeMiddleware
from webapps.portal.views import whoami
from webapps.comment import views as comment_views


def test_integration_whoami_contains_dep():
    rf = RequestFactory()
    req = rf.get("/whoami/")
    req.session = {
        "login_user": "F129195600",
        "login_user_name": "姚承佑",
        "login_user_org": "401",
        "dep": "INFO01",
    }
    req.login_user = "F129195600"

    bridge = IISRemoteUserBridgeMiddleware(lambda r: None)
    bridge(req)

    resp = whoami(req)
    assert resp.status_code == 200

    payload = json.loads(resp.content.decode("utf-8"))
    assert payload.get("login_user_dep") == "INFO01"
    assert payload.get("session_dep") == "INFO01"


def test_integration_comment_index_renders_dep_hidden_field():
    rf = RequestFactory()
    req = rf.get("/comment/")
    req.session = {
        "login_user": "F129195600",
        "login_user_name": "姚承佑",
        "login_user_org": "401",
        "dep": "TECH99",
    }
    req.login_user = "F129195600"

    bridge = IISRemoteUserBridgeMiddleware(lambda r: None)
    bridge(req)

    with mock.patch("webapps.portal.decorators.can_access", return_value=True):
        resp = comment_views.index(req)
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        assert '<input type="hidden" id="h_dep" value="TECH99">' in html
        assert '<input type="hidden" id="h_factory" value="401">' in html

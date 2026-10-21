import os
from unittest import mock
import pytest
from django.test import RequestFactory
from django.http import HttpResponse

from webapps.common.login_utils import get_login_user_dep
from webapps.portal.middleware import IISRemoteUserBridgeMiddleware
from webapps.portal.oracle_emp import get_emp_full_info, clear_cache


@pytest.fixture(autouse=True)
def clean_emp_cache():
    clear_cache()
    yield
    clear_cache()


def test_middleware_restores_dep_to_session_from_emp_full_info():
    rf = RequestFactory()
    middleware = IISRemoteUserBridgeMiddleware(get_response=lambda req: HttpResponse("OK"))

    request = rf.get("/whoami/")
    request.session = {}
    request.login_user = "F129195600"

    mock_full_info = {
        "EMP_NAME": "姚承佑",
        "PLANT": "401",
        "DEPT": "資訊組",
        "TITLE": "工程師",
        "DEPTNO": "INFO01",
        "DEPNO": "INFO01",
    }

    with mock.patch("webapps.portal.oracle_emp.get_emp_full_info", return_value=mock_full_info):
        middleware(request)

        assert request.login_user_dep == "INFO01"
        assert request.session.get("dep") == "INFO01"
        assert request.session.get("login_user_dep") == "INFO01"


def test_middleware_preserves_existing_session_dep():
    rf = RequestFactory()
    middleware = IISRemoteUserBridgeMiddleware(get_response=lambda req: HttpResponse("OK"))

    request = rf.get("/whoami/")
    request.session = {
        "login_user": "F129195600",
        "login_user_name": "姚承佑",
        "login_user_org": "401",
        "dep": "EXISTING_DEP",
    }
    request.login_user = "F129195600"

    with mock.patch("webapps.portal.oracle_emp.get_emp_full_info", return_value={}):
        middleware(request)

        assert request.login_user_dep == "EXISTING_DEP"
        assert request.session.get("dep") == "EXISTING_DEP"
        assert request.session.get("login_user_dep") == "EXISTING_DEP"


def test_middleware_dev_login_dep_fallback_in_debug():
    rf = RequestFactory()
    middleware = IISRemoteUserBridgeMiddleware(get_response=lambda req: HttpResponse("OK"))

    request = rf.get("/whoami/")
    request.session = {}
    request.login_user = "F129195600"

    with mock.patch("webapps.portal.oracle_emp.get_emp_full_info", return_value={}), \
         mock.patch("django.conf.settings.DEBUG", True), \
         mock.patch.dict(os.environ, {"DEV_LOGIN_DEP": "DEV_DEP_99"}):
        middleware(request)

        assert request.login_user_dep == "DEV_DEP_99"
        assert request.session.get("dep") == "DEV_DEP_99"


def test_get_login_user_dep_utility():
    rf = RequestFactory()

    # 1. From request attribute
    req1 = rf.get("/")
    req1.login_user_dep = "DEP_ATTR"
    assert get_login_user_dep(req1) == "DEP_ATTR"

    # 2. From session['dep']
    req2 = rf.get("/")
    req2.session = {"dep": "DEP_SESS"}
    assert get_login_user_dep(req2) == "DEP_SESS"

    # 3. From session['login_user_dep']
    req3 = rf.get("/")
    req3.session = {"login_user_dep": "DEP_SESS_LONG"}
    assert get_login_user_dep(req3) == "DEP_SESS_LONG"

    # 4. Fallback to get_emp_full_info
    req4 = rf.get("/")
    req4.login_user = "F999999999"
    with mock.patch("webapps.portal.oracle_emp.get_emp_full_info", return_value={"DEPTNO": "DEP_REMOTE"}):
        assert get_login_user_dep(req4) == "DEP_REMOTE"


def test_oracle_emp_mock_full_info_returns_dep():
    # Test mock fallback when oracle disabled
    with mock.patch("webapps.portal.oracle_emp._is_oracle_emp_enabled", return_value=False), \
         mock.patch("webapps.portal.oracle_emp._pg_query_one", side_effect=Exception("no pg table")), \
         mock.patch("webapps.portal.oracle_emp._mock_emp_info", return_value={"name": "測試員", "plant": "202", "dep": "D202"}):
        info = get_emp_full_info("A123456789")
        assert info.get("DEPTNO") == "D202"
        assert info.get("DEPNO") == "D202"

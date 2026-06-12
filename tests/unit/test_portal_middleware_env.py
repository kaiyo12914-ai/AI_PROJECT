import os
from unittest import mock
from django.test import TestCase, RequestFactory
from django.http import HttpResponse

from webapps.common.login_utils import get_login_user_org
from webapps.portal.middleware import IISRemoteUserBridgeMiddleware


class TestLoginUserOrgEnv(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = IISRemoteUserBridgeMiddleware(get_response=lambda req: HttpResponse("OK"))

    def test_get_login_user_org_env_ext(self):
        request = self.factory.get("/whoami/")
        request.session = {}
        request.login_user = "F1234567"

        # 1. Test when ENV=EXT
        with mock.patch.dict(os.environ, {"ENV": "EXT", "ENX": ""}):
            org = get_login_user_org(request)
            self.assertEqual(org, "MPC")

        # 2. Test when ENX=EXT
        with mock.patch.dict(os.environ, {"ENV": "", "ENX": "EXT"}):
            org = get_login_user_org(request)
            self.assertEqual(org, "MPC")

        # 3. Test when ENV=INT (should not override)
        with mock.patch.dict(os.environ, {"ENV": "INT", "ENX": ""}):
            org = get_login_user_org(request)
            self.assertNotEqual(org, "MPC")

    def test_middleware_login_user_org_env_ext(self):
        request = self.factory.get("/whoami/")
        request.session = {"login_user_org": "202", "login_user": "F1234567"}  # Preset org_code and user_id
        request.login_user = "F1234567"

        # Under normal circumstances, org_code would resolve from session/resolve
        # But if ENV=EXT, it must be forced to MPC.
        with mock.patch.dict(os.environ, {"ENV": "EXT", "ENX": ""}):
            self.middleware(request)
            self.assertEqual(request.login_user_org, "MPC")
            self.assertEqual(request.session.get("login_user_org"), "MPC")
            self.assertEqual(request.login_user_factory_plant, "MPC")

        # Under normal circumstances, org_code would resolve from session/resolve
        # But if ENX=EXT, it must be forced to MPC.
        request.session = {"login_user_org": "202", "login_user": "F1234567"}
        with mock.patch.dict(os.environ, {"ENV": "", "ENX": "EXT"}):
            self.middleware(request)
            self.assertEqual(request.login_user_org, "MPC")
            self.assertEqual(request.session.get("login_user_org"), "MPC")
            self.assertEqual(request.login_user_factory_plant, "MPC")

        # If neither is EXT, it should fall back to what is resolved (e.g. 202)
        request.session = {"login_user_org": "202", "login_user": "F1234567"}
        with mock.patch.dict(os.environ, {"ENV": "INT", "ENX": ""}):
            self.middleware(request)
            self.assertEqual(request.login_user_org, "202")

        # 4. Test when ENV=EXT and emp_name is preset (should format to MPC-emp_name)
        request.session = {"login_user_org": "202", "login_user_name": "姚承佑", "login_user": "F1234567"}
        request.login_user = "F1234567"
        with mock.patch.dict(os.environ, {"ENV": "EXT", "ENX": ""}):
            self.middleware(request)
            self.assertEqual(request.login_user_name, "MPC-姚承佑")
            self.assertEqual(request.session.get("login_user_name"), "MPC-姚承佑")

        # 5. Test when ENV=EXT and emp_name already has another prefix like "202-"
        request.session = {"login_user_org": "202", "login_user_name": "202-姚承佑", "login_user": "F1234567"}
        request.login_user = "F1234567"
        with mock.patch.dict(os.environ, {"ENV": "EXT", "ENX": ""}):
            self.middleware(request)
            self.assertEqual(request.login_user_name, "MPC-姚承佑")
            self.assertEqual(request.session.get("login_user_name"), "MPC-姚承佑")

    def test_mpc_prefix_username_stripping(self):
        # 1. Test _strip_domain with MPC- prefix
        from webapps.portal.middleware import _strip_domain
        self.assertEqual(_strip_domain("MPC-H121356578"), "H121356578")
        self.assertEqual(_strip_domain("DOMAIN\\MPC-H121356578"), "H121356578")
        self.assertEqual(_strip_domain("mpc-h121356578"), "h121356578")
        self.assertEqual(_strip_domain("H121356578"), "H121356578")

        # 2. Test get_login_user_idno stripping
        from webapps.common.login_utils import get_login_user_idno
        request = self.factory.get("/whoami/")
        request.login_user = "MPC-H121356578"
        self.assertEqual(get_login_user_idno(request), "H121356578")

        # 3. Test acl.py username stripping during Oracle ACL fetch
        from django.contrib.auth.models import User
        from webapps.portal.acl import _get_user_groups_from_oracle_uncached
        user = User(username="MPC-H121356578")
        
        with mock.patch("webapps.portal.acl.db_query_all") as mock_db_query:
            mock_db_query.return_value = []
            with mock.patch("webapps.portal.acl._is_ext_env", return_value=False):
                _get_user_groups_from_oracle_uncached(user)
                mock_db_query.assert_called_once()
                # Check that the username passed to the SQL bind parameters is stripped
                bind_params = mock_db_query.call_args[0][2]
                self.assertEqual(bind_params.get("login_user"), "H121356578")

        # 4. Test that whoami API returns acl debug info
        from webapps.portal.views import whoami
        import json
        req = self.factory.get("/whoami/")
        req.user = User(username="H121356578")
        req.login_user = "H121356578"
        with mock.patch("webapps.portal.acl.db_query_all", return_value=[]):
            with mock.patch("webapps.portal.acl._is_ext_env", return_value=False):
                resp = whoami(req)
                self.assertEqual(resp.status_code, 200)
                data = json.loads(resp.content)
                self.assertIn("acl", data)
                self.assertEqual(data["acl"]["user"], "H121356578")

        # 5. Test that _get_whoami_debug_info includes acl debug info
        from webapps.portal.middleware import _get_whoami_debug_info
        with mock.patch("webapps.portal.acl.db_query_all", return_value=[]):
            with mock.patch("webapps.portal.acl._is_ext_env", return_value=False):
                info = _get_whoami_debug_info(req)
                self.assertIn("acl", info)
                self.assertEqual(info["acl"]["user"], "H121356578")

        # 6. Test _fetch_oracle_acl_groups stripping
        from webapps.portal.views import _fetch_oracle_acl_groups
        with mock.patch("webapps.portal.views.db_query_all") as mock_db_query:
            mock_db_query.return_value = []
            with mock.patch.dict(os.environ, {"ENV": "INT"}):
                with self.settings(ORA_ACL_TABLE="VIEW_ZZ_USER_GROUP_ACL", ORA_ACL_USER_COL="USER_ID", ORA_ACL_GROUP_COL="GROUP_NAME"):
                    _fetch_oracle_acl_groups("MPC-H121356578")
                    mock_db_query.assert_called_once()
                    bind_params = mock_db_query.call_args[0][2]
                    self.assertEqual(bind_params.get("u"), "H121356578")


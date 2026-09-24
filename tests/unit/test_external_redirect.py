from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import Http404
from webapps.portal.views import external_redirect
from webapps.portal.middleware import PortalUsageLogMiddleware

class TestExternalRedirect(SimpleTestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    @override_settings(
        PORTAL_ACL_ENABLED=False,
        OPENWEBUI_PORTAL_URL="http://mpcai.mpc.mil.tw:8000/auth",
        VANNA_PORTAL_URL="http://mpcai.mpc.mil.tw:8084",
    )
    def test_redirect_openwebui_success(self):
        request = self.rf.get("/redirect/openwebui/")
        request.user = None
        response = external_redirect(request, target="openwebui")
        self.assertEqual(response.status_code, 200)
        self.assertIn("http://mpcai.mpc.mil.tw:8000/auth", response.content.decode("utf-8"))
        self.assertIn("window.location.replace", response.content.decode("utf-8"))

    @override_settings(
        PORTAL_ACL_ENABLED=False,
        OPENWEBUI_PORTAL_URL="http://mpcai.mpc.mil.tw:8000/auth",
        VANNA_PORTAL_URL="http://mpcai.mpc.mil.tw:8084",
    )
    def test_redirect_vanna_success(self):
        request = self.rf.get("/redirect/vanna/")
        request.user = None
        response = external_redirect(request, target="vanna")
        self.assertEqual(response.status_code, 200)
        self.assertIn("http://mpcai.mpc.mil.tw:8084", response.content.decode("utf-8"))
        self.assertIn("window.location.replace", response.content.decode("utf-8"))

    def test_redirect_unknown_target_404(self):
        request = self.rf.get("/redirect/unknown/")
        request.user = None
        with self.assertRaises(Http404):
            external_redirect(request, target="unknown")

    def test_redirect_uses_node_acl(self):
        request = self.rf.get("/redirect/openwebui/")
        request.user = SimpleNamespace(is_authenticated=True, username="u1")
        with patch("webapps.portal.decorators.can_access", return_value=False) as mock_can_access:
            response = external_redirect(request, target="openwebui")
        self.assertEqual(response.status_code, 403)
        mock_can_access.assert_called_once()
        self.assertEqual(mock_can_access.call_args.args[1], "openwebui")


class TestExternalRedirectLoggingIntegration(SimpleTestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    @override_settings(
        PORTAL_ACL_ENABLED=False,
        OPENWEBUI_PORTAL_URL="http://mpcai.mpc.mil.tw:8000/auth",
        VANNA_PORTAL_URL="http://mpcai.mpc.mil.tw:8084",
        PORTAL_USAGE_CODE_MAP=(
            ("/redirect/openwebui/", "OPENWEBUI"),
            ("/redirect/vanna/", "VANNA"),
        )
    )
    @patch("webapps.portal.models.PortalUsageLog.objects.create")
    @patch("webapps.portal.models.PortalUsageLog.objects.filter")
    @patch("webapps.portal.middleware.resolve_effective_user_id", return_value="test_user_01")
    def test_openwebui_usage_log_recorded(self, mock_user, mock_filter, mock_create):
        mock_filter.return_value.exists.return_value = False
        middleware = PortalUsageLogMiddleware(get_response=lambda req: external_redirect(req, target="openwebui"))
        
        request = self.rf.get("/redirect/openwebui/")
        request.session = {}
        request.login_user_org = "MPC"
        request.login_user_name = "RedirectTester"

        response = middleware(request)
        self.assertEqual(response.status_code, 200)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs.get("program_code"), "OPENWEBUI")
        self.assertEqual(kwargs.get("user_id"), "test_user_01")
        self.assertEqual(kwargs.get("user_name"), "MPC RedirectTester")

    @override_settings(
        PORTAL_ACL_ENABLED=False,
        OPENWEBUI_PORTAL_URL="http://mpcai.mpc.mil.tw:8000/auth",
        VANNA_PORTAL_URL="http://mpcai.mpc.mil.tw:8084",
        PORTAL_USAGE_CODE_MAP=(
            ("/redirect/openwebui/", "OPENWEBUI"),
            ("/redirect/vanna/", "VANNA"),
        )
    )
    @patch("webapps.portal.models.PortalUsageLog.objects.create")
    @patch("webapps.portal.models.PortalUsageLog.objects.filter")
    @patch("webapps.portal.middleware.resolve_effective_user_id", return_value="test_user_02")
    def test_vanna_usage_log_recorded(self, mock_user, mock_filter, mock_create):
        mock_filter.return_value.exists.return_value = False
        middleware = PortalUsageLogMiddleware(get_response=lambda req: external_redirect(req, target="vanna"))
        
        request = self.rf.get("/redirect/vanna/")
        request.session = {}
        request.login_user_org = "MPC"
        request.login_user_name = "VannaTester"

        response = middleware(request)
        self.assertEqual(response.status_code, 200)

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs.get("program_code"), "VANNA")
        self.assertEqual(kwargs.get("user_id"), "test_user_02")
        self.assertEqual(kwargs.get("user_name"), "MPC VannaTester")

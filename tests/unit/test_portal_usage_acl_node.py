from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from webapps.portal import views


class TestPortalUsageAclNode(SimpleTestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    def _request(self, path: str = "/usage/"):
        request = self.rf.get(path)
        request.user = SimpleNamespace(is_authenticated=True, username="u1")
        return request

    def test_usage_page_uses_usage_acl_node(self):
        with patch("webapps.portal.decorators.can_access", return_value=False) as can_access:
            response = views.usage_log_page(self._request())

        assert response.status_code == 403
        can_access.assert_called_once()
        assert can_access.call_args.args[1] == "usage"

    def test_usage_export_uses_usage_acl_node(self):
        with patch("webapps.portal.decorators.can_access", return_value=False) as can_access:
            response = views.usage_log_export_xlsx(self._request("/usage/export.xlsx/"))

        assert response.status_code == 403
        can_access.assert_called_once()
        assert can_access.call_args.args[1] == "usage"

    def test_usage_whoami_uses_usage_acl_node(self):
        with patch("webapps.portal.decorators.can_access", return_value=False) as can_access:
            response = views.usage_whoami_page(self._request("/usage/whoami/?id=1"))

        assert response.status_code == 403
        can_access.assert_called_once()
        assert can_access.call_args.args[1] == "usage"

    def test_usage_user_acl_uses_usage_acl_node(self):
        with patch("webapps.portal.decorators.can_access", return_value=False) as can_access:
            response = views.usage_user_acl_page(self._request("/usage/user_acl/?user_id=u1"))

        assert response.status_code == 403
        can_access.assert_called_once()
        assert can_access.call_args.args[1] == "usage"

from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import HttpResponse

from webapps.portal.decorators import require_node


class TestPortalAclExtDocBypass(SimpleTestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    @override_settings(ENV_NAME="EXT", PORTAL_ACL_BYPASS_NODES_EXT=["doc"])
    def test_ext_doc_bypass_skips_acl_group_check_for_authenticated_user(self):
        request = self.rf.get("/doc/sybase-query/")
        request.user = SimpleNamespace(is_authenticated=True, username="u1")

        @require_node("doc")
        def view(_request):
            return HttpResponse("ok")

        with patch("webapps.portal.decorators.can_access", side_effect=AssertionError("should not call ACL")):
            response = view(request)

        assert response.status_code == 200

    @override_settings(ENV_NAME="INT", PORTAL_ACL_BYPASS_NODES_EXT=["doc"])
    def test_int_doc_keeps_original_acl_behavior(self):
        request = self.rf.get("/doc/sybase-query/")
        request.user = SimpleNamespace(is_authenticated=True, username="u1")

        @require_node("doc")
        def view(_request):
            return HttpResponse("ok")

        with patch("webapps.portal.decorators.can_access", return_value=False):
            response = view(request)

        assert response.status_code == 403

    @override_settings(ENV_NAME="EXT", PORTAL_ACL_BYPASS_NODES_EXT=["doc"])
    def test_ext_doc_without_auth_not_bypassed_for_api(self):
        request = self.rf.get("/doc/api/sybase/query/search/", HTTP_ACCEPT="application/json")
        request.user = SimpleNamespace(is_authenticated=False, username="")

        @require_node("doc", api=True)
        def view(_request):
            return HttpResponse("ok")

        with patch("webapps.portal.decorators.can_access", return_value=False):
            response = view(request)

        assert response.status_code == 401

import json
import os
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()


class TestPortalExternalRedirectIntegration(SimpleTestCase):
    def test_portal_template_contains_redirect_entries(self):
        text = (Path(__file__).resolve().parents[2] / "webapps/portal/templates/portal/index.html").read_text(encoding="utf-8")
        self.assertIn("{% url 'portal:external_redirect' 'openwebui' as openwebui_redirect_href %}", text)
        self.assertIn("{% url 'portal:external_redirect' 'vanna' as vanna_redirect_href %}", text)

    @override_settings(
        PORTAL_ACL_ENABLED=False,
        OPENWEBUI_PORTAL_URL="http://mpcai.mpc.mil.tw:8000/auth",
        VANNA_PORTAL_URL="http://mpcai.mpc.mil.tw:8084",
    )
    def test_client_get_redirect_endpoints(self):
        client = Client()
        resp_openwebui = client.get("/redirect/openwebui/")
        self.assertEqual(resp_openwebui.status_code, 200)
        self.assertIn("http://mpcai.mpc.mil.tw:8000/auth", resp_openwebui.content.decode("utf-8"))

        resp_vanna = client.get("/redirect/vanna/")
        self.assertEqual(resp_vanna.status_code, 200)
        self.assertIn("http://mpcai.mpc.mil.tw:8084", resp_vanna.content.decode("utf-8"))

from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, override_settings

from webapps.portal.middleware_proxy_prefix import ForwardedPrefixMiddleware


@override_settings(
    ALLOWED_HOSTS=["*"],
    PROXY_PREFIX="/djangoai",
    FORCE_SCRIPT_NAME="",
    PROXY_PREFIX_WRITE_SCRIPT_NAME=True,
    TRUST_X_FORWARDED_PREFIX=False,
    USE_X_FORWARDED_HOST=True,
    STATIC_URL="/static/",
)
class DynamicProxyPrefixTests(SimpleTestCase):
    def request(self, host, path="/chatbotui/", **headers):
        request = RequestFactory().get(path, HTTP_HOST=host, **headers)
        ForwardedPrefixMiddleware(lambda req: HttpResponse())(request)
        return request

    def assert_static(self, request, expected):
        template = Template("{% load custom_tags %}{% custom_static 'chatbotui/js/index.js' %}")
        self.assertEqual(template.render(Context({"request": request})), expected)

    @override_settings(PROXY_PREFIX="")
    def test_local_direct(self):
        for host in ("127.0.0.1:8000", "localhost:8000", "[::1]:8000"):
            with self.subTest(host=host):
                request = self.request(host)
                self.assertEqual(request.script_name, "")
                self.assertEqual(request.proxy_prefix, "")
                self.assert_static(request, "/static/chatbotui/js/index.js")

    def test_proxy_strips_prefix(self):
        request = self.request("intranet.example")
        self.assertEqual(request.script_name, "/djangoai")
        self.assertEqual(request.path_info, "/chatbotui/")
        self.assert_static(request, "/djangoai/static/chatbotui/js/index.js")

    def test_proxy_preserves_prefix(self):
        request = self.request("127.0.0.1:8000", "/djangoai/chatbotui/")
        self.assertEqual(request.script_name, "/djangoai")
        self.assertEqual(request.path_info, "/chatbotui/")

    def test_forwarded_external_host(self):
        request = self.request("localhost:8000", HTTP_X_FORWARDED_HOST="intranet.example")
        self.assertEqual(request.script_name, "/djangoai")

    def test_untrusted_prefix_ignored(self):
        request = self.request("localhost:8000", HTTP_X_FORWARDED_PREFIX="/forged")
        self.assertEqual(request.script_name, "/djangoai")

    @override_settings(TRUST_X_FORWARDED_PREFIX=True)
    def test_trusted_prefix(self):
        request = self.request("localhost:8000", HTTP_X_FORWARDED_PREFIX="/gateway")
        self.assertEqual(request.script_name, "/gateway")

    @override_settings(PROXY_PREFIX="/another")
    def test_prefix_read_from_settings_without_hardcoding(self):
        request = self.request("intranet.example", "/another/chatbotui/")
        self.assertEqual(request.script_name, "/another")
        self.assertEqual(request.path_info, "/chatbotui/")
        self.assert_static(request, "/another/static/chatbotui/js/index.js")

    def test_host_does_not_override_environment(self):
        for prefix in ("", "/djangoai"):
            with override_settings(PROXY_PREFIX=prefix):
                for host in ("intranet.example", "localhost", "127.0.0.1:8000"):
                    self.assertEqual(self.request(host).script_name, prefix)

    def test_cookie_defaults_follow_environment(self):
        from django.conf import settings
        self.assertEqual(settings.DEFAULT_COOKIE_PATH, settings.SESSION_COOKIE_PATH)
        self.assertEqual(settings.DEFAULT_COOKIE_PATH, settings.CSRF_COOKIE_PATH)

from django.test import RequestFactory, SimpleTestCase

from webapps.doc.views_pages import index


class TestDocIndexWelcomeUser(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_index_shows_org_and_name_when_both_present(self):
        request = self.rf.get("/doc/")
        request.login_user_org = "MPC"
        request.login_user_name = "User One"

        response = index.__wrapped__(request)

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("MPC User One", html)

    def test_index_falls_back_to_name_or_org(self):
        request = self.rf.get("/doc/")
        request.login_user_name = "User One"

        response = index.__wrapped__(request)
        html = response.content.decode("utf-8")
        self.assertIn("User One", html)

        request = self.rf.get("/doc/")
        request.login_user_org = "MPC"
        response = index.__wrapped__(request)
        html = response.content.decode("utf-8")
        self.assertIn("MPC", html)

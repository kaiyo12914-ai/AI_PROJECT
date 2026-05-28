import json
from unittest.mock import patch
from django.test import TestCase, RequestFactory, override_settings
from django.http import HttpResponse
from django.utils import timezone
from webapps.portal.middleware import PortalUsageLogMiddleware
from webapps.portal.models import PortalUsageLog

class TestPortalUsageLogMiddlewareDeduplication(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = PortalUsageLogMiddleware(get_response=lambda req: HttpResponse("OK"))
        self.initial_count = PortalUsageLog.objects.count()
        self.created_logs = []

    def tearDown(self):
        # Clean up any logged records we created during the test
        for log in self.created_logs:
            try:
                log.delete()
            except Exception:
                pass
        # Also clean up any other logs matching our test codes
        PortalUsageLog.objects.filter(program_code__in=["TEST_FEATURE", "ANOTHER_FEATURE"]).delete()

    def _track_new_logs(self):
        # Helper to find new logs created during this test run
        return list(PortalUsageLog.objects.filter(program_code__in=["TEST_FEATURE", "ANOTHER_FEATURE"]))

    @override_settings(
        PORTAL_USAGE_CODE_MAP=(("/test-feature/", "TEST_FEATURE"),)
    )
    @patch("webapps.portal.middleware.resolve_effective_user_id", return_value="user123")
    def test_deduplication_same_user_same_feature_within_one_hour(self, mock_resolve_user):
        # 1. First request by user123 to /test-feature/ -> should be logged
        request1 = self.factory.get("/test-feature/")
        request1.session = {}
        request1.login_user_name = "User One"
        
        response1 = self.middleware(request1)
        self.assertEqual(response1.status_code, 200)
        
        new_logs = self._track_new_logs()
        self.assertEqual(len(new_logs), 1)
        first_log = new_logs[0]
        self.assertEqual(first_log.user_id, "user123")
        self.assertEqual(first_log.program_code, "TEST_FEATURE")

        # 2. Second request by user123 to /test-feature/ within one hour -> should NOT be logged (deduplicated)
        request2 = self.factory.get("/test-feature/")
        request2.session = {}
        request2.login_user_name = "User One"
        
        response2 = self.middleware(request2)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(len(self._track_new_logs()), 1) # count remains 1

    @override_settings(
        PORTAL_USAGE_CODE_MAP=(("/test-feature/", "TEST_FEATURE"),)
    )
    @patch("webapps.portal.middleware.resolve_effective_user_id", return_value="user123")
    def test_no_deduplication_for_different_user(self, mock_resolve_user):
        # 1. First request by user123 -> logged
        request1 = self.factory.get("/test-feature/")
        request1.session = {}
        request1.login_user_name = "User One"
        self.middleware(request1)
        self.assertEqual(len(self._track_new_logs()), 1)

        # 2. Second request by user456 -> should be logged
        mock_resolve_user.return_value = "user456"
        request2 = self.factory.get("/test-feature/")
        request2.session = {}
        request2.login_user_name = "User Two"
        self.middleware(request2)
        self.assertEqual(len(self._track_new_logs()), 2)

    @override_settings(
        PORTAL_USAGE_CODE_MAP=(("/test-feature/", "TEST_FEATURE"), ("/another-feature/", "ANOTHER_FEATURE"))
    )
    @patch("webapps.portal.middleware.resolve_effective_user_id", return_value="user123")
    def test_no_deduplication_for_different_feature(self, mock_resolve_user):
        # 1. First request to /test-feature/ -> logged
        request1 = self.factory.get("/test-feature/")
        request1.session = {}
        request1.login_user_name = "User One"
        self.middleware(request1)
        self.assertEqual(len(self._track_new_logs()), 1)

        # 2. Second request to /another-feature/ -> should be logged
        request2 = self.factory.get("/another-feature/")
        request2.session = {}
        request2.login_user_name = "User One"
        self.middleware(request2)
        self.assertEqual(len(self._track_new_logs()), 2)

    @override_settings(
        PORTAL_USAGE_CODE_MAP=(("/test-feature/", "TEST_FEATURE"),)
    )
    @patch("webapps.portal.middleware.resolve_effective_user_id", return_value="user123")
    def test_no_deduplication_after_one_hour(self, mock_resolve_user):
        # 1. First request -> logged
        request1 = self.factory.get("/test-feature/")
        request1.session = {}
        request1.login_user_name = "User One"
        self.middleware(request1)
        self.assertEqual(len(self._track_new_logs()), 1)

        # Update the created_at timestamp of the first log to be 2 hours ago
        log = self._track_new_logs()[0]
        two_hours_ago = timezone.now() - timezone.timedelta(hours=2)
        PortalUsageLog.objects.filter(id=log.id).update(created_at=two_hours_ago)

        # 2. Second request after 1 hour -> should be logged
        request2 = self.factory.get("/test-feature/")
        request2.session = {}
        request2.login_user_name = "User One"
        self.middleware(request2)
        self.assertEqual(len(self._track_new_logs()), 2)

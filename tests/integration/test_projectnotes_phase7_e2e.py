from django.test import Client, TestCase, override_settings
from django.urls import reverse
import os
import django
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
django.setup()

from webapps.projectnotes import views
from webapps.projectnotes import models

@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class Phase7E2ETest(TestCase):
    # Allow 'default' for user authentication in middleware
    databases = ["default"] 

    def setUp(self):
        self.client = Client()
        self.project_id = 999
        self.job_id = 888
        self.source_id = 777

    @patch("webapps.projectnotes.views.Project.objects")
    @patch("webapps.projectnotes.views.start_source_upload_task")
    @patch("webapps.projectnotes.views.ProcessingJob.objects")
    @patch("webapps.projectnotes.views.ActivityLog.objects")
    @patch("webapps.projectnotes.views._can_manage_projects")
    def test_full_ingestion_workflow(self, 
                                   mock_can_manage,
                                   mock_act_objs, mock_job_objs_views,
                                   mock_start_task, mock_proj_objs):
        # 0. Mock permissions to avoid DB hits for user/group
        mock_can_manage.return_value = True
        
        # 1. Setup Mocks
        mock_proj_objs.filter.return_value.exists.return_value = True
        mock_start_task.return_value = self.job_id
        
        job_instance = MagicMock()
        job_instance.id = self.job_id
        job_instance.status = "completed"
        job_instance.target_id = self.source_id
        job_instance.progress_info = "Completed"
        job_instance.error_message = ""
        mock_job_objs_views.get.return_value = job_instance

        # 2. Start Upload
        url = reverse("projectnotes:sources")
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile("test_doc.txt", b"content", content_type="text/plain")
        
        response = self.client.post(url, {
            "project_id": self.project_id,
            "title": "E2E Test Source",
            "file": upload
        }, **{"HTTP_X_REMOTE_USER": "test_user"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["job_id"] == self.job_id
        
        # 3. Check Job Status
        status_url = reverse("projectnotes:job_status", args=[self.job_id])
        resp = self.client.get(status_url, **{"HTTP_X_REMOTE_USER": "test_user"})
        status_data = resp.json()
        assert status_data["ok"] is True
        assert status_data["status"] == "completed"
        assert status_data["target_id"] == self.source_id

        # 4. Verify Audit Logs (ActivityLog)
        mock_qs = MagicMock()
        # Handle select_related chain: all().select_related().order_by()
        mock_act_objs.all.return_value.select_related.return_value.order_by.return_value = mock_qs
        # Also handle filter case if project_id is passed
        mock_act_objs.all.return_value.select_related.return_value.order_by.return_value.filter.return_value = mock_qs
        
        log_entry = MagicMock()
        log_entry.id = 1
        log_entry.project_id = self.project_id
        log_entry.action = "source_upload"
        log_entry.target_type = "source"
        log_entry.target_id = self.source_id
        log_entry.user_id = "test_user"
        log_entry.created_at = None
        log_entry.detail_json = {}
        log_entry.project.name = "E2E Test Project"
        
        # Ensure slicing works: qs[:limit] returns a list of models
        mock_qs.__getitem__.side_effect = lambda s: [log_entry] if isinstance(s, slice) else log_entry
        
        audit_url = reverse("projectnotes:audit_logs")
        resp = self.client.get(audit_url + f"?project_id={self.project_id}", **{"HTTP_X_REMOTE_USER": "test_user"})
        audit_data = resp.json()
        assert audit_data["ok"] is True
        assert len(audit_data["rows"]) > 0
        assert audit_data["rows"][0]["action"] == "source_upload"
        assert audit_data["rows"][0]["project_id"] == self.project_id

from django.db import models


class DocumentFormalizeLog(models.Model):
    user_id = models.CharField(max_length=64, blank=True, default="")
    user_name = models.CharField(max_length=128, blank=True, default="")
    mode = models.CharField(max_length=32)
    options_json = models.JSONField(default=dict, blank=True)
    input_chars = models.IntegerField(default=0)
    output_chars = models.IntegerField(default=0)
    processing_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=16, default="ok")
    source_masked = models.TextField(blank=True, default="")
    result_masked = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


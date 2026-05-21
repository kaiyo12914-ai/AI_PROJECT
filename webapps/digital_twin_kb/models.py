from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from pgvector.django import VectorField


class Document(models.Model):
    UPLOADER_TYPES = [("user", "User"), ("ai_agent", "AI Agent"), ("system", "System")]

    document_id = models.BigAutoField(primary_key=True)
    file_name = models.CharField(max_length=255)
    original_file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=32)
    file_path = models.TextField()
    file_size = models.BigIntegerField(default=0)
    source = models.CharField(max_length=255, blank=True)
    uploaded_by = models.CharField(max_length=128, blank=True)
    uploaded_by_type = models.CharField(max_length=32, choices=UPLOADER_TYPES, default="user")
    topic = models.CharField(max_length=255, blank=True)
    security_level = models.PositiveSmallIntegerField(default=1)
    checksum = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["topic"]),
            models.Index(fields=["security_level"]),
            models.Index(fields=["checksum"]),
        ]

    def __str__(self):
        return self.file_name


class DocumentChunk(models.Model):
    chunk_id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(Document, related_name="chunks", on_delete=models.CASCADE)
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    section_title = models.CharField(max_length=255, blank=True)
    twin_level = models.CharField(max_length=64, blank=True)
    isa95_level = models.CharField(max_length=64, blank=True)
    system_type = models.CharField(max_length=64, blank=True)
    topic = models.CharField(max_length=255, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    security_level = models.PositiveSmallIntegerField(default=1)
    embedding = VectorField(dimensions=getattr(settings, "DIGITAL_TWIN_KB_EMBEDDING_DIMENSIONS", 384))
    token_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "chunk_index"], name="uq_document_chunk_index")
        ]
        indexes = [
            models.Index(fields=["security_level"]),
            models.Index(fields=["twin_level"]),
            models.Index(fields=["isa95_level"]),
            models.Index(fields=["system_type"]),
            models.Index(fields=["topic"]),
        ]

    def __str__(self):
        return f"{self.document.file_name}#{self.chunk_index}"


class DigitalTwinCategory(models.Model):
    category_id = models.BigAutoField(primary_key=True)
    twin_level = models.CharField(max_length=64, unique=True)
    level_name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    related_systems = models.JSONField(default=list, blank=True)
    example_data = models.JSONField(default=list, blank=True)
    use_cases = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.twin_level} {self.level_name}"


class QALog(models.Model):
    ASKER_TYPES = [("user", "User"), ("ai_agent", "AI Agent"), ("system", "System")]

    query_id = models.BigAutoField(primary_key=True)
    asker_type = models.CharField(max_length=32, choices=ASKER_TYPES, default="user")
    asker_id = models.CharField(max_length=128, blank=True)
    user_question = models.TextField()
    filters = models.JSONField(default=dict, blank=True)
    retrieved_chunks = models.JSONField(default=list, blank=True)
    answer = models.TextField(blank=True)
    cited_sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["asker_type", "asker_id", "created_at"])]


class KnowledgeNode(models.Model):
    NODE_TYPES = [
        ("equipment", "Equipment"),
        ("process", "Process"),
        ("system", "System"),
        ("risk", "Risk"),
        ("abnormal_event", "Abnormal Event"),
        ("improvement_action", "Improvement Action"),
        ("maintenance", "Maintenance"),
        ("quality_issue", "Quality Issue"),
    ]

    node_id = models.BigAutoField(primary_key=True)
    node_type = models.CharField(max_length=64, choices=NODE_TYPES)
    node_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    related_level = models.CharField(max_length=64, blank=True)
    related_system = models.CharField(max_length=64, blank=True)
    risk_level = models.CharField(max_length=64, blank=True)
    source_document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.node_name


class IngestionJob(models.Model):
    STATUSES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial_failed", "Partial Failed"),
    ]
    TRIGGER_TYPES = [("user", "User"), ("ai_agent", "AI Agent"), ("system", "System")]

    job_id = models.BigAutoField(primary_key=True)
    source_type = models.CharField(max_length=64)
    source_path = models.TextField(blank=True)
    triggered_by = models.CharField(max_length=128, blank=True)
    triggered_by_type = models.CharField(max_length=32, choices=TRIGGER_TYPES, default="user")
    status = models.CharField(max_length=32, choices=STATUSES, default="pending")
    total_files = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    failed_files = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=64, default="user")
    security_level = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

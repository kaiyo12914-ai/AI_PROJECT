from __future__ import annotations
from django.db import models
from pgvector.django import VectorField, HnswIndex

# NOTE: User model is in SQLite (default db), ProjectNotes models are in PostgreSQL.
# Cross-database ForeignKeys are not supported, so we store user ID (username) as a string.

class Project(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    created_by = models.CharField(max_length=100, blank=True, default="") # stores username
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_project"

class Membership(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user_id = models.CharField(max_length=100) # stores username
    role = models.CharField(max_length=20) # owner, editor, viewer
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_membership"
        unique_together = ("project", "user_id")

class Source(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sources")
    name = models.CharField(max_length=240)
    source_type = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_source"

class Document(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=240)
    path = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_document"

class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    uploaded_by = models.CharField(max_length=100, blank=True, default="") # stores username
    content_hash = models.CharField(max_length=128, blank=True, default="")
    raw_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_document_version"
        unique_together = ("document", "version_number")

class DocumentChunk(models.Model):
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    token_count = models.PositiveIntegerField(default=0)
    content = models.TextField()
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_document_chunk"
        unique_together = ("document_version", "chunk_index")
        indexes = [
            HnswIndex(
                name="pn_chunk_vector_idx",
                fields=["embedding"],
                opclasses=["vector_cosine_ops"]
            )
        ]

class Citation(models.Model):
    document_chunk = models.ForeignKey(DocumentChunk, on_delete=models.CASCADE, related_name="citations")
    reference_text = models.TextField()
    reference_url = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_citation"

class Conversation(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=200, blank=True, default="")
    created_by = models.CharField(max_length=100, blank=True, default="") # stores username
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_conversation"

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender_type = models.CharField(max_length=20) # 'user' or 'assistant'
    sender_id = models.CharField(max_length=100, blank=True, default="") # stores username
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_message"

class MessageCitation(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="citations")
    document_chunk = models.ForeignKey(DocumentChunk, on_delete=models.CASCADE, related_name="message_citations")
    citation_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_message_citation"

class Comment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    target_type = models.CharField(max_length=50) # 'document_version', 'document_chunk', 'message'
    target_id = models.PositiveIntegerField()
    user_id = models.CharField(max_length=100) # stores username
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_comment"

class ActivityLog(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user_id = models.CharField(max_length=100, blank=True, default="") # stores username
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.PositiveIntegerField(null=True, blank=True)
    detail_json = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projectnotes"
        db_table = "projectnotes_activity_log"
        indexes = [
            models.Index(fields=["project", "created_at"]),
        ]

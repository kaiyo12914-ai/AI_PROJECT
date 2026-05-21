from django.contrib import admin

from .models import (
    DigitalTwinCategory,
    Document,
    DocumentChunk,
    IngestionJob,
    KnowledgeNode,
    QALog,
    UserProfile,
)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("document_id", "file_name", "topic", "security_level", "uploaded_by_type", "created_at")
    search_fields = ("file_name", "original_file_name", "topic", "checksum")
    list_filter = ("file_type", "uploaded_by_type", "security_level")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("chunk_id", "document", "chunk_index", "twin_level", "isa95_level", "system_type", "security_level")
    search_fields = ("content", "section_title", "topic")
    list_filter = ("twin_level", "isa95_level", "system_type", "security_level")


admin.site.register(DigitalTwinCategory)
admin.site.register(QALog)
admin.site.register(KnowledgeNode)
admin.site.register(IngestionJob)
admin.site.register(UserProfile)

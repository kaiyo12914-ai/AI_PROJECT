# webapps/doc/admin.py
from django.contrib import admin
from webapps.doc.models import DocumentTemplate


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "doc_type",
        "short_tags",
        "updated_at",
    )
    list_filter = ("doc_type",)
    search_fields = ("title", "content")
    ordering = ("-updated_at",)

    def short_tags(self, obj):
        # tags 可能是 None / [] / 或包含非字串元素，這樣寫最穩
        if not obj.tags:
            return "-"
        return ", ".join(map(str, obj.tags))

    short_tags.short_description = "tags"
    
    def save_model(self, request, obj, form, change):
        if not obj.owner:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

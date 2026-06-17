import os
import sys
import django

# Add current workspace directory to python path
sys.path.insert(0, os.getcwd())

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
django.setup()

from webapps.vanna.models import SchemaObject, SchemaEmbedding, TrainingDocumentation, DocumentationEmbedding

from django.db.models import Count

print("=== TrainingDocumentation Grouped by DataSource ===")
counts = TrainingDocumentation.objects.values("data_source__code").annotate(count=Count("id"))
for c in counts:
    print(f"DataSource: {c['data_source__code']}, Count: {c['count']}")

print("\n=== TrainingDocumentation sample ===")
for doc in TrainingDocumentation.objects.filter(data_source__code="legacy_vanna_chroma")[:10]:
    print(f"ID: {doc.id}, Title: {doc.title}, Content Length: {len(doc.documentation)}")
    print(f"Content: {doc.documentation[:100]}\n")

print("\n=== SchemaObject (documentation) remaining ===")
virtual_objects = SchemaObject.objects.filter(
    object_name__startswith="VANNA_DOCUMENTATION_"
) | SchemaObject.objects.filter(object_name="VANNA_LEGACY_DOCUMENTATION")
print("Count:", virtual_objects.count())
for obj in virtual_objects:
    print(f"ID: {obj.id}, Schema: {obj.schema_name}, Name: {obj.object_name}")

print("\n=== SchemaEmbedding (documentation) remaining ===")
se_docs = SchemaEmbedding.objects.filter(chunk_type="documentation")
print("Count:", se_docs.count())

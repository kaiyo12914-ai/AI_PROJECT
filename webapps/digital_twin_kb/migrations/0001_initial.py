import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import pgvector.django


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name="DigitalTwinCategory",
            fields=[
                ("category_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("twin_level", models.CharField(max_length=64, unique=True)),
                ("level_name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("related_systems", models.JSONField(blank=True, default=list)),
                ("example_data", models.JSONField(blank=True, default=list)),
                ("use_cases", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("document_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("file_name", models.CharField(max_length=255)),
                ("original_file_name", models.CharField(max_length=255)),
                ("file_type", models.CharField(max_length=32)),
                ("file_path", models.TextField()),
                ("file_size", models.BigIntegerField(default=0)),
                ("source", models.CharField(blank=True, max_length=255)),
                ("uploaded_by", models.CharField(blank=True, max_length=128)),
                ("uploaded_by_type", models.CharField(choices=[("user", "User"), ("ai_agent", "AI Agent"), ("system", "System")], default="user", max_length=32)),
                ("topic", models.CharField(blank=True, max_length=255)),
                ("security_level", models.PositiveSmallIntegerField(default=1)),
                ("checksum", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="IngestionJob",
            fields=[
                ("job_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("source_type", models.CharField(max_length=64)),
                ("source_path", models.TextField(blank=True)),
                ("triggered_by", models.CharField(blank=True, max_length=128)),
                ("triggered_by_type", models.CharField(choices=[("user", "User"), ("ai_agent", "AI Agent"), ("system", "System")], default="user", max_length=32)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed"), ("partial_failed", "Partial Failed")], default="pending", max_length=32)),
                ("total_files", models.PositiveIntegerField(default=0)),
                ("processed_files", models.PositiveIntegerField(default=0)),
                ("failed_files", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="QALog",
            fields=[
                ("query_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("asker_type", models.CharField(choices=[("user", "User"), ("ai_agent", "AI Agent"), ("system", "System")], default="user", max_length=32)),
                ("asker_id", models.CharField(blank=True, max_length=128)),
                ("user_question", models.TextField()),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("retrieved_chunks", models.JSONField(blank=True, default=list)),
                ("answer", models.TextField(blank=True)),
                ("cited_sources", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                ("chunk_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("chunk_index", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("page_number", models.PositiveIntegerField(blank=True, null=True)),
                ("section_title", models.CharField(blank=True, max_length=255)),
                ("twin_level", models.CharField(blank=True, max_length=64)),
                ("isa95_level", models.CharField(blank=True, max_length=64)),
                ("system_type", models.CharField(blank=True, max_length=64)),
                ("topic", models.CharField(blank=True, max_length=255)),
                ("keywords", models.JSONField(blank=True, default=list)),
                ("security_level", models.PositiveSmallIntegerField(default=1)),
                ("embedding", pgvector.django.VectorField(dimensions=384)),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="digital_twin_kb.document")),
            ],
            options={"ordering": ["document_id", "chunk_index"]},
        ),
        migrations.CreateModel(
            name="KnowledgeNode",
            fields=[
                ("node_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("node_type", models.CharField(choices=[("equipment", "Equipment"), ("process", "Process"), ("system", "System"), ("risk", "Risk"), ("abnormal_event", "Abnormal Event"), ("improvement_action", "Improvement Action"), ("maintenance", "Maintenance"), ("quality_issue", "Quality Issue")], max_length=64)),
                ("node_name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("related_level", models.CharField(blank=True, max_length=64)),
                ("related_system", models.CharField(blank=True, max_length=64)),
                ("risk_level", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source_document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="digital_twin_kb.document")),
            ],
        ),
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(default="user", max_length=64)),
                ("security_level", models.PositiveSmallIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(model_name="document", index=models.Index(fields=["topic"], name="digital_twi_topic_99deb9_idx")),
        migrations.AddIndex(model_name="document", index=models.Index(fields=["security_level"], name="digital_twi_securit_bcb869_idx")),
        migrations.AddIndex(model_name="document", index=models.Index(fields=["checksum"], name="digital_twi_checksu_c73f7e_idx")),
        migrations.AddIndex(model_name="documentchunk", index=models.Index(fields=["security_level"], name="digital_twi_securit_201d1a_idx")),
        migrations.AddIndex(model_name="documentchunk", index=models.Index(fields=["twin_level"], name="digital_twi_twin_le_743836_idx")),
        migrations.AddIndex(model_name="documentchunk", index=models.Index(fields=["isa95_level"], name="digital_twi_isa95_l_203ab9_idx")),
        migrations.AddIndex(model_name="documentchunk", index=models.Index(fields=["system_type"], name="digital_twi_system__2e5cc6_idx")),
        migrations.AddIndex(model_name="documentchunk", index=models.Index(fields=["topic"], name="digital_twi_topic_3f58e6_idx")),
        migrations.AddConstraint(model_name="documentchunk", constraint=models.UniqueConstraint(fields=("document", "chunk_index"), name="uq_document_chunk_index")),
        migrations.AddIndex(model_name="qalog", index=models.Index(fields=["asker_type", "asker_id", "created_at"], name="digital_twi_asker_t_b60097_idx")),
        migrations.RunSQL(
            sql="CREATE INDEX IF NOT EXISTS digital_twin_kb_chunk_embedding_hnsw_idx ON digital_twin_kb_documentchunk USING hnsw (embedding vector_cosine_ops);",
            reverse_sql="DROP INDEX IF EXISTS digital_twin_kb_chunk_embedding_hnsw_idx;",
        ),
    ]

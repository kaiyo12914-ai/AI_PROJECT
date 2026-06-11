import pgvector.django
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name="MeetingRecordEmbedding",
            fields=[
                ("doc_id", models.CharField(max_length=128, primary_key=True, serialize=False)),
                ("case_id", models.CharField(blank=True, max_length=64)),
                ("item_no", models.CharField(blank=True, max_length=64)),
                ("case_name", models.CharField(blank=True, max_length=255)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("directive", models.TextField(blank=True)),
                ("status", models.TextField(blank=True)),
                ("dept_name", models.CharField(blank=True, max_length=128)),
                ("dept_code", models.CharField(blank=True, max_length=64)),
                ("source_text", models.TextField()),
                ("record_checksum", models.CharField(db_index=True, max_length=64)),
                ("embedding", pgvector.django.VectorField(blank=True, dimensions=1024, null=True)),
                ("embedding_model", models.CharField(blank=True, default="", max_length=160)),
                ("embedding_dimension", models.PositiveIntegerField(default=1024)),
                ("source_updated_at", models.DateField(blank=True, null=True)),
                ("synced_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "meetingreply_record_embedding",
            },
        ),
        migrations.AddIndex(
            model_name="meetingrecordembedding",
            index=models.Index(fields=["case_id"], name="meetingrepl_case_id_1d5e55_idx"),
        ),
        migrations.AddIndex(
            model_name="meetingrecordembedding",
            index=models.Index(fields=["item_no"], name="meetingrepl_item_no_8a71ae_idx"),
        ),
        migrations.AddIndex(
            model_name="meetingrecordembedding",
            index=models.Index(fields=["dept_code"], name="meetingrepl_dept_co_5ea9ae_idx"),
        ),
        migrations.AddIndex(
            model_name="meetingrecordembedding",
            index=models.Index(fields=["source_updated_at"], name="meetingrepl_source__5ea7da_idx"),
        ),
        migrations.RunSQL(
            sql="CREATE INDEX IF NOT EXISTS meetingreply_record_embedding_hnsw_idx ON meetingreply_record_embedding USING hnsw (embedding vector_cosine_ops);",
            reverse_sql="DROP INDEX IF EXISTS meetingreply_record_embedding_hnsw_idx;",
        ),
    ]

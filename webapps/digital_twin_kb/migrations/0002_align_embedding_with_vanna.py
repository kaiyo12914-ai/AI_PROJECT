from django.db import migrations
import pgvector.django


class Migration(migrations.Migration):
    dependencies = [
        ("digital_twin_kb", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    DROP INDEX IF EXISTS digital_twin_kb_chunk_embedding_hnsw_idx;
                    ALTER TABLE digital_twin_kb_documentchunk
                    ALTER COLUMN embedding DROP NOT NULL;
                    UPDATE digital_twin_kb_documentchunk
                    SET embedding = NULL;
                    ALTER TABLE digital_twin_kb_documentchunk
                    ALTER COLUMN embedding TYPE vector(1024);
                    CREATE INDEX IF NOT EXISTS digital_twin_kb_chunk_embedding_hnsw_idx
                    ON digital_twin_kb_documentchunk
                    USING hnsw (embedding vector_cosine_ops);
                    """,
                    reverse_sql="""
                    DROP INDEX IF EXISTS digital_twin_kb_chunk_embedding_hnsw_idx;
                    UPDATE digital_twin_kb_documentchunk
                    SET embedding = NULL;
                    ALTER TABLE digital_twin_kb_documentchunk
                    ALTER COLUMN embedding TYPE vector(384);
                    ALTER TABLE digital_twin_kb_documentchunk
                    ALTER COLUMN embedding SET NOT NULL;
                    CREATE INDEX IF NOT EXISTS digital_twin_kb_chunk_embedding_hnsw_idx
                    ON digital_twin_kb_documentchunk
                    USING hnsw (embedding vector_cosine_ops);
                    """,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="documentchunk",
                    name="embedding",
                    field=pgvector.django.VectorField(blank=True, null=True, dimensions=1024),
                ),
            ],
        ),
    ]

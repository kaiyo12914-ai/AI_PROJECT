from django.db import migrations, models
import pgvector.django.vector
import webapps.vanna.models


FORWARD_SQL = """
DROP INDEX IF EXISTS nl2sql_schema_vec_idx;
DROP INDEX IF EXISTS nl2sql_example_vec_idx;

UPDATE nl2sql_schema_embedding
SET embedding = NULL,
    embedding_model = '',
    embedding_dimension = 1024;

UPDATE nl2sql_example_embedding
SET embedding = NULL,
    embedding_model = '',
    embedding_dimension = 1024;

ALTER TABLE nl2sql_schema_embedding
ALTER COLUMN embedding TYPE vector(1024);

ALTER TABLE nl2sql_example_embedding
ALTER COLUMN embedding TYPE vector(1024);

CREATE INDEX nl2sql_schema_vec_idx
ON nl2sql_schema_embedding
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX nl2sql_example_vec_idx
ON nl2sql_example_embedding
USING hnsw (embedding vector_cosine_ops);
"""


REVERSE_SQL = """
DROP INDEX IF EXISTS nl2sql_schema_vec_idx;
DROP INDEX IF EXISTS nl2sql_example_vec_idx;

UPDATE nl2sql_schema_embedding
SET embedding = NULL,
    embedding_model = '',
    embedding_dimension = 1536;

UPDATE nl2sql_example_embedding
SET embedding = NULL,
    embedding_model = '',
    embedding_dimension = 1536;

ALTER TABLE nl2sql_schema_embedding
ALTER COLUMN embedding TYPE vector(1536);

ALTER TABLE nl2sql_example_embedding
ALTER COLUMN embedding TYPE vector(1536);

CREATE INDEX nl2sql_schema_vec_idx
ON nl2sql_schema_embedding
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX nl2sql_example_vec_idx
ON nl2sql_example_embedding
USING hnsw (embedding vector_cosine_ops);
"""


class Migration(migrations.Migration):

    dependencies = [
        ("vanna_integration", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="schemaembedding",
                    name="embedding",
                    field=pgvector.django.vector.VectorField(blank=True, dimensions=1024, null=True),
                ),
                migrations.AlterField(
                    model_name="schemaembedding",
                    name="embedding_dimension",
                    field=models.PositiveIntegerField(default=webapps.vanna.models._embedding_dimensions),
                ),
                migrations.AlterField(
                    model_name="exampleembedding",
                    name="embedding",
                    field=pgvector.django.vector.VectorField(blank=True, dimensions=1024, null=True),
                ),
                migrations.AlterField(
                    model_name="exampleembedding",
                    name="embedding_dimension",
                    field=models.PositiveIntegerField(default=webapps.vanna.models._embedding_dimensions),
                ),
            ],
        ),
    ]

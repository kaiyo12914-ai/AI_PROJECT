from __future__ import annotations

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


def _embedding_dimensions() -> int:
    return int(getattr(settings, "NL2SQL_EMBEDDING_DIMENSION", 1024) or 1024)


class DataSource(models.Model):
    DB_TYPE_CHOICES = [
        ("postgresql", "PostgreSQL"),
        ("oracle", "Oracle"),
    ]

    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    db_type = models.CharField(max_length=20, choices=DB_TYPE_CHOICES)
    db_profile = models.CharField(max_length=120, blank=True, default="")
    default_schema = models.CharField(max_length=120, blank=True, default="")
    enabled = models.BooleanField(default=True)
    execute_enabled = models.BooleanField(default=False)
    config_json = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_data_source"
        indexes = [
            models.Index(fields=["db_type", "enabled"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.db_type})"


class SchemaObject(models.Model):
    OBJECT_TYPE_CHOICES = [
        ("table", "Table"),
        ("view", "View"),
        ("materialized_view", "Materialized View"),
    ]

    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="schema_objects")
    schema_name = models.CharField(max_length=120)
    object_name = models.CharField(max_length=160)
    object_type = models.CharField(max_length=32, choices=OBJECT_TYPE_CHOICES)
    description = models.TextField(blank=True, default="")
    columns_json = models.JSONField(blank=True, default=list)
    ddl_text = models.TextField(blank=True, default="")
    row_estimate = models.BigIntegerField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_schema_object"
        constraints = [
            models.UniqueConstraint(
                fields=["data_source", "schema_name", "object_name"],
                name="uq_nl2sql_schema_object",
            )
        ]
        indexes = [
            models.Index(fields=["data_source", "is_enabled"]),
            models.Index(fields=["schema_name", "object_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.schema_name}.{self.object_name}"


class SchemaEmbedding(models.Model):
    CHUNK_TYPE_CHOICES = [
        ("ddl", "DDL"),
        ("columns", "Columns"),
        ("documentation", "Documentation"),
    ]

    schema_object = models.ForeignKey(SchemaObject, on_delete=models.CASCADE, related_name="embeddings")
    chunk_type = models.CharField(max_length=32, choices=CHUNK_TYPE_CHOICES)
    chunk_text = models.TextField()
    embedding = VectorField(dimensions=_embedding_dimensions(), null=True, blank=True)
    embedding_model = models.CharField(max_length=160, blank=True, default="")
    embedding_dimension = models.PositiveIntegerField(default=_embedding_dimensions)
    content_hash = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nl2sql_schema_embedding"
        indexes = [
            models.Index(fields=["schema_object", "chunk_type"]),
            models.Index(fields=["content_hash"]),
            HnswIndex(
                name="nl2sql_schema_vec_idx",
                fields=["embedding"],
                opclasses=["vector_cosine_ops"],
            ),
        ]


class TrainingExample(models.Model):
    REVIEW_STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="training_examples")
    question = models.TextField()
    sql_text = models.TextField()
    dialect = models.CharField(max_length=32, blank=True, default="")
    tags_json = models.JSONField(blank=True, default=list)
    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default="draft")
    created_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_training_example"
        indexes = [
            models.Index(fields=["data_source", "review_status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return self.question[:80]


class ExampleEmbedding(models.Model):
    training_example = models.ForeignKey(TrainingExample, on_delete=models.CASCADE, related_name="embeddings")
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="example_embeddings")
    question_text = models.TextField()
    sql_text = models.TextField()
    embedding = VectorField(dimensions=_embedding_dimensions(), null=True, blank=True)
    embedding_model = models.CharField(max_length=160, blank=True, default="")
    embedding_dimension = models.PositiveIntegerField(default=_embedding_dimensions)
    content_hash = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nl2sql_example_embedding"
        indexes = [
            models.Index(fields=["data_source"]),
            models.Index(fields=["content_hash"]),
            HnswIndex(
                name="nl2sql_example_vec_idx",
                fields=["embedding"],
                opclasses=["vector_cosine_ops"],
            ),
        ]


class VannaTrainingSync(models.Model):
    SYNC_TYPE_CHOICES = [
        ("ddl", "DDL"),
        ("documentation", "Documentation"),
        ("example", "Example"),
    ]
    SYNC_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("synced", "Synced"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="vanna_training_syncs")
    sync_type = models.CharField(max_length=32, choices=SYNC_TYPE_CHOICES)
    source_object_id = models.BigIntegerField(null=True, blank=True)
    vanna_training_id = models.CharField(max_length=160, blank=True, default="")
    content_hash = models.CharField(max_length=128, blank=True, default="")
    sync_status = models.CharField(max_length=20, choices=SYNC_STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_vanna_training_sync"
        indexes = [
            models.Index(fields=["data_source", "sync_type", "sync_status"]),
            models.Index(fields=["content_hash"]),
        ]


class BusinessTerm(models.Model):
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="business_terms")
    term = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    mapped_schema = models.CharField(max_length=120, blank=True, default="")
    mapped_tables_json = models.JSONField(blank=True, default=list)
    mapped_columns_json = models.JSONField(blank=True, default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_business_term"
        constraints = [
            models.UniqueConstraint(fields=["data_source", "term"], name="uq_nl2sql_business_term")
        ]
        indexes = [
            models.Index(fields=["data_source", "term"]),
        ]


class UserDataSourceAcl(models.Model):
    user_id = models.CharField(max_length=128)
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="user_acls")
    can_generate = models.BooleanField(default=True)
    can_execute = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nl2sql_user_data_source_acl"
        constraints = [
            models.UniqueConstraint(fields=["user_id", "data_source"], name="uq_nl2sql_user_data_source_acl")
        ]


class TablePolicy(models.Model):
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="table_policies")
    schema_name = models.CharField(max_length=120)
    table_name = models.CharField(max_length=160)
    is_allowed = models.BooleanField(default=True)
    requires_where = models.BooleanField(default=False)
    max_row_limit = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "nl2sql_table_policy"
        constraints = [
            models.UniqueConstraint(
                fields=["data_source", "schema_name", "table_name"],
                name="uq_nl2sql_table_policy",
            )
        ]


class ColumnPolicy(models.Model):
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="column_policies")
    schema_name = models.CharField(max_length=120)
    table_name = models.CharField(max_length=160)
    column_name = models.CharField(max_length=160)
    is_allowed = models.BooleanField(default=True)
    is_sensitive = models.BooleanField(default=False)
    mask_type = models.CharField(max_length=40, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "nl2sql_column_policy"
        constraints = [
            models.UniqueConstraint(
                fields=["data_source", "schema_name", "table_name", "column_name"],
                name="uq_nl2sql_column_policy",
            )
        ]


class QueryLog(models.Model):
    data_source = models.ForeignKey(DataSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="query_logs")
    user_id = models.CharField(max_length=128, blank=True, default="")
    question = models.TextField()
    normalized_question = models.TextField(blank=True, default="")
    retrieved_context_json = models.JSONField(blank=True, default=dict)
    generated_sql = models.TextField(blank=True, default="")
    cleaned_sql = models.TextField(blank=True, default="")
    guard_status = models.CharField(max_length=32, blank=True, default="")
    guard_message = models.TextField(blank=True, default="")
    guard_rules_json = models.JSONField(blank=True, default=list)
    final_sql = models.TextField(blank=True, default="")
    execution_status = models.CharField(max_length=32, blank=True, default="")
    row_count = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    engine_version = models.CharField(max_length=80, blank=True, default="")
    prompt_version = models.CharField(max_length=80, blank=True, default="")
    guard_version = models.CharField(max_length=80, blank=True, default="")
    retriever_version = models.CharField(max_length=80, blank=True, default="")
    vanna_version = models.CharField(max_length=80, blank=True, default="")
    vanna_training_version = models.CharField(max_length=80, blank=True, default="")
    vanna_response_json = models.JSONField(blank=True, default=dict)
    model_name = models.CharField(max_length=160, blank=True, default="")
    model_parameters_json = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nl2sql_query_log"
        indexes = [
            models.Index(fields=["data_source", "created_at"]),
            models.Index(fields=["user_id", "created_at"]),
            models.Index(fields=["guard_status"]),
            models.Index(fields=["execution_status"]),
        ]


class ReviewQueue(models.Model):
    REVIEW_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    query_log = models.ForeignKey(QueryLog, on_delete=models.CASCADE, related_name="reviews")
    reason = models.TextField(blank=True, default="")
    suggested_sql = models.TextField(blank=True, default="")
    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default="pending")
    reviewed_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_review_queue"
        indexes = [
            models.Index(fields=["review_status", "created_at"]),
        ]


class EvalCase(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="eval_cases")
    question = models.TextField()
    expected_sql = models.TextField(blank=True, default="")
    expected_tables_json = models.JSONField(blank=True, default=list)
    expected_columns_json = models.JSONField(blank=True, default=list)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="easy")
    category = models.CharField(max_length=80, blank=True, default="")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nl2sql_eval_case"
        indexes = [
            models.Index(fields=["data_source", "enabled"]),
            models.Index(fields=["difficulty", "category"]),
        ]


class FailedQueryRecord(models.Model):
    STATUS_CHOICES = [
        ("pending", "待處理"),
        ("optimized", "已完成優化"),
        ("ignored", "忽略/不處理"),
    ]

    query_log = models.OneToOneField(
        "QueryLog",
        on_delete=models.CASCADE,
        related_name="failed_record",
        verbose_name="關聯查詢日誌"
    )
    question = models.TextField(verbose_name="自然語言提問")
    failed_sql = models.TextField(verbose_name="失敗之 SQL")
    error_message = models.TextField(verbose_name="錯誤訊息")
    data_source_code = models.CharField(max_length=80, blank=True, default="", verbose_name="資料來源編號")
    analysis = models.TextField(blank=True, default="", verbose_name="失敗根因剖析")
    action_taken = models.TextField(blank=True, default="", verbose_name="精進措施 (如修正 DDL/新增 SQL 範例)")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending", verbose_name="處理狀態")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_failed_query_record"
        ordering = ["-created_at"]
        verbose_name = "失敗語法精進記錄"

    def __str__(self) -> str:
        return f"Fail Log {self.query_log_id}: {self.question[:40]}"


class TrainingDocumentation(models.Model):
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="training_documentations")
    title = models.CharField(max_length=255, blank=True, default="")
    documentation = models.TextField()
    created_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nl2sql_training_documentation"
        indexes = [
            models.Index(fields=["data_source"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return self.title[:80] if self.title else self.documentation[:80]


class DocumentationEmbedding(models.Model):
    training_documentation = models.ForeignKey(TrainingDocumentation, on_delete=models.CASCADE, related_name="embeddings")
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="documentation_embeddings")
    title = models.CharField(max_length=255, blank=True, default="")
    documentation_text = models.TextField()
    embedding = VectorField(dimensions=_embedding_dimensions(), null=True, blank=True)
    embedding_model = models.CharField(max_length=160, blank=True, default="")
    embedding_dimension = models.PositiveIntegerField(default=_embedding_dimensions)
    content_hash = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nl2sql_documentation_embedding"
        indexes = [
            models.Index(fields=["data_source"]),
            models.Index(fields=["content_hash"]),
            HnswIndex(
                name="nl2sql_doc_vec_idx",
                fields=["embedding"],
                opclasses=["vector_cosine_ops"],
            ),
        ]


from django.apps import AppConfig


class RagOracleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webapps.rag_oracle"
    label = "rag_oracle"
    verbose_name = "RAG Oracle（Oracle19i + Chroma）"

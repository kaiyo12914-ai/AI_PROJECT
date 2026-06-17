from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from webapps.vanna.embedding_factory import (
    expected_embedding_dimension,
    get_nl2sql_embedding_model,
    get_nl2sql_embedding_provider,
)


class VannaEmbeddingFactoryTestCase(SimpleTestCase):
    @override_settings(
        GLOBAL_EMBEDDING_PROVIDER="LM_STUDIO",
        GLOBAL_OLLAMA_EMBEDDING_MODEL="snowflake-arctic-embed2",
        GLOBAL_OLLAMA_EMBEDDING_BASE_URL="http://example-ollama:11434",
    )
    @patch("webapps.llm.embedding_factory._build_ollama_embeddings")
    def test_nl2sql_provider_normalizes_lm_studio_to_ollama(self, mock_build):
        sentinel = object()
        mock_build.return_value = sentinel

        model = get_nl2sql_embedding_model()

        self.assertIs(model, sentinel)
        self.assertEqual(get_nl2sql_embedding_provider(), "OLLAMA")
        mock_build.assert_called_once_with(
            model_name="snowflake-arctic-embed2",
            base_url="http://example-ollama:11434",
        )

    @override_settings(
        GLOBAL_EMBEDDING_PROVIDER="OPENAI",
        GLOBAL_OPENAI_EMBEDDING_MODEL="text-embedding-3-small",
    )
    @patch("webapps.llm.embedding_factory._build_openai_embeddings")
    def test_nl2sql_provider_can_be_configured_independently(self, mock_build):
        sentinel = object()
        mock_build.return_value = sentinel

        model = get_nl2sql_embedding_model()

        self.assertIs(model, sentinel)
        self.assertEqual(get_nl2sql_embedding_provider(), "OPENAI")
        mock_build.assert_called_once_with(model_name="text-embedding-3-small")

    @override_settings(GLOBAL_EMBEDDING_DIMENSION=1024)
    def test_expected_embedding_dimension_uses_nl2sql_setting(self):
        self.assertEqual(expected_embedding_dimension(), 1024)

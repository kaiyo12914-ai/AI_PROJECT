from webapps.chatbotui.service import allowed_model_types, normalize_model_type
from webapps.llm.llm_factory import _looks_non_chat_openai_model, _normalize_provider_for_env


def test_model_type_controls_provider_regardless_of_env(monkeypatch):
    monkeypatch.setenv("ENV", "INT")
    monkeypatch.setenv("MODEL_TYPE", "OPENAI")

    assert normalize_model_type("OLLAMA") == "OPENAI"


def test_model_type_allows_configured_ollama(monkeypatch):
    monkeypatch.setenv("ENV", "EXT")
    monkeypatch.setenv("MODEL_TYPE", "OLLAMA")

    assert normalize_model_type("OLLAMA") == "OLLAMA"


def test_environment_does_not_change_configured_model_type(monkeypatch):
    monkeypatch.setenv("ENV", "EXT")
    monkeypatch.setenv("MODEL_TYPE", "OPENAI")
    assert allowed_model_types() == {"OPENAI"}

    monkeypatch.setenv("ENV", "INT")
    assert allowed_model_types() == {"OPENAI"}


def test_modern_codex_model_is_treated_as_chat_capable():
    assert _looks_non_chat_openai_model("gpt-5.3-codex") is False


def test_provider_normalization_does_not_depend_on_env(monkeypatch):
    monkeypatch.setenv("ENV", "EXT")
    assert _normalize_provider_for_env("OLLAMA") == "OLLAMA"

    monkeypatch.setenv("ENV", "INT")
    assert _normalize_provider_for_env("OPENAI") == "OPENAI"

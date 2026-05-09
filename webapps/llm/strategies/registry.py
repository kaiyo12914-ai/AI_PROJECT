from __future__ import annotations

from .base import ChatStrategy, EmbeddingStrategy
from .chat_strategies import (
    GoogleChatStrategy,
    LMStudioChatStrategy,
    OllamaChatStrategy,
    OpenAIChatStrategy,
)
from .embedding_strategies import (
    GoogleEmbeddingStrategy,
    OllamaEmbeddingStrategy,
    OpenAIEmbeddingStrategy,
)


def build_chat_registry(deps) -> dict[str, ChatStrategy]:
    return {
        "GOOGLE": GoogleChatStrategy(deps),
        "OLLAMA": OllamaChatStrategy(deps),
        "OPENAI": OpenAIChatStrategy(deps),
        "LM_STUDIO": LMStudioChatStrategy(deps),
    }


def build_embedding_registry(deps) -> dict[str, EmbeddingStrategy]:
    ollama = OllamaEmbeddingStrategy()
    return {
        "GOOGLE": GoogleEmbeddingStrategy(deps),
        "OPENAI": OpenAIEmbeddingStrategy(),
        "OLLAMA": ollama,
        "LM_STUDIO": ollama,
    }

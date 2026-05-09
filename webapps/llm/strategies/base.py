from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class ChatBuildContext:
    temperature: float | None
    timeout: int | None
    model_name: str | None


@dataclass(frozen=True)
class ChatStrategyDeps:
    make_google: Callable[..., Any]
    make_ollama: Callable[..., Any]
    make_openai: Callable[..., Any]
    make_lm_studio: Callable[..., Any]
    resolve_provider_fallback: Callable[[str], str]
    logger: Any


@dataclass(frozen=True)
class EmbeddingStrategyDeps:
    resolve_provider_fallback: Callable[[str], str]
    logger: Any


class ChatStrategy(Protocol):
    def build(self, ctx: ChatBuildContext) -> Any:
        ...


class EmbeddingStrategy(Protocol):
    def build(self) -> Any:
        ...

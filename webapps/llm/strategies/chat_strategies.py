from __future__ import annotations

from .base import ChatBuildContext, ChatStrategy, ChatStrategyDeps


class GoogleChatStrategy(ChatStrategy):
    def __init__(self, deps: ChatStrategyDeps) -> None:
        self._deps = deps

    def build(self, ctx: ChatBuildContext):
        try:
            return self._deps.make_google(temperature=ctx.temperature, timeout=ctx.timeout)
        except ModuleNotFoundError as exc:
            if "langchain_google_genai" not in str(exc):
                raise
            fallback = self._deps.resolve_provider_fallback("GOOGLE")
            if fallback == "GOOGLE":
                raise RuntimeError(
                    "MODEL_TYPE=GOOGLE requires 'langchain_google_genai'. "
                    "Install package or set MISSING_PROVIDER_FALLBACK=LM_STUDIO/OPENAI/OLLAMA."
                ) from exc
            self._deps.logger.warning("[LLM] GOOGLE provider missing (%s); fallback=%s", exc, fallback)
            if fallback == "LM_STUDIO":
                return self._deps.make_lm_studio(temperature=ctx.temperature, timeout=ctx.timeout)
            if fallback == "OPENAI":
                return self._deps.make_openai(temperature=ctx.temperature, timeout=ctx.timeout)
            return self._deps.make_ollama(
                temperature=ctx.temperature,
                timeout=ctx.timeout,
                model_name=ctx.model_name,
            )


class OllamaChatStrategy(ChatStrategy):
    def __init__(self, deps: ChatStrategyDeps) -> None:
        self._deps = deps

    def build(self, ctx: ChatBuildContext):
        return self._deps.make_ollama(
            temperature=ctx.temperature,
            timeout=ctx.timeout,
            model_name=ctx.model_name,
        )


class OpenAIChatStrategy(ChatStrategy):
    def __init__(self, deps: ChatStrategyDeps) -> None:
        self._deps = deps

    def build(self, ctx: ChatBuildContext):
        return self._deps.make_openai(temperature=ctx.temperature, timeout=ctx.timeout)


class LMStudioChatStrategy(ChatStrategy):
    def __init__(self, deps: ChatStrategyDeps) -> None:
        self._deps = deps

    def build(self, ctx: ChatBuildContext):
        return self._deps.make_lm_studio(temperature=ctx.temperature, timeout=ctx.timeout)

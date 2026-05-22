# webapps/llm/llm_factory.py
import os
import inspect
import logging
from urllib.parse import urlparse

from dotenv import load_dotenv
from webapps.llm.strategies import (
    ChatBuildContext,
    ChatStrategyDeps,
    EmbeddingStrategyDeps,
    build_chat_registry,
    build_embedding_registry,
)

load_dotenv()
logger = logging.getLogger(__name__)

def _is_int_env() -> bool:
    return (os.getenv("ENV") or "").strip().upper() == "INT"


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


# -------------------------
# ✅ 通用（你 .env 的 MODEL_*）
# -------------------------
def _model_temperature_default() -> float:
    return _f("MODEL_TEMPERATURE", 0.2)


def _model_timeout_default() -> int:
    return _i("MODEL_TIMEOUT", 120)


def _extract_host_from_base_url(base_url: str) -> str:
    """
    從 OLLAMA_BASE_URL 解析 hostname
    - 支援: http://host:11434 / https://host / host:11434 / host
    """
    s = (base_url or "").strip()
    if not s:
        return ""
    if "://" not in s:
        s = "http://" + s
    try:
        u = urlparse(s)
        return (u.hostname or "").strip()
    except Exception:
        return ""


def _append_no_proxy_host(host: str) -> None:
    """
    確保 NO_PROXY / no_proxy 包含 host（逗號分隔）
    - 安全可重複呼叫
    - 不依賴其他模組也可運作（若 webapps.common.net 存在則優先用）
    """
    host = (host or "").strip()
    if not host:
        return

    # ✅ 若你已經建立 webapps/common/net.py 的 ensure_no_proxy，就會走這條
    try:
        from webapps.common.net import ensure_no_proxy  # type: ignore
        ensure_no_proxy([host])
        return
    except Exception:
        pass

    # fallback：合併 NO_PROXY + no_proxy 並去重（case-insensitive）
    cur = []
    for k in ("NO_PROXY", "no_proxy"):
        cur += [x.strip() for x in (os.environ.get(k) or "").split(",") if x.strip()]

    merged = []
    seen = set()
    for x in cur + [host]:
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(x)

    val = ",".join(merged)
    os.environ["NO_PROXY"] = val
    os.environ["no_proxy"] = val


def _ollama_fallback_models(primary_model: str) -> list[str]:
    """
    Fallback order when primary Ollama model crashes at runtime.
    Override by OLLAMA_FALLBACK_MODELS, e.g.:
      OLLAMA_FALLBACK_MODELS=gemma3:4b,qwen3:8b
    """
    raw = (os.getenv("OLLAMA_FALLBACK_MODELS") or "gemma3:4b,qwen3:8b").strip()
    out: list[str] = []
    seen = set()
    for x in raw.split(","):
        m = (x or "").strip()
        if not m:
            continue
        if m == primary_model:
            continue
        k = m.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return out


def _should_try_ollama_fallback(err: Exception) -> bool:
    s = str(err or "").lower()
    return (
        "runner process has terminated" in s
        or "exit status" in s
        or "responseerror" in s
    )

def _resolve_provider_fallback(primary: str) -> str:
    explicit = (os.getenv("MISSING_PROVIDER_FALLBACK") or "").strip().upper()
    if _is_int_env():
        if explicit in {"LM_STUDIO", "OLLAMA"}:
            return explicit
        if explicit in {"GOOGLE", "OPENAI"}:
            logger.warning("[LLM] Ignore external fallback=%s under ENV=INT", explicit)
    else:
        if explicit in {"GOOGLE", "OPENAI", "OLLAMA", "LM_STUDIO"}:
            return explicit
    # Prefer internal providers by default.
    if os.getenv("LM_STUDIO_BASE_URL"):
        return "LM_STUDIO"
    if os.getenv("OLLAMA_BASE_URL"):
        return "OLLAMA"
    if primary == "GOOGLE":
        return "LM_STUDIO"
    return "OLLAMA"


def _is_openai_quota_error(err: Exception) -> bool:
    s = str(err or "").lower()
    return (
        "insufficient_quota" in s
        or "you exceeded your current quota" in s
    )


def _resolve_openai_runtime_fallback() -> str:
    fallback = (os.getenv("OPENAI_RUNTIME_FALLBACK") or "").strip().upper()
    if _is_int_env():
        if fallback in {"OPENAI", "GOOGLE"}:
            logger.warning("[LLM] Ignore OPENAI_RUNTIME_FALLBACK=%s under ENV=INT", fallback)
            return ""
        if fallback in {"OLLAMA", "LM_STUDIO"}:
            return fallback
        return ""
    if fallback in {"GOOGLE", "OLLAMA", "LM_STUDIO"}:
        return fallback
    return ""

def _looks_non_chat_openai_model(model: str) -> bool:
    m = (model or "").strip().lower()
    if not m:
        return False
    # Completion-only or clearly non-chat families.
    bad_tokens = (
        "instruct",
        "text-",
        "codex",
        "davinci",
        "babbage",
        "curie",
        "ada",
    )
    return any(t in m for t in bad_tokens)


def _normalize_provider_for_env(provider: str) -> str:
    p = (provider or "").strip().upper()
    if not _is_int_env():
        return p
    if p in {"GOOGLE", "OPENAI"}:
        internal = _resolve_provider_fallback(p)
        if internal not in {"OLLAMA", "LM_STUDIO"}:
            internal = "LM_STUDIO" if os.getenv("LM_STUDIO_BASE_URL") else "OLLAMA"
        logger.warning("[LLM] ENV=INT remap provider %s -> %s", p, internal)
        return internal
    return p


_CHAT_STRATEGY_REGISTRY = None
_EMBEDDING_STRATEGY_REGISTRY = None


def _get_chat_strategy_registry():
    global _CHAT_STRATEGY_REGISTRY
    if _CHAT_STRATEGY_REGISTRY is None:
        deps = ChatStrategyDeps(
            make_google=_make_google,
            make_ollama=_make_ollama,
            make_openai=_make_openai,
            make_lm_studio=_make_lm_studio,
            resolve_provider_fallback=_resolve_provider_fallback,
            logger=logger,
        )
        _CHAT_STRATEGY_REGISTRY = build_chat_registry(deps)
    return _CHAT_STRATEGY_REGISTRY


def get_chat_model(temperature: float | None = None, timeout: int | None = None, model_type: str | None = None, model_name: str | None = None):
    """Create chat LLM instance by MODEL_TYPE with provider fallback support."""
    provider = _normalize_provider_for_env((model_type or os.getenv("MODEL_TYPE") or "OLLAMA"))
    strategy = _get_chat_strategy_registry().get(provider)
    if not strategy:
        raise ValueError(f"Unknown MODEL_TYPE={provider}. Use GOOGLE/OLLAMA/OPENAI/LM_STUDIO.")
    return strategy.build(
        ChatBuildContext(
            temperature=temperature,
            timeout=timeout,
            model_name=model_name,
        )
    )

# -------------------------
# ✅ 依你 .env：MODEL_TIMEOUT / MODEL_TEMPERATURE fallback
# - 若呼叫端沒傳 temperature/timeout
# - 就先看 provider 專屬 OLLAMA_* / OPENAI_*
# - 若沒設，fallback 用 MODEL_*
# -------------------------
def _resolve_temperature(provider_key: str, passed: float | None) -> float:
    if passed is not None:
        return float(passed)

    # provider-specific first (if set)
    if os.getenv(provider_key) is not None:
        return _f(provider_key, _model_temperature_default())

    # fallback to MODEL_TEMPERATURE
    return _model_temperature_default()


def _resolve_timeout(provider_key: str, passed: int | None) -> int:
    if passed is not None:
        return int(passed)

    # provider-specific first (if set)
    if os.getenv(provider_key) is not None:
        return _i(provider_key, _model_timeout_default())

    # fallback to MODEL_TIMEOUT
    return _model_timeout_default()


def log_llm_config():
    """
    啟動時列印 LLM 配置摘要，方便診斷。
    """
    model_type = (os.getenv("MODEL_TYPE") or "OLLAMA").strip().upper()

    def _mask_key(key):
        if not key: return "MISSING"
        if len(key) < 8: return "SET (Too Short?)"
        return f"SET ({key[:4]}...{key[-4:]})"

    if model_type == "GOOGLE":
        return
    elif model_type == "OPENAI":
        m = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        k = os.getenv("OPENAI_API_KEY")
        fb = (os.getenv("OPENAI_RUNTIME_FALLBACK") or "").strip().upper()
        logger.info("[LLM CONFIG] OPENAI: model=%s, api_key=%s, runtime_fallback=%s", m, _mask_key(k), fb or "NONE")
        return

def _make_ollama(temperature: float | None, timeout: int | None, model_name: str | None = None):
    model = model_name or os.getenv("OLLAMA_MODEL", "mistral_small_3_1_2503:latest")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434")

    t = _resolve_temperature("OLLAMA_TEMPERATURE", temperature)
    to = _resolve_timeout("OLLAMA_TIMEOUT", timeout)

    host = _extract_host_from_base_url(base_url)
    if host:
        _append_no_proxy_host(host)

    _new_pkg = False
    try:
        from langchain_ollama import OllamaLLM
        _new_pkg = True

        def _build_ollama(m: str):
            kwargs = {"model": m, "base_url": base_url}
            sig = inspect.signature(OllamaLLM.__init__)
            if "temperature" in sig.parameters:
                kwargs["temperature"] = t
            if "timeout" in sig.parameters:
                kwargs["timeout"] = to
            return OllamaLLM(**kwargs)

    except ImportError:
        from langchain_community.llms import Ollama

        def _build_ollama(m: str):
            kwargs = {"model": m, "base_url": base_url}
            sig = inspect.signature(Ollama.__init__)
            if "temperature" in sig.parameters:
                kwargs["temperature"] = t
            if "timeout" in sig.parameters:
                kwargs["timeout"] = to
            return Ollama(**kwargs)

    llm = _build_ollama(model)

    class LoggedOllama:
        def __getattr__(self, name):
            return getattr(llm, name)

        def invoke(self, input, **kwargs):
            _log_llm_use("OLLAMA", model, temperature=t, timeout=to)
            try:
                return llm.invoke(input, **kwargs)
            except Exception as e:
                if not _should_try_ollama_fallback(e):
                    raise
                last_err = e
                for alt in _ollama_fallback_models(model):
                    try:
                        _log_llm_use("OLLAMA_FALLBACK", alt, temperature=t, timeout=to)
                        return _build_ollama(alt).invoke(input, **kwargs)
                    except Exception as e2:
                        last_err = e2
                        logger.warning("[LLM] OLLAMA fallback failed model=%s err=%r", alt, e2)
                raise last_err

        async def ainvoke(self, input, **kwargs):
            _log_llm_use("OLLAMA", model, temperature=t, timeout=to)
            try:
                return await llm.ainvoke(input, **kwargs)
            except Exception as e:
                if not _should_try_ollama_fallback(e):
                    raise
                last_err = e
                for alt in _ollama_fallback_models(model):
                    try:
                        _log_llm_use("OLLAMA_FALLBACK", alt, temperature=t, timeout=to)
                        return await _build_ollama(alt).ainvoke(input, **kwargs)
                    except Exception as e2:
                        last_err = e2
                        logger.warning("[LLM] OLLAMA fallback failed (async) model=%s err=%r", alt, e2)
                raise last_err

        def __repr__(self):
            backend_name = "OllamaLLM" if _new_pkg else "Ollama(community)"
            return f"{backend_name}(model={model})"

    return LoggedOllama()


def _make_openai(temperature: float | None, timeout: int | None, model: str | None = None, base_url: str | None = None):
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = base_url or os.getenv("OPENAI_BASE_URL")  # 👈 支援從 .env 載入通用 OPENAI_BASE_URL 變數

    if not api_key and not base_url:
        # Compatibility path for intranet LM_STUDIO deployments:
        # if caller accidentally routes into OpenAI factory while MODEL_TYPE=LM_STUDIO,
        # transparently use LM Studio endpoint instead of hard-failing on OPENAI_API_KEY.
        env_model_type = (os.getenv("MODEL_TYPE") or "").strip().upper()
        if env_model_type == "LM_STUDIO":
            base_url = os.getenv("LM_STUDIO_BASE_URL", "http://mpcai.mpc.mil.tw:1234/v1")
            model = model or os.getenv("LM_STUDIO_MODEL", "ministral-3-14b-instruct-2512")
        else:
            raise RuntimeError("OPENAI_API_KEY 未設定（OpenAI 不可用）。若要連線至本地內網相容 OpenAI 介面之大模型，請配置 OPENAI_BASE_URL 環境變數。")
    
    # 對於本地推理 (如 LM-Studio、Ollama/v1、內網 OpenAI 相容端點)，若無 Key 則使用佔位符
    if not api_key:
        api_key = "openai-compatible"

    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if _looks_non_chat_openai_model(model):
        fallback_chat_model = (os.getenv("OPENAI_CHAT_MODEL") or "gpt-4.1").strip()
        logger.warning("[LLM] OPENAI_MODEL=%s is non-chat; fallback to chat model=%s", model, fallback_chat_model)
        model = fallback_chat_model

    # ✅ 改：支援 MODEL_TEMPERATURE / MODEL_TIMEOUT fallback
    t = _resolve_temperature("OPENAI_TEMPERATURE", temperature)
    to = _resolve_timeout("OPENAI_TIMEOUT", timeout)

    llm = ChatOpenAI(
        base_url=base_url,
        model=model,
        temperature=t,
        timeout=to,
        api_key=api_key,
    )
    runtime_fallback = _resolve_openai_runtime_fallback()

    def _invoke_fallback(input, kwargs):
        if runtime_fallback == "GOOGLE":
            return _make_google(temperature=t, timeout=to).invoke(input, **kwargs)
        if runtime_fallback == "OLLAMA":
            return _make_ollama(temperature=t, timeout=to).invoke(input, **kwargs)
        if runtime_fallback == "LM_STUDIO":
            return _make_lm_studio(temperature=t, timeout=to).invoke(input, **kwargs)
        raise RuntimeError("no fallback configured")

    async def _ainvoke_fallback(input, kwargs):
        if runtime_fallback == "GOOGLE":
            return await _make_google(temperature=t, timeout=to).ainvoke(input, **kwargs)
        if runtime_fallback == "OLLAMA":
            return await _make_ollama(temperature=t, timeout=to).ainvoke(input, **kwargs)
        if runtime_fallback == "LM_STUDIO":
            return await _make_lm_studio(temperature=t, timeout=to).ainvoke(input, **kwargs)
        raise RuntimeError("no fallback configured")

    class LoggedOpenAI:
        def __getattr__(self, name):
            return getattr(llm, name)

        def invoke(self, input, **kwargs):
            _log_llm_use("OPENAI", model, temperature=t, timeout=to)
            try:
                return llm.invoke(input, **kwargs)
            except Exception as e:
                if runtime_fallback and _is_openai_quota_error(e):
                    logger.warning("[LLM] OPENAI quota exceeded; runtime fallback=%s", runtime_fallback)
                    return _invoke_fallback(input, kwargs)
                raise

        async def ainvoke(self, input, **kwargs):
            _log_llm_use("OPENAI", model, temperature=t, timeout=to)
            try:
                return await llm.ainvoke(input, **kwargs)
            except Exception as e:
                if runtime_fallback and _is_openai_quota_error(e):
                    logger.warning("[LLM] OPENAI quota exceeded (async); runtime fallback=%s", runtime_fallback)
                    return await _ainvoke_fallback(input, kwargs)
                raise

        def __repr__(self):
            return f"ChatOpenAI(model={model})"

    return LoggedOpenAI()


def _make_lm_studio(temperature: float | None, timeout: int | None):
    from langchain_openai import ChatOpenAI

    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://mpcai.mpc.mil.tw:1234/v1")
    model = os.getenv("LM_STUDIO_MODEL", "ministral-3-14b-instruct-2512")
    api_key = os.getenv("LM_STUDIO_API_KEY") or os.getenv("OPENAI_API_KEY") or "lm-studio"

    t = _resolve_temperature("LM_STUDIO_TEMPERATURE", temperature)
    to = _resolve_timeout("LM_STUDIO_TIMEOUT", timeout)

    host = _extract_host_from_base_url(base_url)
    if host:
        _append_no_proxy_host(host)

    llm = ChatOpenAI(
        base_url=base_url,
        model=model,
        temperature=t,
        timeout=to,
        api_key=api_key,
    )

    class LoggedLMStudio:
        def __getattr__(self, name):
            return getattr(llm, name)

        def invoke(self, input, **kwargs):
            _log_llm_use("LM_STUDIO", model, temperature=t, timeout=to)
            return llm.invoke(input, **kwargs)

        async def ainvoke(self, input, **kwargs):
            _log_llm_use("LM_STUDIO", model, temperature=t, timeout=to)
            return await llm.ainvoke(input, **kwargs)

        def __repr__(self):
            return f"LMStudioChatModel(model={model})"

    return LoggedLMStudio()


def _make_google(temperature: float | None, timeout: int | None):
    from langchain_google_genai import ChatGoogleGenerativeAI
    # Prefer google.genai enums to avoid deprecated google.generativeai warning.
    HarmCategory = None
    HarmBlockThreshold = None
    try:
        from google.genai import types as _genai_types  # type: ignore
        HarmCategory = _genai_types.HarmCategory
        HarmBlockThreshold = _genai_types.HarmBlockThreshold
    except Exception:
        try:
            from google.generativeai.types import HarmCategory as _HC, HarmBlockThreshold as _HBT  # type: ignore
            HarmCategory = _HC
            HarmBlockThreshold = _HBT
        except Exception:
            HarmCategory = None
            HarmBlockThreshold = None

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 未設定（Google Gemini 不可用）")

    model = os.getenv("GOOGLE_MODEL", "gemini-1.5-flash")

    t = _resolve_temperature("GOOGLE_TEMPERATURE", temperature)
    to = _resolve_timeout("GOOGLE_TIMEOUT", timeout)

    # ✅ 修正：關閉安全過濾與工具呼叫，避免解析公文時因敏感字眼或格式被 Google 阻擋
    safety_settings = None
    if HarmCategory and HarmBlockThreshold:
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

    kwargs = {
        "model": model,
        "temperature": t,
        "timeout": to,
        "google_api_key": api_key,
    }
    if safety_settings is not None:
        kwargs["safety_settings"] = safety_settings

    llm = ChatGoogleGenerativeAI(**kwargs)

    class LoggedGoogle:
        def __getattr__(self, name):
            return getattr(llm, name)

        def invoke(self, input, **kwargs):
            _log_llm_use("GOOGLE", model, temperature=t, timeout=to)
            return llm.invoke(input, **kwargs)

        async def ainvoke(self, input, **kwargs):
            _log_llm_use("GOOGLE", model, temperature=t, timeout=to)
            return await llm.ainvoke(input, **kwargs)

        def __repr__(self):
            return f"ChatGoogleGenerativeAI(model={model})"

    return LoggedGoogle()


def _log_llm_use(tag: str, model: str, *, temperature: float | None = None, timeout: int | None = None):
    extra = []
    if temperature is not None:
        extra.append(f"temp={temperature}")
    if timeout is not None:
        extra.append(f"timeout={timeout}")
    suffix = (" " + " ".join(extra)) if extra else ""
    logger.info("[LLM] backend=%s model=%s%s", tag, model, suffix)


def _get_embedding_strategy_registry():
    global _EMBEDDING_STRATEGY_REGISTRY
    if _EMBEDDING_STRATEGY_REGISTRY is None:
        deps = EmbeddingStrategyDeps(
            resolve_provider_fallback=_resolve_provider_fallback,
            logger=logger,
        )
        _EMBEDDING_STRATEGY_REGISTRY = build_embedding_registry(deps)
    return _EMBEDDING_STRATEGY_REGISTRY


def get_embedding_model(model_type: str | None = None):
    """Create embedding model instance by MODEL_TYPE."""
    provider = _normalize_provider_for_env((model_type or os.getenv("MODEL_TYPE") or "OLLAMA"))
    strategy = _get_embedding_strategy_registry().get(provider)
    if not strategy:
        raise ValueError(f"Unknown MODEL_TYPE={provider}. Use GOOGLE/OLLAMA/OPENAI.")
    return strategy.build()

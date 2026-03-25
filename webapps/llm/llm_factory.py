# webapps/llm/llm_factory.py
import os
import inspect
import json
import logging
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_ENV_ALIASES = {
    "DEV": "DEV_EXT",
    "EXT": "DEV_EXT",
    "INT": "DEV_INT",
    "PROD": "PROD_EXT",
}


def _normalize_env_name(raw: str) -> str:
    return _ENV_ALIASES.get((raw or "").strip().upper(), (raw or "").strip().upper())


def _active_env_name() -> str:
    return _normalize_env_name(os.getenv("ENV") or "DEV_EXT")


def _env_keys(name: str) -> list[str]:
    env_name = _active_env_name()
    keys = [f"{name}__{env_name}"]
    keys.append(name)
    return keys


def _env_get(name: str, default: str | None = None) -> str | None:
    for key in _env_keys(name):
        if key in os.environ:
            return os.environ.get(key)
    return default


def _env_has(name: str) -> bool:
    for key in _env_keys(name):
        if key in os.environ:
            return True
    return False


def _f(name: str, default: float) -> float:
    try:
        return float(_env_get(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(_env_get(name, str(default)))
    except Exception:
        return default


def _b(name: str, default: bool = False) -> bool:
    """
    env bool: 1/0, true/false, yes/no, on/off
    """
    v = (_env_get(name, "") or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


# -------------------------
# ✅ 通用（你 .env 的 MODEL_*）
# -------------------------
def _model_temperature_default() -> float:
    return _f("MODEL_TEMPERATURE", 0.2)


def _model_timeout_default() -> int:
    return _i("MODEL_TIMEOUT", 120)


def _resolved_model_priority() -> list[str]:
    """
    Resolve AUTO backend priority by ENV first, then MODEL_PRIORITY, then legacy fallback.
    - ENV=DEV_INT/PROD_INT: force OLLAMA only (intranet policy)
    - ENV=DEV_EXT/PROD_EXT: default GOOGLE -> OPENAI -> OLLAMA
    - Legacy aliases: EXT/DEV->DEV_EXT, INT->DEV_INT, PROD->PROD_EXT.
    """
    env_name = _active_env_name()
    raw_prio = (_env_get("MODEL_PRIORITY", "") or "").strip()

    if env_name in ("DEV_INT", "PROD_INT"):
        return ["OLLAMA"]

    if env_name in ("DEV_EXT", "PROD_EXT"):
        if raw_prio:
            return [x.strip().upper() for x in raw_prio.split(",") if x.strip()]
        return ["GOOGLE", "OPENAI", "OLLAMA"]

    if raw_prio:
        return [x.strip().upper() for x in raw_prio.split(",") if x.strip()]

    use_ollama_first = _b("USE_OLLAMA_FIRST", True)
    return ["OLLAMA", "OPENAI"] if use_ollama_first else ["OPENAI", "OLLAMA"]


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
    raw = (_env_get("OLLAMA_FALLBACK_MODELS", "gemma3:4b,qwen3:8b") or "gemma3:4b,qwen3:8b").strip()
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


def _ollama_list_models(base_url: str, timeout_sec: int = 5) -> list[str]:
    """
    Probe Ollama /api/tags and return installed model names.
    Returns [] when probe fails.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return []

    url = f"{base}/api/tags"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=max(1, int(timeout_sec))) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as e:
        logger.info("[LLM] OLLAMA tags probe failed: %r", e)
        return []

    models = payload.get("models") or []
    out: list[str] = []
    seen = set()
    for item in models:
        if isinstance(item, dict):
            name = (item.get("name") or item.get("model") or "").strip()
        else:
            name = str(item).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _merge_ollama_fallback_models(
    primary_model: str,
    *,
    base_url: str,
    timeout_sec: int,
) -> list[str]:
    merged: list[str] = []
    seen = set()

    for model_name in _ollama_fallback_models(primary_model) + _ollama_list_models(base_url, timeout_sec):
        m = (model_name or "").strip()
        if not m:
            continue
        if m.lower() == primary_model.lower():
            continue
        key = m.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(m)
    return merged


def _should_try_ollama_fallback(err: Exception) -> bool:
    s = str(err or "").lower()
    return (
        "runner process has terminated" in s
        or "exit status" in s
        or "responseerror" in s
    )


def get_chat_model(temperature: float | None = None, timeout: int | None = None):
    model_type = (_env_get("MODEL_TYPE", "AUTO") or "AUTO").strip().upper()

    if model_type == "GOOGLE":
        return _make_google(temperature=temperature, timeout=timeout)

    if model_type == "OLLAMA":
        return _make_ollama(temperature=temperature, timeout=timeout)

    if model_type == "OPENAI":
        return _make_openai(temperature=temperature, timeout=timeout)

    if model_type == "AUTO":
        return _make_auto(temperature=temperature, timeout=timeout)

    raise ValueError(f"Unknown MODEL_TYPE={model_type}. Use AUTO/GOOGLE/OLLAMA/OPENAI.")


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
    if _env_has(provider_key):
        return _f(provider_key, _model_temperature_default())

    # fallback to MODEL_TEMPERATURE
    return _model_temperature_default()


def _resolve_timeout(provider_key: str, passed: int | None) -> int:
    if passed is not None:
        return int(passed)

    # provider-specific first (if set)
    if _env_has(provider_key):
        return _i(provider_key, _model_timeout_default())

    # fallback to MODEL_TIMEOUT
    return _model_timeout_default()


def log_llm_config():
    """
    啟動時列印 LLM 配置摘要，方便診斷。
    """
    model_type = (_env_get("MODEL_TYPE", "AUTO") or "AUTO").strip().upper()
    logger.info("[LLM CONFIG] MODEL_TYPE=%s", model_type)

    def _mask_key(key):
        if not key: return "MISSING"
        if len(key) < 8: return "SET (Too Short?)"
        return f"SET ({key[:4]}...{key[-4:]})"

    if model_type == "GOOGLE":
        m = _env_get("GOOGLE_MODEL", "gemini-1.5-flash")
        k = _env_get("GOOGLE_API_KEY")
        logger.info("[LLM CONFIG] GOOGLE: model=%s, api_key=%s", m, _mask_key(k))
    elif model_type == "OPENAI":
        m = _env_get("OPENAI_MODEL", "gpt-4o-mini")
        k = _env_get("OPENAI_API_KEY")
        logger.info("[LLM CONFIG] OPENAI: model=%s, api_key=%s", m, _mask_key(k))
    elif model_type == "OLLAMA":
        m = _env_get("OLLAMA_MODEL", "mistral_small_3_1_2503:latest")
        u = _env_get("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434")
        logger.info("[LLM CONFIG] OLLAMA: model=%s, base_url=%s", m, u)
    elif model_type == "AUTO":
        prio = _resolved_model_priority()
        logger.info("[LLM CONFIG] AUTO Priority: %s", " -> ".join(prio))
        
        # 檢查各後端狀態
        status_line = []
        for p in prio:
            if p == "GOOGLE":
                status_line.append(f"GOOGLE:{_mask_key(_env_get('GOOGLE_API_KEY'))}")
            elif p == "OPENAI":
                status_line.append(f"OPENAI:{_mask_key(_env_get('OPENAI_API_KEY'))}")
            elif p == "OLLAMA":
                status_line.append(f"OLLAMA:Ready")
        logger.info("[LLM CONFIG] Status: %s", " | ".join(status_line))
    logger.info("%s", "-" * 40)


def _make_ollama(temperature: float | None, timeout: int | None):
    # Prefer new package; fallback to deprecated path for compatibility.
    _new_pkg = True
    try:
        from langchain_ollama import OllamaLLM  # type: ignore
    except Exception:
        from langchain_community.llms.ollama import Ollama as OllamaLLM  # type: ignore
        _new_pkg = False

    base_url = _env_get("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434")
    model = _env_get("OLLAMA_MODEL", "mistral_small_3_1_2503:latest")

    # ✅ 改：支援 MODEL_TEMPERATURE / MODEL_TIMEOUT fallback
    t = _resolve_temperature("OLLAMA_TEMPERATURE", temperature)
    to = _resolve_timeout("OLLAMA_TIMEOUT", timeout)

    # ✅ 自動把 base_url 的 host 加進 NO_PROXY/no_proxy
    host = _extract_host_from_base_url(base_url)
    if host:
        _append_no_proxy_host(host)

    # ✅ timeout：不同版本參數名稱不一樣，安全嘗試塞入（不支援就略過）
    ollama_kwargs = {
        "base_url": base_url,
        "temperature": t,
    }
    try:
        sig = inspect.signature(OllamaLLM.__init__)
        params = set(sig.parameters.keys())
        if "request_timeout" in params:
            ollama_kwargs["request_timeout"] = to
        elif "timeout" in params:
            ollama_kwargs["timeout"] = to
    except Exception:
        pass

    def _build_ollama(model_name: str):
        kwargs = dict(ollama_kwargs)
        kwargs["model"] = model_name
        return OllamaLLM(**kwargs)

    probe_timeout = max(3, min(to, 8))
    installed_models = _ollama_list_models(base_url, timeout_sec=probe_timeout)

    active_model = model
    if installed_models and all(m.lower() != model.lower() for m in installed_models):
        active_model = installed_models[0]
        logger.warning(
            "[LLM] OLLAMA model '%s' not found in /api/tags. Auto switch to '%s'.",
            model,
            active_model,
        )

    llm = _build_ollama(active_model)

    class LoggedOllama:
        def invoke(self, input, **kwargs):
            _log_llm_use("OLLAMA", active_model, temperature=t, timeout=to)
            try:
                return llm.invoke(input, **kwargs)
            except Exception as e:
                if not _should_try_ollama_fallback(e):
                    raise
                last_err = e
                for alt in _merge_ollama_fallback_models(
                    active_model,
                    base_url=base_url,
                    timeout_sec=probe_timeout,
                ):
                    try:
                        _log_llm_use("OLLAMA_FALLBACK", alt, temperature=t, timeout=to)
                        return _build_ollama(alt).invoke(input, **kwargs)
                    except Exception as e2:
                        last_err = e2
                        logger.warning("[LLM] OLLAMA fallback failed model=%s err=%r", alt, e2)
                raise last_err

        async def ainvoke(self, input, **kwargs):
            _log_llm_use("OLLAMA", active_model, temperature=t, timeout=to)
            try:
                return await llm.ainvoke(input, **kwargs)
            except Exception as e:
                if not _should_try_ollama_fallback(e):
                    raise
                last_err = e
                for alt in _merge_ollama_fallback_models(
                    active_model,
                    base_url=base_url,
                    timeout_sec=probe_timeout,
                ):
                    try:
                        _log_llm_use("OLLAMA_FALLBACK", alt, temperature=t, timeout=to)
                        return await _build_ollama(alt).ainvoke(input, **kwargs)
                    except Exception as e2:
                        last_err = e2
                        logger.warning("[LLM] OLLAMA fallback failed (async) model=%s err=%r", alt, e2)
                raise last_err

        def __repr__(self):
            backend_name = "OllamaLLM" if _new_pkg else "Ollama(community)"
            return f"{backend_name}(model={active_model})"

    return LoggedOllama()


def _make_openai(temperature: float | None, timeout: int | None):
    from langchain_openai import ChatOpenAI

    api_key = _env_get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 未設定（OpenAI 不可用）")

    model = _env_get("OPENAI_MODEL", "gpt-4o-mini")

    # ✅ 改：支援 MODEL_TEMPERATURE / MODEL_TIMEOUT fallback
    t = _resolve_temperature("OPENAI_TEMPERATURE", temperature)
    to = _resolve_timeout("OPENAI_TIMEOUT", timeout)

    llm = ChatOpenAI(
        model=model,
        temperature=t,
        timeout=to,
        api_key=api_key,
    )

    class LoggedOpenAI:
        def invoke(self, input, **kwargs):
            _log_llm_use("OPENAI", model, temperature=t, timeout=to)
            return llm.invoke(input, **kwargs)

        async def ainvoke(self, input, **kwargs):
            _log_llm_use("OPENAI", model, temperature=t, timeout=to)
            return await llm.ainvoke(input, **kwargs)

        def __repr__(self):
            return f"ChatOpenAI(model={model})"

    return LoggedOpenAI()


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

    api_key = _env_get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY 未設定（Google Gemini 不可用）")

    model = _env_get("GOOGLE_MODEL", "gemini-1.5-flash")

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


# -------------------------
# ✅ AUTO：尊重 USE_OLLAMA_FIRST
# - USE_OLLAMA_FIRST=1 => 先 Ollama 後 OpenAI
# - USE_OLLAMA_FIRST=0 => 先 OpenAI 後 Ollama
# -------------------------
def _make_auto(temperature: float | None, timeout: int | None):
    # Resolve priority with ENV policy + MODEL_PRIORITY + legacy fallback.
    priority_list = _resolved_model_priority()

    # 預先初始化所有在 list 中的後端
    backends = {}
    init_errors = {}

    for name in priority_list:
        try:
            if name == "GOOGLE":
                backends[name] = _make_google(temperature, timeout)
            elif name == "OPENAI":
                backends[name] = _make_openai(temperature, timeout)
            elif name == "OLLAMA":
                backends[name] = _make_ollama(temperature, timeout)
        except Exception as e:
            init_errors[name] = e

    class AutoFallbackChatModel:
        def invoke(self, input, config=None, **kwargs):
            last_err = None
            for name in priority_list:
                llm = backends.get(name)
                if not llm:
                    last_err = init_errors.get(name) or RuntimeError(f"{name} backend not inited")
                    continue
                
                try:
                    _log_llm_use(f"AUTO->({name})", _env_get(f"{name}_MODEL", ""))
                    return llm.invoke(input, config=config, **kwargs)
                except Exception as e:
                    last_err = e
                    logger.warning("[LLM] AUTO fallback: %s failed, error=%r", name, e)
            
            raise RuntimeError(f"AUTO 模式所有後端皆失敗。最後錯誤: {last_err!r}")

        async def ainvoke(self, input, config=None, **kwargs):
            last_err = None
            for name in priority_list:
                llm = backends.get(name)
                if not llm:
                    last_err = init_errors.get(name) or RuntimeError(f"{name} backend not inited")
                    continue
                
                try:
                    _log_llm_use(f"AUTO->({name})", _env_get(f"{name}_MODEL", ""))
                    return await llm.ainvoke(input, config=config, **kwargs)
                except Exception as e:
                    last_err = e
                    logger.warning("[LLM] AUTO fallback (async): %s failed, error=%r", name, e)
            
            raise RuntimeError(f"AUTO 模式所有後端皆失敗。最後錯誤: {last_err!r}")

        def __call__(self, *args, **kwargs):
            return self.invoke(*args, **kwargs)

        def __repr__(self):
            return f"AutoFallbackChatModel(priority={priority_list}, active_keys={list(backends.keys())})"

    return AutoFallbackChatModel()

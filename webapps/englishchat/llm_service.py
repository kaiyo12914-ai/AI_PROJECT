from __future__ import annotations

import ast
import json
import logging
import time
from typing import Any, Dict, List

from webapps.llm.llm_factory import get_chat_model

logger = logging.getLogger(__name__)


class EnglishChatLLMError(Exception):
    pass


def safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def coerce_llm_text(value: Any) -> str:
    if value is None:
        return ""

    content = value.content if hasattr(value, "content") else value

    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, list):
                    content = parsed
            except Exception:
                pass
        elif stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, dict):
                    content = parsed
            except Exception:
                pass

    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if "text" in part:
                    parts.append(str(part.get("text") or ""))
                elif "content" in part:
                    parts.append(str(part.get("content") or ""))
                else:
                    parts.append(str(part))
            else:
                parts.append(str(part))
        return "".join(parts).strip()

    if isinstance(content, dict):
        if "content" in content:
            return str(content.get("content") or "").strip()
        if "text" in content:
            return str(content.get("text") or "").strip()

    return safe_text(content)


def strip_json_fence(text: str) -> str:
    stripped = safe_text(text)
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def extract_json_object(raw: str) -> Dict[str, Any]:
    text = strip_json_fence(coerce_llm_text(raw))
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def extract_json_array(raw: str) -> List[Dict[str, Any]]:
    text = strip_json_fence(coerce_llm_text(raw))
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        pass
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def invoke_json(
    prompt: str,
    *,
    purpose: str,
    temperature: float = 0.6,
    timeout: int = 90,
    max_retries: int = 2,
    retry_delay: float = 1.5,
) -> Dict[str, Any]:
    llm = get_chat_model(temperature=temperature, timeout=timeout)
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            started = time.time()
            out = llm.invoke(prompt)
            parsed = extract_json_object(out)
            if parsed:
                logger.info(
                    "englishchat llm success purpose=%s attempt=%s duration_ms=%s",
                    purpose,
                    attempt,
                    round((time.time() - started) * 1000),
                )
                return parsed
            last_error = EnglishChatLLMError("empty_or_invalid_json")
            logger.warning("englishchat llm parse failure purpose=%s attempt=%s", purpose, attempt)
        except Exception as exc:
            last_error = exc
            logger.warning("englishchat llm request failure purpose=%s attempt=%s error=%s", purpose, attempt, exc)
        if attempt <= max_retries:
            time.sleep(retry_delay * attempt)
    raise EnglishChatLLMError(f"{purpose} failed after retries: {last_error}")


def invoke_json_array(
    prompt: str,
    *,
    purpose: str,
    temperature: float = 0.6,
    timeout: int = 90,
    max_retries: int = 2,
    retry_delay: float = 1.5,
) -> List[Dict[str, Any]]:
    llm = get_chat_model(temperature=temperature, timeout=timeout)
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            started = time.time()
            out = llm.invoke(prompt)
            parsed = extract_json_array(out)
            if parsed:
                logger.info(
                    "englishchat llm array success purpose=%s attempt=%s duration_ms=%s",
                    purpose,
                    attempt,
                    round((time.time() - started) * 1000),
                )
                return parsed
            last_error = EnglishChatLLMError("empty_or_invalid_json_array")
            logger.warning("englishchat llm array parse failure purpose=%s attempt=%s", purpose, attempt)
        except Exception as exc:
            last_error = exc
            logger.warning("englishchat llm array request failure purpose=%s attempt=%s error=%s", purpose, attempt, exc)
        if attempt <= max_retries:
            time.sleep(retry_delay * attempt)
    raise EnglishChatLLMError(f"{purpose} failed after retries: {last_error}")

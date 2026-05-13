from __future__ import annotations

import ast
import json
import logging
import os
import time
from typing import Any, Dict, List

from webapps.llm.llm_factory import get_chat_model

logger = logging.getLogger(__name__)
RAW_LOG_LIMIT = 1200


class EnglishChatLLMError(Exception):
    pass


def is_non_retryable_llm_error(exc: Exception) -> bool:
    text = safe_text(exc).lower()
    return any(
        token in text
        for token in [
            "insufficient_quota",
            "you exceeded your current quota",
            "invalid_api_key",
            "incorrect api key",
            "authenticationerror",
            "permission denied",
        ]
    )


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


def summarize_for_log(value: Any, limit: int = RAW_LOG_LIMIT) -> str:
    text = safe_text(value)
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def log_parse_diagnostics(kind: str, purpose: str, attempt: int, out: Any) -> None:
    raw_content = out.content if hasattr(out, "content") else out
    coerced_text = coerce_llm_text(out)
    logger.debug(
        (
            "englishchat llm %s parse diagnostics purpose=%s attempt=%s "
            "response_type=%s content_type=%s raw_excerpt=%r normalized_excerpt=%r"
        ),
        kind,
        purpose,
        attempt,
        type(out).__name__,
        type(raw_content).__name__,
        summarize_for_log(raw_content),
        summarize_for_log(coerced_text),
    )


def build_array_repair_prompt(raw_text: str) -> str:
    excerpt = summarize_for_log(raw_text, limit=4000)
    return f"""
你是一個 JSON 修復器。

請把下面內容修正成「合法的 JSON array」後直接輸出。
限制：
1. 只能輸出 JSON array。
2. 第一個字必須是 `[`，最後一個字必須是 `]`。
3. 不要輸出 markdown、```、說明文字、註解、前言或結語。
4. 若原內容看起來是題目清單，請盡量保留原意，只修正 JSON 格式。
5. 若欄位缺值，請保留 key，並用 `""` 或 `[]` 補空值。
6. 不要新增原本不存在的外層包裝物件。

待修復內容：
{excerpt}
""".strip()


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
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            return [parsed]
        return []
    except Exception:
        pass
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
        except Exception:
            pass
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        try:
            parsed = json.loads(snippet)
            return [parsed] if isinstance(parsed, dict) else []
        except Exception:
            try:
                parsed = ast.literal_eval(snippet)
                return [parsed] if isinstance(parsed, dict) else []
            except Exception:
                return []
    return []


def _openai_array_schema() -> Dict[str, Any]:
    return {
        "name": "englishchat_question_array",
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "prompt_text": {"type": "string"},
                    "choices_json": {"type": "array", "items": {"type": "string"}},
                    "words_json": {"type": "array"},
                    "answer_text": {"type": "string"},
                    "explanation_zh": {"type": "string"},
                    "pattern_text": {"type": "string"},
                    "zh_prompt": {"type": "string"},
                    "sample_answer": {"type": "string"},
                    "patterns_json": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["prompt_text", "choices_json", "answer_text"],
            },
        },
    }


def try_invoke_structured_json_array(llm: Any, prompt: str) -> List[Dict[str, Any]]:
    # Default OFF: some environments return 400 for structured output attempts.
    # Enable only when explicitly requested.
    if (os.getenv("ENABLE_OPENAI_STRUCTURED_ARRAY") or "").strip() != "1":
        return []
    model_type = (os.getenv("MODEL_TYPE") or "").strip().upper()
    if model_type != "OPENAI":
        return []
    if not hasattr(llm, "with_structured_output"):
        return []
    try:
        structured_llm = llm.with_structured_output(_openai_array_schema(), method="json_schema")
        out = structured_llm.invoke(prompt)
        return extract_json_array(out)
    except Exception as exc:
        logger.debug("englishchat structured output failed error=%s", exc)
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
            logger.info("englishchat llm parse failure purpose=%s attempt=%s", purpose, attempt)
            log_parse_diagnostics("object", purpose, attempt, out)
        except Exception as exc:
            last_error = exc
            logger.warning("englishchat llm request failure purpose=%s attempt=%s error=%s", purpose, attempt, exc)
            if is_non_retryable_llm_error(exc):
                raise EnglishChatLLMError(f"{purpose} non_retryable_error: {exc}") from exc
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
            out: Any = None
            parsed = try_invoke_structured_json_array(llm, prompt)
            if not parsed:
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
            logger.info("englishchat llm array parse failure purpose=%s attempt=%s", purpose, attempt)
            if out is not None:
                log_parse_diagnostics("array", purpose, attempt, out)
                repaired_raw = coerce_llm_text(out)
            else:
                repaired_raw = ""
            if repaired_raw:
                try:
                    repair_started = time.time()
                    repair_prompt = build_array_repair_prompt(repaired_raw)
                    repair_out = llm.invoke(repair_prompt)
                    repaired = extract_json_array(repair_out)
                    if repaired:
                        logger.info(
                            "englishchat llm array repair success purpose=%s attempt=%s duration_ms=%s",
                            purpose,
                            attempt,
                            round((time.time() - repair_started) * 1000),
                        )
                        return repaired
                    logger.info("englishchat llm array repair parse failure purpose=%s attempt=%s", purpose, attempt)
                    log_parse_diagnostics("array_repair", purpose, attempt, repair_out)
                except Exception as repair_exc:
                    logger.warning(
                        "englishchat llm array repair request failure purpose=%s attempt=%s error=%s",
                        purpose,
                        attempt,
                        repair_exc,
                    )
        except Exception as exc:
            last_error = exc
            logger.warning("englishchat llm array request failure purpose=%s attempt=%s error=%s", purpose, attempt, exc)
            if is_non_retryable_llm_error(exc):
                raise EnglishChatLLMError(f"{purpose} non_retryable_error: {exc}") from exc
        if attempt <= max_retries:
            time.sleep(retry_delay * attempt)
    raise EnglishChatLLMError(f"{purpose} failed after retries: {last_error}")

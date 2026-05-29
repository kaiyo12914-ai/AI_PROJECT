from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List

from webapps.llm.llm_factory import get_chat_model

from .repository import ChatbotUIRepository

SYSTEM_PROMPT = """You are a helpful AI assistant inside an internal enterprise portal.
Reply clearly and directly.
Use Traditional Chinese if the user writes in Chinese, otherwise reply in the user's language.
If the user asks for code, provide practical code and short explanation.
Do not claim capabilities you do not have.
"""
DEFAULT_TEMPERATURE = 0.3
DEFAULT_TIMEOUT_SEC = 120
MAX_SYSTEM_PROMPT_CHARS = 1500
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_ATTACHMENT_TEXT_CHARS = 12000
MAX_ATTACHMENT_PROMPT_CHARS = 500
MAX_ATTACHMENT_TOTAL_PROMPT_CHARS = 1000
MAX_PROMPT_CHARS = 10000
MAX_HISTORY_ITEMS = 6
ATTACHMENT_PROMPT_LIMIT = 2
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".ini", ".cfg", ".py", ".js", ".ts", ".html", ".css", ".pdf", ".docx"
}


def safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def extract_message_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, dict):
                text = safe_text(item.get("text"))
                if text:
                    parts.append(text)
            else:
                text = safe_text(item)
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return safe_text(value)


def infer_title(user_text: str) -> str:
    cleaned = " ".join(safe_text(user_text).split())
    if not cleaned:
        return "New Chat"
    return cleaned[:36]


def resolve_user_id(request) -> str:
    return (
        safe_text(getattr(request, "login_user", "")) or
        safe_text(getattr(getattr(request, "user", None), "username", "")) or
        "anonymous"
    )


def normalize_temperature(value: Any, default: float = DEFAULT_TEMPERATURE) -> float:
    try:
        out = float(value)
    except Exception:
        out = default
    if out < 0:
        return 0.0
    if out > 2:
        return 2.0
    return out


def normalize_timeout_sec(value: Any, default: int = DEFAULT_TIMEOUT_SEC) -> int:
    try:
        out = int(value)
    except Exception:
        out = default
    if out < 10:
        return 10
    if out > 600:
        return 600
    return out


def normalize_system_prompt(value: Any) -> str:
    text = str(value) if value is not None else ""
    text = text.strip()
    if len(text) > MAX_SYSTEM_PROMPT_CHARS:
        text = text[:MAX_SYSTEM_PROMPT_CHARS]
    return text


def format_prompt_history_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(item.get("id") or 0),
        "prompt_text": normalize_system_prompt(item.get("prompt_text")),
        "created_at": safe_text(item.get("created_at")),
    }


def resolve_system_prompt(value: Any) -> str:
    custom = normalize_system_prompt(value)
    return custom or SYSTEM_PROMPT.strip()


def history_to_prompt(
    messages: List[Dict[str, Any]],
    latest_user_text: str,
    system_prompt: str,
    attachment_context: str = "",
    max_prompt_chars: int = MAX_PROMPT_CHARS,
    max_history_items: int = MAX_HISTORY_ITEMS,
) -> str:
    system_text = resolve_system_prompt(system_prompt)
    latest_user = safe_text(latest_user_text)
    lines: List[str] = [system_text, "", "Conversation history:"]
    if attachment_context:
        lines.extend(["", "Reference attachments:", safe_text(attachment_context), ""])

    history_lines: List[str] = []
    max_history = max(1, int(max_history_items or 1))
    for item in messages[-max_history:]:
        if not isinstance(item, dict):
            continue
        role = safe_text(item.get("role")).lower()
        content = safe_text(item.get("content"))
        if not content:
            continue
        speaker = "User" if role == "user" else "Assistant"
        history_lines.append(f"{speaker}: {content}")

    tail_lines = [f"User: {latest_user}", "Assistant:"]
    fixed_prefix = "\n".join(lines)
    fixed_tail = "\n".join(tail_lines)
    budget = max(1000, int(max_prompt_chars or MAX_PROMPT_CHARS))
    remaining = budget - len(fixed_prefix) - len(fixed_tail) - 16

    selected_reversed: List[str] = []
    for row in reversed(history_lines):
        clipped = row[:1200]
        need = len(clipped) + 1
        if remaining - need < 0:
            break
        selected_reversed.append(clipped)
        remaining -= need
    selected_history = list(reversed(selected_reversed))

    lines.extend(selected_history)
    lines.extend(tail_lines)
    return "\n".join(lines)


def is_context_exceeded_error(exc: Exception) -> bool:
    text = safe_text(exc).lower()
    if not text:
        return False
    patterns = [
        "context size has been exceeded",
        "maximum context length",
        "context_length_exceeded",
        "prompt is too long",
        "too many tokens",
    ]
    return any(p in text for p in patterns)


def resolve_model_name(model_type: str) -> str:
    mtype = safe_text(model_type).upper()
    if mtype == "GOOGLE":
        return safe_text(os.getenv("GOOGLE_MODEL")) or "gemini-1.5-flash"
    if mtype == "OPENAI":
        return safe_text(os.getenv("OPENAI_MODEL")) or "gpt-4o-mini"
    if mtype == "LM_STUDIO":
        return safe_text(os.getenv("LM_STUDIO_MODEL")) or "ministral-3-14b-instruct-2512"
    if mtype == "OLLAMA":
        return safe_text(os.getenv("OLLAMA_MODEL")) or "mistral_small_3_1_2503:latest"
    return ""


def _is_int_env() -> bool:
    return safe_text(os.getenv("ENV")).upper() == "INT"


def allowed_model_types() -> set[str]:
    if _is_int_env():
        return {"OLLAMA", "LM_STUDIO"}
    return {"GOOGLE", "OPENAI", "OLLAMA", "LM_STUDIO"}


def normalize_model_type(value: Any, default: str = "OLLAMA") -> str:
    requested = safe_text(value).upper()
    allowed = allowed_model_types()
    if requested in allowed:
        return requested
    if default in allowed:
        return default
    return "OLLAMA" if "OLLAMA" in allowed else "LM_STUDIO"


def normalize_model_name(model_type: str, model_name: Any) -> str:
    name = safe_text(model_name)
    return name or resolve_model_name(model_type)


def normalize_filename(value: Any) -> str:
    name = safe_text(value).replace("\\", "/").split("/")[-1]
    return name[:200]


def normalize_attachment_text(value: Any) -> str:
    text = safe_text(value)
    if not text:
        return ""
    if len(text) > MAX_ATTACHMENT_TEXT_CHARS:
        return text[:MAX_ATTACHMENT_TEXT_CHARS]
    return text


def _attachment_count_from_context(attachment_context: str) -> int:
    text = safe_text(attachment_context)
    if not text:
        return 0
    count = 0
    for line in text.splitlines():
        if line.startswith("- "):
            count += 1
    return count


def _normalize_citations(citations: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not isinstance(citations, list):
        return rows
    for item in citations:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "ref": safe_text(item.get("ref")) or "",
                "source_title": safe_text(item.get("source_title")) or "",
                "source_url": safe_text(item.get("source_url")) or "",
                "confidence": float(item.get("confidence") or 0),
                "excerpt": safe_text(item.get("excerpt"))[:240],
            }
        )
    return rows


class ChatbotUIService:
    def __init__(self, repository: ChatbotUIRepository | None = None) -> None:
        self.repository = repository or ChatbotUIRepository()

    def ensure_schema(self) -> None:
        self.repository.ensure_schema()

    def list_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        self.ensure_schema()
        rows = self.repository.list_conversations(user_id)
        out: List[Dict[str, Any]] = []
        for row in rows:
            model_type = normalize_model_type(safe_text(row.get("model_type")) or "OLLAMA", default="OLLAMA")
            out.append({
                "id": safe_text(row.get("id")),
                "title": safe_text(row.get("title")) or "New Chat",
                "model_type": model_type,
                "model_name": safe_text(row.get("model_name")) or "",
                "temperature": normalize_temperature(row.get("temperature")),
                "timeout_sec": normalize_timeout_sec(row.get("timeout_sec")),
                "system_prompt": normalize_system_prompt(row.get("system_prompt")),
                "chat_mode": safe_text(row.get("chat_mode")) or "GENERAL",
                "rag_source": safe_text(row.get("rag_source")) or "",
                "updated_at": safe_text(row.get("updated_at")),
                "preview": safe_text(row.get("last_message_preview"))[:80],
                "message_count": int(row.get("message_count") or 0),
            })
        return out

    def create_conversation(self, user_id: str, title: str = "New Chat", model_type: str = "OLLAMA") -> Dict[str, Any]:
        self.ensure_schema()
        profile = self.repository.get_user_profile(user_id) or {}
        profile_model_type = safe_text(profile.get("model_type")).upper() if profile else ""
        chosen_model_type = normalize_model_type(model_type or profile_model_type or "OLLAMA", default="OLLAMA")
        conversation_id = str(uuid.uuid4())
        self.repository.create_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            title=safe_text(title) or "New Chat",
            model_type=chosen_model_type,
            temperature=normalize_temperature(profile.get("temperature"), DEFAULT_TEMPERATURE),
            timeout_sec=normalize_timeout_sec(profile.get("timeout_sec"), DEFAULT_TIMEOUT_SEC),
            system_prompt=normalize_system_prompt(profile.get("system_prompt")),
            chat_mode=safe_text(profile.get("chat_mode")) or "GENERAL",
            rag_source=safe_text(profile.get("rag_source")) or "",
            model_name=safe_text(profile.get("model_name")) or resolve_model_name(chosen_model_type),
        )
        return self.get_conversation_detail(user_id, conversation_id)

    def _conversation_config(self, conversation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "temperature": normalize_temperature(conversation.get("temperature")),
            "timeout_sec": normalize_timeout_sec(conversation.get("timeout_sec")),
            "system_prompt": normalize_system_prompt(conversation.get("system_prompt")),
            "chat_mode": safe_text(conversation.get("chat_mode")) or "GENERAL",
            "rag_source": safe_text(conversation.get("rag_source")) or "",
        }

    def get_conversation_detail(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}
        profile = self.repository.get_user_profile(user_id) or {}
        config = self._conversation_config(conversation)
        config_source = "conversation_override"
        if profile:
            same = (
                safe_text(conversation.get("model_type")) == safe_text(profile.get("model_type")) and
                safe_text(conversation.get("model_name")) == safe_text(profile.get("model_name")) and
                normalize_temperature(conversation.get("temperature")) == normalize_temperature(profile.get("temperature")) and
                normalize_timeout_sec(conversation.get("timeout_sec")) == normalize_timeout_sec(profile.get("timeout_sec")) and
                normalize_system_prompt(conversation.get("system_prompt")) == normalize_system_prompt(profile.get("system_prompt")) and
                (safe_text(conversation.get("chat_mode")) or "GENERAL") == (safe_text(profile.get("chat_mode")) or "GENERAL") and
                safe_text(conversation.get("rag_source")) == safe_text(profile.get("rag_source"))
            )
            if same:
                config_source = "profile"
        return {
            "id": safe_text(conversation.get("id")),
            "title": safe_text(conversation.get("title")) or "New Chat",
            "model_type": normalize_model_type(safe_text(conversation.get("model_type")) or "OLLAMA", default="OLLAMA"),
            "model_name": safe_text(conversation.get("model_name")) or "",
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "system_prompt": config["system_prompt"],
            "chat_mode": config["chat_mode"],
            "rag_source": config["rag_source"],
            "config_source": config_source,
            "messages": [
                {
                    "id": int(item.get("id") or 0),
                    "role": safe_text(item.get("role")),
                    "content": safe_text(item.get("content")),
                    "model_type": safe_text(item.get("model_type")),
                    "model_name": safe_text(item.get("model_name")),
                    "latency_ms": int(item.get("latency_ms") or 0),
                }
                for item in self.repository.list_messages(conversation_id)
            ],
            "attachments": self.list_attachments(user_id, conversation_id, limit=20),
        }

    def _format_attachment_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        content_text = normalize_attachment_text(item.get("content_text"))
        return {
            "id": int(item.get("id") or 0),
            "filename": normalize_filename(item.get("filename")),
            "mime_type": safe_text(item.get("mime_type")),
            "size_bytes": int(item.get("size_bytes") or 0),
            "content_preview": content_text[:240],
            "created_at": safe_text(item.get("created_at")),
        }

    def list_attachments(self, user_id: str, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return []
        normalized_limit = int(limit or 20)
        if normalized_limit < 1:
            normalized_limit = 1
        if normalized_limit > 100:
            normalized_limit = 100
        rows = self.repository.list_attachments(user_id=user_id, conversation_id=conversation_id, limit=normalized_limit)
        return [self._format_attachment_item(row) for row in rows]

    def upload_attachment(
        self,
        user_id: str,
        conversation_id: str,
        filename: str,
        mime_type: str,
        content_bytes: bytes,
    ) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}

        safe_name = normalize_filename(filename)
        if not safe_name:
            raise RuntimeError("filename is required")
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise RuntimeError("unsupported file type")

        raw = content_bytes or b""
        size_bytes = len(raw)
        if size_bytes <= 0:
            raise RuntimeError("empty file")
        if size_bytes > MAX_ATTACHMENT_BYTES:
            raise RuntimeError("file too large")

        text = ""
        if ext == ".pdf":
            from webapps.pdf.views import _extract_pdf_text_auto
            class FakeUpload:
                def __init__(self, content):
                    self.content = content
                def read(self):
                    return self.content
                def seek(self, *args):
                    pass
            text, _ = _extract_pdf_text_auto(FakeUpload(raw))
        elif ext == ".docx":
            import docx
            import io
            d = docx.Document(io.BytesIO(raw))
            text = "\n".join([p.text for p in d.paragraphs])
        else:
            text = raw.decode("utf-8", errors="replace")

        text = text.replace("\x00", "").replace("\u0000", "")
        normalized_text = normalize_attachment_text(text)
        if not normalized_text:
            raise RuntimeError("empty attachment text")

        self.repository.add_attachment(
            conversation_id=conversation_id,
            user_id=user_id,
            filename=safe_name,
            mime_type=safe_text(mime_type) or "text/plain",
            size_bytes=size_bytes,
            content_text=normalized_text,
        )
        latest = self.repository.list_attachments(user_id=user_id, conversation_id=conversation_id, limit=1)
        if not latest:
            raise RuntimeError("attachment upload failed")
        self.repository.touch_conversation(conversation_id)
        return self._format_attachment_item(latest[0])

    def delete_attachment(self, user_id: str, conversation_id: str, attachment_id: int) -> bool:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return False
        deleted = self.repository.delete_attachment(user_id, conversation_id, attachment_id)
        if deleted > 0:
            self.repository.touch_conversation(conversation_id)
            return True
        return False

    def _build_attachment_context(self, user_id: str, conversation_id: str) -> str:
        rows = self.repository.list_attachments_for_prompt(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=ATTACHMENT_PROMPT_LIMIT,
        )
        if not rows:
            return ""
        lines: List[str] = []
        total_chars = 0
        for item in rows:
            name = normalize_filename(item.get("filename")) or "attachment"
            excerpt = normalize_attachment_text(item.get("content_text"))[:MAX_ATTACHMENT_PROMPT_CHARS]
            if not excerpt:
                continue
            chunk = f"- {name}:\n{excerpt}"
            remaining = MAX_ATTACHMENT_TOTAL_PROMPT_CHARS - total_chars
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            lines.append(chunk)
            total_chars += len(chunk)
        return "\n".join(lines).strip()

    def clear_conversation(self, user_id: str, conversation_id: str) -> bool:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return False
        self.repository.clear_messages(conversation_id)
        self.repository.rename_conversation(user_id, conversation_id, "New Chat")
        self.repository.touch_conversation(conversation_id)
        return True

    def archive_conversation(self, user_id: str, conversation_id: str) -> bool:
        self.ensure_schema()
        return self.repository.archive_conversation(user_id, conversation_id) > 0

    def rename_conversation(self, user_id: str, conversation_id: str, title: str) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}
        normalized_title = " ".join(safe_text(title).split())[:80] or "New Chat"
        self.repository.rename_conversation(user_id, conversation_id, normalized_title)
        refreshed = self.repository.get_conversation(user_id, conversation_id) or {}
        config = self._conversation_config(refreshed)
        return {
            "id": safe_text(refreshed.get("id")),
            "title": safe_text(refreshed.get("title")) or "New Chat",
            "model_type": normalize_model_type(safe_text(refreshed.get("model_type")) or "OLLAMA", default="OLLAMA"),
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "system_prompt": config["system_prompt"],
        }

    def update_conversation_model(self, user_id: str, conversation_id: str, model_type: str, model_name: str = "") -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}
        normalized = normalize_model_type(model_type, default=safe_text(conversation.get("model_type")) or "OLLAMA")
        existing_model_name = safe_text(conversation.get("model_name"))
        chosen_model_name = normalize_model_name(normalized, model_name or existing_model_name)
        self.repository.set_model_type(user_id, conversation_id, normalized, chosen_model_name)
        config = self._conversation_config(conversation)
        self.repository.upsert_user_profile(
            user_id=user_id,
            model_type=normalized,
            model_name=chosen_model_name,
            temperature=config["temperature"],
            timeout_sec=config["timeout_sec"],
            system_prompt=config["system_prompt"],
            chat_mode=config["chat_mode"],
            rag_source=config["rag_source"],
        )
        self.repository.touch_conversation(conversation_id)
        return {
            "id": safe_text(conversation.get("id")),
            "title": safe_text(conversation.get("title")) or "New Chat",
            "model_type": normalized,
            "model_name": chosen_model_name,
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "system_prompt": config["system_prompt"],
        }

    def update_conversation_config(
        self,
        user_id: str,
        conversation_id: str,
        temperature: Any,
        timeout_sec: Any,
        system_prompt: Any,
        chat_mode: Any = None,
        rag_source: Any = None,
    ) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}

        next_temperature = normalize_temperature(
            conversation.get("temperature") if temperature is None else temperature
        )
        next_timeout = normalize_timeout_sec(
            conversation.get("timeout_sec") if timeout_sec is None else timeout_sec
        )
        next_system_prompt = normalize_system_prompt(
            conversation.get("system_prompt") if system_prompt is None else system_prompt
        )
        prev_system_prompt = normalize_system_prompt(conversation.get("system_prompt"))

        next_chat_mode = safe_text(conversation.get("chat_mode") if chat_mode is None else chat_mode) or "GENERAL"
        next_rag_source = safe_text(conversation.get("rag_source") if rag_source is None else rag_source)

        self.repository.set_conversation_config(
            user_id=user_id,
            conversation_id=conversation_id,
            temperature=next_temperature,
            timeout_sec=next_timeout,
            system_prompt=next_system_prompt,
            chat_mode=next_chat_mode,
            rag_source=next_rag_source,
        )
        model_type = normalize_model_type(safe_text(conversation.get("model_type")) or "OLLAMA", default="OLLAMA")
        self.repository.upsert_user_profile(
            user_id=user_id,
            model_type=model_type,
            model_name=safe_text(conversation.get("model_name")) or resolve_model_name(model_type),
            temperature=next_temperature,
            timeout_sec=next_timeout,
            system_prompt=next_system_prompt,
            chat_mode=next_chat_mode,
            rag_source=next_rag_source,
        )
        if system_prompt is not None and next_system_prompt != prev_system_prompt:
            self.repository.add_prompt_history(
                conversation_id=conversation_id,
                user_id=user_id,
                prompt_text=next_system_prompt,
            )

        refreshed = self.repository.get_conversation(user_id, conversation_id) or {}
        config = self._conversation_config(refreshed)
        model_type = normalize_model_type(safe_text(refreshed.get("model_type")) or "OLLAMA", default="OLLAMA")
        return {
            "id": safe_text(refreshed.get("id")),
            "title": safe_text(refreshed.get("title")) or "New Chat",
            "model_type": model_type,
            "model_name": resolve_model_name(model_type),
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "system_prompt": config["system_prompt"],
            "chat_mode": config["chat_mode"],
            "rag_source": config["rag_source"],
            "config_source": "conversation_override",
        }

    def reset_conversation_config_from_profile(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}
        env_model_type = normalize_model_type(os.getenv("MODEL_TYPE") or "OLLAMA", default="OLLAMA")
        env_model_name = resolve_model_name(env_model_type)
        next_temperature = normalize_temperature(DEFAULT_TEMPERATURE, DEFAULT_TEMPERATURE)
        next_timeout = normalize_timeout_sec(DEFAULT_TIMEOUT_SEC, DEFAULT_TIMEOUT_SEC)
        next_system_prompt = ""
        next_chat_mode = "GENERAL"
        next_rag_source = ""

        self.repository.set_model_type(user_id, conversation_id, env_model_type, env_model_name)
        self.repository.set_conversation_config(
            user_id=user_id,
            conversation_id=conversation_id,
            temperature=next_temperature,
            timeout_sec=next_timeout,
            system_prompt=next_system_prompt,
            chat_mode=next_chat_mode,
            rag_source=next_rag_source,
        )
        self.repository.upsert_user_profile(
            user_id=user_id,
            model_type=env_model_type,
            model_name=env_model_name,
            temperature=next_temperature,
            timeout_sec=next_timeout,
            system_prompt=next_system_prompt,
            chat_mode=next_chat_mode,
            rag_source=next_rag_source,
        )
        self.repository.touch_conversation(conversation_id)

        refreshed = self.repository.get_conversation(user_id, conversation_id) or {}
        config = self._conversation_config(refreshed)
        return {
            "id": safe_text(refreshed.get("id")),
            "title": safe_text(refreshed.get("title")) or "New Chat",
            "model_type": safe_text(refreshed.get("model_type")) or env_model_type,
            "model_name": safe_text(refreshed.get("model_name")) or env_model_name,
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "system_prompt": config["system_prompt"],
            "chat_mode": config["chat_mode"],
            "rag_source": config["rag_source"],
            "config_source": "environment",
        }

    def list_prompt_history(self, user_id: str, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return []
        normalized_limit = int(limit or 20)
        if normalized_limit < 1:
            normalized_limit = 1
        if normalized_limit > 50:
            normalized_limit = 50
        rows = self.repository.list_prompt_history(user_id=user_id, conversation_id=conversation_id, limit=normalized_limit)
        return [format_prompt_history_item(row) for row in rows]

    def restore_prompt_history(self, user_id: str, conversation_id: str, history_id: int) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}
        item = self.repository.get_prompt_history_item(user_id=user_id, conversation_id=conversation_id, history_id=history_id)
        if not item:
            raise RuntimeError("prompt history not found")
        prompt_text = normalize_system_prompt(item.get("prompt_text"))
        return self.update_conversation_config(
            user_id=user_id,
            conversation_id=conversation_id,
            temperature=None,
            timeout_sec=None,
            system_prompt=prompt_text,
        )

    def _invoke_reply(
        self,
        messages: List[Dict[str, Any]],
        user_text: str,
        model_type: str,
        model_name: str,
        temperature: float,
        timeout_sec: int,
        system_prompt: str,
        attachment_context: str,
        chat_mode: str = "GENERAL",
        rag_source: str = "",
    ) -> Dict[str, Any]:
        attachment_used = bool(safe_text(attachment_context))
        attachment_count = _attachment_count_from_context(attachment_context)
        if chat_mode == "RAG_PROJECTNOTES" and rag_source:
            try:
                project_id = int(rag_source)
                from .chatbotui_rag_service import query_projectnotes_rag
                rag_result = query_projectnotes_rag(
                    project_id=project_id,
                    query=user_text,
                    history_messages=messages,
                    model_type=model_type,
                    temperature=temperature,
                    timeout_sec=timeout_sec,
                    system_prompt=system_prompt,
                )
                rag_result["attachment_used"] = attachment_used
                rag_result["attachment_count"] = attachment_count
                rag_result["rag_used"] = True
                rag_result["citation_count"] = len(rag_result.get("citations") or [])
                rag_result["rag_reason"] = "rag_hit"
                return rag_result
            except Exception as e:
                # fallback to normal chat path when RAG fails
                rag_reason = "rag_error"
        else:
            rag_reason = "rag_disabled"

        prompt = history_to_prompt(
            messages,
            user_text,
            system_prompt,
            attachment_context,
            max_prompt_chars=MAX_PROMPT_CHARS,
            max_history_items=MAX_HISTORY_ITEMS,
        )
        started = time.perf_counter()
        llm = get_chat_model(
            temperature=temperature,
            timeout=timeout_sec,
            model_type=model_type,
            model_name=model_name,
        )
        try:
            result = llm.invoke(prompt)
        except Exception as exc:
            if not is_context_exceeded_error(exc):
                raise
            retry_profiles = [
                {"max_history_items": 4, "attachment_context": "", "max_prompt_chars": 6000},
                {"max_history_items": 2, "attachment_context": "", "max_prompt_chars": 4000},
                {"max_history_items": 1, "attachment_context": "", "max_prompt_chars": 2000},
            ]
            last_exc: Exception = exc
            result = None
            for profile in retry_profiles:
                try:
                    retry_prompt = history_to_prompt(
                        messages,
                        user_text,
                        system_prompt,
                        profile["attachment_context"],
                        max_prompt_chars=profile["max_prompt_chars"],
                        max_history_items=profile["max_history_items"],
                    )
                    result = llm.invoke(retry_prompt)
                    break
                except Exception as retry_exc:
                    last_exc = retry_exc
                    if not is_context_exceeded_error(retry_exc):
                        raise
            if result is None:
                raise last_exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        answer = extract_message_text(getattr(result, "content", result))
        if not answer:
            raise RuntimeError("empty llm response")
        return {
            "answer": answer,
            "latency_ms": latency_ms,
            "attachment_used": attachment_used,
            "attachment_count": attachment_count,
            "rag_used": False,
            "citation_count": 0,
            "rag_reason": rag_reason,
        }

    def regenerate_last_reply(self, user_id: str, conversation_id: str, model_type: str) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}

        all_messages = self.repository.list_messages(conversation_id)
        if not all_messages:
            raise RuntimeError("no messages to regenerate")

        target_user_idx = -1
        for idx in range(len(all_messages) - 1, -1, -1):
            role = safe_text(all_messages[idx].get("role")).lower()
            if role == "user":
                target_user_idx = idx
                break
        if target_user_idx < 0:
            raise RuntimeError("no user message found")

        latest_user_text = safe_text(all_messages[target_user_idx].get("content"))
        if not latest_user_text:
            raise RuntimeError("last user message is empty")

        # Keep only messages before the target user message for context rebuild.
        history_messages = all_messages[:target_user_idx]

        model_type = normalize_model_type(safe_text(model_type) or safe_text(conversation.get("model_type")) or "OLLAMA", default="OLLAMA")
        model_name = normalize_model_name(model_type, conversation.get("model_name"))
        config = self._conversation_config(conversation)
        attachment_context = self._build_attachment_context(user_id, conversation_id)
        generated = self._invoke_reply(
            history_messages,
            latest_user_text,
            model_type,
            model_name,
            config["temperature"],
            config["timeout_sec"],
            config["system_prompt"],
            attachment_context,
            config["chat_mode"],
            config["rag_source"],
        )
        answer = generated["answer"]
        latency_ms = generated["latency_ms"]

        start_message_id = int(all_messages[target_user_idx].get("id") or 0)
        if start_message_id <= 0:
            raise RuntimeError("invalid target message id")
        self.repository.delete_messages_from(conversation_id, start_message_id)

        self.repository.set_model_type(user_id, conversation_id, model_type, model_name)
        self.repository.add_message(conversation_id, "user", latest_user_text, model_type, model_name, 0)
        self.repository.add_message(conversation_id, "assistant", answer, model_type, model_name, latency_ms)
        self.repository.touch_conversation(conversation_id)
        return {
            "reply": answer,
            "conversation_title": safe_text(conversation.get("title")) or "New Chat",
            "latency_ms": latency_ms,
            "model_type": model_type,
            "model_name": model_name,
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "user_message": latest_user_text,
            "attachment_used": bool(generated.get("attachment_used")),
            "attachment_count": int(generated.get("attachment_count") or 0),
            "rag_used": bool(generated.get("rag_used")),
            "citation_count": int(generated.get("citation_count") or 0),
            "rag_reason": safe_text(generated.get("rag_reason")),
            "citations": _normalize_citations(generated.get("citations")),
        }

    def resend_from_user_message(
        self,
        user_id: str,
        conversation_id: str,
        target_message_id: int,
        user_text: str,
        model_type: str,
    ) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}

        all_messages = self.repository.list_messages(conversation_id)
        if not all_messages:
            raise RuntimeError("no messages found")

        target_idx = -1
        for idx, item in enumerate(all_messages):
            message_id = int(item.get("id") or 0)
            role = safe_text(item.get("role")).lower()
            if message_id == target_message_id and role == "user":
                target_idx = idx
                break
        if target_idx < 0:
            raise RuntimeError("target user message not found")

        normalized_user_text = " ".join(safe_text(user_text).split())
        if not normalized_user_text:
            raise RuntimeError("message is required")

        history_messages = all_messages[:target_idx]
        model_type = normalize_model_type(safe_text(model_type) or safe_text(conversation.get("model_type")) or "OLLAMA", default="OLLAMA")
        model_name = normalize_model_name(model_type, conversation.get("model_name"))
        config = self._conversation_config(conversation)
        attachment_context = self._build_attachment_context(user_id, conversation_id)
        generated = self._invoke_reply(
            history_messages,
            normalized_user_text,
            model_type,
            model_name,
            config["temperature"],
            config["timeout_sec"],
            config["system_prompt"],
            attachment_context,
            config["chat_mode"],
            config["rag_source"],
        )

        self.repository.delete_messages_from(conversation_id, target_message_id)
        self.repository.set_model_type(user_id, conversation_id, model_type, model_name)
        self.repository.add_message(conversation_id, "user", normalized_user_text, model_type, model_name, 0)
        self.repository.add_message(conversation_id, "assistant", generated["answer"], model_type, model_name, generated["latency_ms"])
        self.repository.touch_conversation(conversation_id)
        return {
            "reply": generated["answer"],
            "conversation_title": safe_text(conversation.get("title")) or "New Chat",
            "latency_ms": generated["latency_ms"],
            "model_type": model_type,
            "model_name": model_name,
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "user_message": normalized_user_text,
            "attachment_used": bool(generated.get("attachment_used")),
            "attachment_count": int(generated.get("attachment_count") or 0),
            "rag_used": bool(generated.get("rag_used")),
            "citation_count": int(generated.get("citation_count") or 0),
            "rag_reason": safe_text(generated.get("rag_reason")),
            "citations": _normalize_citations(generated.get("citations")),
        }

    def chat(self, user_id: str, conversation_id: str, user_text: str, model_type: str) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}

        model_type = normalize_model_type(safe_text(model_type) or safe_text(conversation.get("model_type")) or "OLLAMA", default="OLLAMA")
        model_name = normalize_model_name(model_type, conversation.get("model_name"))
        current_messages = self.repository.list_messages(conversation_id)
        config = self._conversation_config(conversation)
        attachment_context = self._build_attachment_context(user_id, conversation_id)
        generated = self._invoke_reply(
            current_messages,
            user_text,
            model_type,
            model_name,
            config["temperature"],
            config["timeout_sec"],
            config["system_prompt"],
            attachment_context,
            config["chat_mode"],
            config["rag_source"],
        )
        answer = generated["answer"]
        latency_ms = generated["latency_ms"]

        if not current_messages:
            self.repository.rename_conversation(user_id, conversation_id, infer_title(user_text))
        self.repository.set_model_type(user_id, conversation_id, model_type, model_name)
        self.repository.add_message(conversation_id, "user", user_text, model_type, model_name, 0)
        self.repository.add_message(conversation_id, "assistant", answer, model_type, model_name, latency_ms)
        self.repository.touch_conversation(conversation_id)
        return {
            "reply": answer,
            "conversation_title": infer_title(user_text) if not current_messages else safe_text(conversation.get("title")) or "New Chat",
            "latency_ms": latency_ms,
            "model_type": model_type,
            "model_name": model_name,
            "temperature": config["temperature"],
            "timeout_sec": config["timeout_sec"],
            "attachment_used": bool(generated.get("attachment_used")),
            "attachment_count": int(generated.get("attachment_count") or 0),
            "rag_used": bool(generated.get("rag_used")),
            "citation_count": int(generated.get("citation_count") or 0),
            "rag_reason": safe_text(generated.get("rag_reason")),
            "citations": _normalize_citations(generated.get("citations")),
        }

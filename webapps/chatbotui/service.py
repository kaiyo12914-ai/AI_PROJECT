from __future__ import annotations

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


def history_to_prompt(messages: List[Dict[str, Any]], latest_user_text: str) -> str:
    lines: List[str] = [SYSTEM_PROMPT.strip(), "", "Conversation history:"]
    for item in messages[-12:]:
        if not isinstance(item, dict):
            continue
        role = safe_text(item.get("role")).lower()
        content = safe_text(item.get("content"))
        if not content:
            continue
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content}")
    lines.append(f"User: {latest_user_text}")
    lines.append("Assistant:")
    return "\n".join(lines)


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
            out.append({
                "id": safe_text(row.get("id")),
                "title": safe_text(row.get("title")) or "New Chat",
                "model_type": safe_text(row.get("model_type")) or "OPENAI",
                "updated_at": safe_text(row.get("updated_at")),
                "preview": safe_text(row.get("last_message_preview"))[:80],
                "message_count": int(row.get("message_count") or 0),
            })
        return out

    def create_conversation(self, user_id: str, title: str = "New Chat", model_type: str = "OPENAI") -> Dict[str, Any]:
        self.ensure_schema()
        conversation_id = str(uuid.uuid4())
        self.repository.create_conversation(conversation_id, user_id, safe_text(title) or "New Chat", safe_text(model_type) or "OPENAI")
        return self.get_conversation_detail(user_id, conversation_id)

    def get_conversation_detail(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}
        return {
            "id": safe_text(conversation.get("id")),
            "title": safe_text(conversation.get("title")) or "New Chat",
            "model_type": safe_text(conversation.get("model_type")) or "OPENAI",
            "messages": [
                {
                    "id": int(item.get("id") or 0),
                    "role": safe_text(item.get("role")),
                    "content": safe_text(item.get("content")),
                    "model_type": safe_text(item.get("model_type")),
                    "latency_ms": int(item.get("latency_ms") or 0),
                }
                for item in self.repository.list_messages(conversation_id)
            ],
        }

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

    def chat(self, user_id: str, conversation_id: str, user_text: str, model_type: str) -> Dict[str, Any]:
        self.ensure_schema()
        conversation = self.repository.get_conversation(user_id, conversation_id)
        if not conversation:
            return {}

        model_type = safe_text(model_type) or safe_text(conversation.get("model_type")) or "OPENAI"
        current_messages = self.repository.list_messages(conversation_id)
        prompt = history_to_prompt(current_messages, user_text)

        started = time.perf_counter()
        llm = get_chat_model(temperature=0.3, timeout=120, model_type=model_type)
        result = llm.invoke(prompt)
        latency_ms = int((time.perf_counter() - started) * 1000)
        answer = extract_message_text(getattr(result, "content", result))
        if not answer:
            raise RuntimeError("empty llm response")

        if not current_messages:
            self.repository.rename_conversation(user_id, conversation_id, infer_title(user_text))
        self.repository.set_model_type(user_id, conversation_id, model_type)
        self.repository.add_message(conversation_id, "user", user_text, model_type, 0)
        self.repository.add_message(conversation_id, "assistant", answer, model_type, latency_ms)
        self.repository.touch_conversation(conversation_id)
        return {
            "reply": answer,
            "conversation_title": infer_title(user_text) if not current_messages else safe_text(conversation.get("title")) or "New Chat",
            "latency_ms": latency_ms,
            "model_type": model_type,
        }


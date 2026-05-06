from __future__ import annotations

from typing import Any, Dict, List

from webapps.repositories.base import BaseRepository


class ChatbotUIRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__(db_type="postgresql")
        self.profile = "CHATBOTUI"

    def ensure_schema(self) -> None:
        sql = """
        CREATE TABLE IF NOT EXISTS chatbotui_conversation (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'New Chat',
            model_type TEXT NOT NULL DEFAULT 'OPENAI',
            is_archived BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS chatbotui_message (
            id BIGSERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES chatbotui_conversation(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model_type TEXT,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_chatbotui_conversation_user_updated
            ON chatbotui_conversation (user_id, is_archived, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_chatbotui_message_conversation_created
            ON chatbotui_message (conversation_id, created_at ASC, id ASC);
        """
        self.execute(sql, profile=self.profile)

    def list_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            c.id,
            c.title,
            c.model_type,
            c.created_at,
            c.updated_at,
            (
                SELECT m.content
                FROM chatbotui_message m
                WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT 1
            ) AS last_message_preview,
            (
                SELECT COUNT(*)
                FROM chatbotui_message m
                WHERE m.conversation_id = c.id
            ) AS message_count
        FROM chatbotui_conversation c
        WHERE c.user_id = %s
          AND c.is_archived = FALSE
        ORDER BY c.updated_at DESC, c.id DESC
        """
        rows = self.query_all(sql, [user_id], profile=self.profile)
        return [self._conversation_row_to_dict(row) for row in rows]

    def create_conversation(self, conversation_id: str, user_id: str, title: str, model_type: str) -> int:
        sql = """
        INSERT INTO chatbotui_conversation (
            id, user_id, title, model_type, is_archived, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, FALSE, NOW(), NOW()
        )
        """
        return self.execute(sql, [conversation_id, user_id, title, model_type], profile=self.profile)

    def get_conversation(self, user_id: str, conversation_id: str) -> Dict[str, Any] | None:
        sql = """
        SELECT id, title, model_type, created_at, updated_at
        FROM chatbotui_conversation
        WHERE id = %s
          AND user_id = %s
          AND is_archived = FALSE
        """
        row = self.query_one(sql, [conversation_id, user_id], profile=self.profile)
        return self._conversation_row_to_dict(row) if row else None

    def rename_conversation(self, user_id: str, conversation_id: str, title: str) -> int:
        sql = """
        UPDATE chatbotui_conversation
        SET title = %s,
            updated_at = NOW()
        WHERE id = %s
          AND user_id = %s
          AND is_archived = FALSE
        """
        return self.execute(sql, [title, conversation_id, user_id], profile=self.profile)

    def set_model_type(self, user_id: str, conversation_id: str, model_type: str) -> int:
        sql = """
        UPDATE chatbotui_conversation
        SET model_type = %s,
            updated_at = NOW()
        WHERE id = %s
          AND user_id = %s
          AND is_archived = FALSE
        """
        return self.execute(sql, [model_type, conversation_id, user_id], profile=self.profile)

    def archive_conversation(self, user_id: str, conversation_id: str) -> int:
        sql = """
        UPDATE chatbotui_conversation
        SET is_archived = TRUE,
            updated_at = NOW()
        WHERE id = %s
          AND user_id = %s
          AND is_archived = FALSE
        """
        return self.execute(sql, [conversation_id, user_id], profile=self.profile)

    def list_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT id, role, content, model_type, latency_ms, created_at
        FROM chatbotui_message
        WHERE conversation_id = %s
        ORDER BY created_at ASC, id ASC
        """
        rows = self.query_all(sql, [conversation_id], profile=self.profile)
        return [self._message_row_to_dict(row) for row in rows]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model_type: str,
        latency_ms: int = 0,
    ) -> int:
        sql = """
        INSERT INTO chatbotui_message (
            conversation_id, role, content, model_type, latency_ms, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, NOW()
        )
        """
        return self.execute(sql, [conversation_id, role, content, model_type, latency_ms], profile=self.profile)

    def clear_messages(self, conversation_id: str) -> int:
        sql = "DELETE FROM chatbotui_message WHERE conversation_id = %s"
        return self.execute(sql, [conversation_id], profile=self.profile)

    def touch_conversation(self, conversation_id: str) -> int:
        sql = """
        UPDATE chatbotui_conversation
        SET updated_at = NOW()
        WHERE id = %s
        """
        return self.execute(sql, [conversation_id], profile=self.profile)

    @staticmethod
    def _conversation_row_to_dict(row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        if isinstance(row, dict):
            return dict(row)
        if isinstance(row, (list, tuple)):
            return {
                "id": row[0] if len(row) > 0 else "",
                "title": row[1] if len(row) > 1 else "New Chat",
                "model_type": row[2] if len(row) > 2 else "OPENAI",
                "created_at": row[3] if len(row) > 3 else None,
                "updated_at": row[4] if len(row) > 4 else None,
                "last_message_preview": row[5] if len(row) > 5 else "",
                "message_count": int(row[6] or 0) if len(row) > 6 else 0,
            }
        return {
            "id": getattr(row, "id", ""),
            "title": getattr(row, "title", "New Chat"),
            "model_type": getattr(row, "model_type", "OPENAI"),
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
            "last_message_preview": getattr(row, "last_message_preview", ""),
            "message_count": int(getattr(row, "message_count", 0) or 0),
        }

    @staticmethod
    def _message_row_to_dict(row: Any) -> Dict[str, Any]:
        if isinstance(row, dict):
            return dict(row)
        if isinstance(row, (list, tuple)):
            return {
                "id": row[0] if len(row) > 0 else 0,
                "role": row[1] if len(row) > 1 else "",
                "content": row[2] if len(row) > 2 else "",
                "model_type": row[3] if len(row) > 3 else "",
                "latency_ms": int(row[4] or 0) if len(row) > 4 else 0,
                "created_at": row[5] if len(row) > 5 else None,
            }
        return {
            "id": getattr(row, "id", 0),
            "role": getattr(row, "role", ""),
            "content": getattr(row, "content", ""),
            "model_type": getattr(row, "model_type", ""),
            "latency_ms": int(getattr(row, "latency_ms", 0) or 0),
            "created_at": getattr(row, "created_at", None),
        }


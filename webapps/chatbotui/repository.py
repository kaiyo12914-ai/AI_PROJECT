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
            temperature DOUBLE PRECISION NOT NULL DEFAULT 0.3,
            timeout_sec INTEGER NOT NULL DEFAULT 120,
            system_prompt TEXT NOT NULL DEFAULT '',
            chat_mode TEXT NOT NULL DEFAULT 'GENERAL',
            rag_source TEXT NOT NULL DEFAULT '',
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

        CREATE TABLE IF NOT EXISTS chatbotui_prompt_history (
            id BIGSERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES chatbotui_conversation(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS chatbotui_attachment (
            id BIGSERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES chatbotui_conversation(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            content_text TEXT NOT NULL DEFAULT '',
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS chatbotui_user_profile (
            user_id TEXT PRIMARY KEY,
            model_type TEXT NOT NULL DEFAULT 'OPENAI',
            model_name TEXT NOT NULL DEFAULT '',
            temperature DOUBLE PRECISION NOT NULL DEFAULT 0.3,
            timeout_sec INTEGER NOT NULL DEFAULT 120,
            system_prompt TEXT NOT NULL DEFAULT '',
            chat_mode TEXT NOT NULL DEFAULT 'GENERAL',
            rag_source TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_chatbotui_conversation_user_updated
            ON chatbotui_conversation (user_id, is_archived, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_chatbotui_message_conversation_created
            ON chatbotui_message (conversation_id, created_at ASC, id ASC);

        CREATE INDEX IF NOT EXISTS idx_chatbotui_prompt_history_conversation_created
            ON chatbotui_prompt_history (conversation_id, created_at DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_chatbotui_attachment_conversation_created
            ON chatbotui_attachment (conversation_id, created_at DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_chatbotui_user_profile_updated
            ON chatbotui_user_profile (updated_at DESC);

        ALTER TABLE chatbotui_conversation
            ADD COLUMN IF NOT EXISTS temperature DOUBLE PRECISION NOT NULL DEFAULT 0.3;

        ALTER TABLE chatbotui_conversation
            ADD COLUMN IF NOT EXISTS timeout_sec INTEGER NOT NULL DEFAULT 120;

        ALTER TABLE chatbotui_conversation
            ADD COLUMN IF NOT EXISTS system_prompt TEXT NOT NULL DEFAULT '';
            
        ALTER TABLE chatbotui_conversation
            ADD COLUMN IF NOT EXISTS chat_mode TEXT NOT NULL DEFAULT 'GENERAL';
            
        ALTER TABLE chatbotui_conversation
            ADD COLUMN IF NOT EXISTS rag_source TEXT NOT NULL DEFAULT '';
            
        ALTER TABLE chatbotui_conversation
            ADD COLUMN IF NOT EXISTS model_name TEXT NOT NULL DEFAULT '';

        ALTER TABLE chatbotui_user_profile
            ADD COLUMN IF NOT EXISTS model_name TEXT NOT NULL DEFAULT '';
        """
        self.execute(sql, profile=self.profile)

    def get_user_profile(self, user_id: str) -> Dict[str, Any] | None:
        sql = """
        SELECT user_id, model_type, model_name, temperature, timeout_sec, system_prompt, chat_mode, rag_source, updated_at
        FROM chatbotui_user_profile
        WHERE user_id = %s
        LIMIT 1
        """
        row = self.query_one(sql, [user_id], profile=self.profile)
        if not row:
            return None
        if isinstance(row, dict):
            return dict(row)
        if isinstance(row, (list, tuple)):
            return {
                "user_id": row[0] if len(row) > 0 else "",
                "model_type": row[1] if len(row) > 1 else "OPENAI",
                "model_name": row[2] if len(row) > 2 else "",
                "temperature": row[3] if len(row) > 3 else 0.3,
                "timeout_sec": row[4] if len(row) > 4 else 120,
                "system_prompt": row[5] if len(row) > 5 else "",
                "chat_mode": row[6] if len(row) > 6 else "GENERAL",
                "rag_source": row[7] if len(row) > 7 else "",
                "updated_at": row[8] if len(row) > 8 else None,
            }
        return {
            "user_id": getattr(row, "user_id", ""),
            "model_type": getattr(row, "model_type", "OPENAI"),
            "model_name": getattr(row, "model_name", ""),
            "temperature": getattr(row, "temperature", 0.3),
            "timeout_sec": getattr(row, "timeout_sec", 120),
            "system_prompt": getattr(row, "system_prompt", ""),
            "chat_mode": getattr(row, "chat_mode", "GENERAL"),
            "rag_source": getattr(row, "rag_source", ""),
            "updated_at": getattr(row, "updated_at", None),
        }

    def upsert_user_profile(
        self,
        user_id: str,
        model_type: str,
        model_name: str,
        temperature: float,
        timeout_sec: int,
        system_prompt: str,
        chat_mode: str = "GENERAL",
        rag_source: str = "",
    ) -> int:
        sql = """
        INSERT INTO chatbotui_user_profile (
            user_id, model_type, model_name, temperature, timeout_sec, system_prompt, chat_mode, rag_source, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, NOW()
        )
        ON CONFLICT (user_id) DO UPDATE
        SET model_type = EXCLUDED.model_type,
            model_name = EXCLUDED.model_name,
            temperature = EXCLUDED.temperature,
            timeout_sec = EXCLUDED.timeout_sec,
            system_prompt = EXCLUDED.system_prompt,
            chat_mode = EXCLUDED.chat_mode,
            rag_source = EXCLUDED.rag_source,
            updated_at = NOW()
        """
        return self.execute(
            sql,
            [user_id, model_type, model_name, temperature, timeout_sec, system_prompt, chat_mode, rag_source],
            profile=self.profile,
        )

    def list_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            c.id,
            c.title,
            c.model_type,
            c.temperature,
            c.timeout_sec,
            c.system_prompt,
            c.chat_mode,
            c.rag_source,
            c.model_name,
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

    def create_conversation(
        self,
        conversation_id: str,
        user_id: str,
        title: str,
        model_type: str,
        temperature: float,
        timeout_sec: int,
        system_prompt: str,
        chat_mode: str = 'GENERAL',
        rag_source: str = '',
        model_name: str = '',
    ) -> int:
        sql = """
        INSERT INTO chatbotui_conversation (
            id, user_id, title, model_type, model_name, temperature, timeout_sec, system_prompt, chat_mode, rag_source, is_archived, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NOW(), NOW()
        )
        """
        return self.execute(
            sql,
            [conversation_id, user_id, title, model_type, model_name, temperature, timeout_sec, system_prompt, chat_mode, rag_source],
            profile=self.profile,
        )

    def get_conversation(self, user_id: str, conversation_id: str) -> Dict[str, Any] | None:
        sql = """
        SELECT id, title, model_type, model_name, temperature, timeout_sec, system_prompt, chat_mode, rag_source, created_at, updated_at
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

    def set_model_type(self, user_id: str, conversation_id: str, model_type: str, model_name: str = "") -> int:
        sql = """
        UPDATE chatbotui_conversation
        SET model_type = %s,
            model_name = %s,
            updated_at = NOW()
        WHERE id = %s
          AND user_id = %s
          AND is_archived = FALSE
        """
        return self.execute(sql, [model_type, model_name, conversation_id, user_id], profile=self.profile)

    def set_conversation_config(
        self,
        user_id: str,
        conversation_id: str,
        temperature: float,
        timeout_sec: int,
        system_prompt: str,
        chat_mode: str = 'GENERAL',
        rag_source: str = '',
    ) -> int:
        sql = """
        UPDATE chatbotui_conversation
        SET temperature = %s,
            timeout_sec = %s,
            system_prompt = %s,
            chat_mode = %s,
            rag_source = %s,
            updated_at = NOW()
        WHERE id = %s
          AND user_id = %s
          AND is_archived = FALSE
        """
        return self.execute(sql, [temperature, timeout_sec, system_prompt, chat_mode, rag_source, conversation_id, user_id], profile=self.profile)

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

    def delete_message(self, conversation_id: str, message_id: int) -> int:
        sql = """
        DELETE FROM chatbotui_message
        WHERE conversation_id = %s
          AND id = %s
        """
        return self.execute(sql, [conversation_id, message_id], profile=self.profile)

    def delete_messages_from(self, conversation_id: str, start_message_id: int) -> int:
        sql = """
        DELETE FROM chatbotui_message
        WHERE conversation_id = %s
          AND id >= %s
        """
        return self.execute(sql, [conversation_id, start_message_id], profile=self.profile)

    def touch_conversation(self, conversation_id: str) -> int:
        sql = """
        UPDATE chatbotui_conversation
        SET updated_at = NOW()
        WHERE id = %s
        """
        return self.execute(sql, [conversation_id], profile=self.profile)

    def add_prompt_history(self, conversation_id: str, user_id: str, prompt_text: str) -> int:
        sql = """
        INSERT INTO chatbotui_prompt_history (conversation_id, user_id, prompt_text, created_at)
        VALUES (%s, %s, %s, NOW())
        """
        return self.execute(sql, [conversation_id, user_id, prompt_text], profile=self.profile)

    def list_prompt_history(self, user_id: str, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        sql = """
        SELECT h.id, h.prompt_text, h.created_at
        FROM chatbotui_prompt_history h
        JOIN chatbotui_conversation c ON c.id = h.conversation_id
        WHERE h.conversation_id = %s
          AND c.user_id = %s
          AND c.is_archived = FALSE
        ORDER BY h.created_at DESC, h.id DESC
        LIMIT %s
        """
        rows = self.query_all(sql, [conversation_id, user_id, limit], profile=self.profile)
        out: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append({
                    "id": int(row.get("id") or 0),
                    "prompt_text": row.get("prompt_text") or "",
                    "created_at": row.get("created_at"),
                })
            elif isinstance(row, (list, tuple)):
                out.append({
                    "id": int(row[0] or 0) if len(row) > 0 else 0,
                    "prompt_text": row[1] if len(row) > 1 and row[1] is not None else "",
                    "created_at": row[2] if len(row) > 2 else None,
                })
            else:
                out.append({
                    "id": int(getattr(row, "id", 0) or 0),
                    "prompt_text": getattr(row, "prompt_text", "") or "",
                    "created_at": getattr(row, "created_at", None),
                })
        return out

    def get_prompt_history_item(self, user_id: str, conversation_id: str, history_id: int) -> Dict[str, Any] | None:
        sql = """
        SELECT h.id, h.prompt_text, h.created_at
        FROM chatbotui_prompt_history h
        JOIN chatbotui_conversation c ON c.id = h.conversation_id
        WHERE h.id = %s
          AND h.conversation_id = %s
          AND c.user_id = %s
          AND c.is_archived = FALSE
        LIMIT 1
        """
        row = self.query_one(sql, [history_id, conversation_id, user_id], profile=self.profile)
        if not row:
            return None
        if isinstance(row, dict):
            return {
                "id": int(row.get("id") or 0),
                "prompt_text": row.get("prompt_text") or "",
                "created_at": row.get("created_at"),
            }
        if isinstance(row, (list, tuple)):
            return {
                "id": int(row[0] or 0) if len(row) > 0 else 0,
                "prompt_text": row[1] if len(row) > 1 and row[1] is not None else "",
                "created_at": row[2] if len(row) > 2 else None,
            }
        return {
            "id": int(getattr(row, "id", 0) or 0),
            "prompt_text": getattr(row, "prompt_text", "") or "",
            "created_at": getattr(row, "created_at", None),
        }

    def add_attachment(
        self,
        conversation_id: str,
        user_id: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        content_text: str,
    ) -> int:
        sql = """
        INSERT INTO chatbotui_attachment (
            conversation_id, user_id, filename, mime_type, size_bytes, content_text, is_deleted, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, FALSE, NOW()
        )
        """
        return self.execute(
            sql,
            [conversation_id, user_id, filename, mime_type, size_bytes, content_text],
            profile=self.profile,
        )

    def list_attachments(self, user_id: str, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        sql = """
        SELECT a.id, a.filename, a.mime_type, a.size_bytes, a.content_text, a.created_at
        FROM chatbotui_attachment a
        JOIN chatbotui_conversation c ON a.conversation_id = c.id
        WHERE a.conversation_id = %s
          AND c.user_id = %s
          AND c.is_archived = FALSE
          AND a.is_deleted = FALSE
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT %s
        """
        rows = self.query_all(sql, [conversation_id, user_id, limit], profile=self.profile)
        out: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append({
                    "id": int(row.get("id") or 0),
                    "filename": row.get("filename") or "",
                    "mime_type": row.get("mime_type") or "",
                    "size_bytes": int(row.get("size_bytes") or 0),
                    "content_text": row.get("content_text") or "",
                    "created_at": row.get("created_at"),
                })
            elif isinstance(row, (list, tuple)):
                out.append({
                    "id": int(row[0] or 0) if len(row) > 0 else 0,
                    "filename": row[1] if len(row) > 1 and row[1] is not None else "",
                    "mime_type": row[2] if len(row) > 2 and row[2] is not None else "",
                    "size_bytes": int(row[3] or 0) if len(row) > 3 else 0,
                    "content_text": row[4] if len(row) > 4 and row[4] is not None else "",
                    "created_at": row[5] if len(row) > 5 else None,
                })
            else:
                out.append({
                    "id": int(getattr(row, "id", 0) or 0),
                    "filename": getattr(row, "filename", "") or "",
                    "mime_type": getattr(row, "mime_type", "") or "",
                    "size_bytes": int(getattr(row, "size_bytes", 0) or 0),
                    "content_text": getattr(row, "content_text", "") or "",
                    "created_at": getattr(row, "created_at", None),
                })
        return out

    def delete_attachment(self, user_id: str, conversation_id: str, attachment_id: int) -> int:
        sql = """
        UPDATE chatbotui_attachment
        SET is_deleted = TRUE
        WHERE id = %s
          AND conversation_id = %s
          AND EXISTS (
              SELECT 1 FROM chatbotui_conversation
              WHERE id = %s AND user_id = %s
          )
        """
        return self.execute(sql, [attachment_id, conversation_id, conversation_id, user_id], profile=self.profile)

    def list_attachments_for_prompt(self, user_id: str, conversation_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        sql = """
        SELECT a.id, a.filename, a.content_text, a.created_at
        FROM chatbotui_attachment a
        JOIN chatbotui_conversation c ON a.conversation_id = c.id
        WHERE a.conversation_id = %s
          AND c.user_id = %s
          AND c.is_archived = FALSE
          AND a.is_deleted = FALSE
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT %s
        """
        rows = self.query_all(sql, [conversation_id, user_id, limit], profile=self.profile)
        out: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append({
                    "id": int(row.get("id") or 0),
                    "filename": row.get("filename") or "",
                    "content_text": row.get("content_text") or "",
                    "created_at": row.get("created_at"),
                })
            elif isinstance(row, (list, tuple)):
                out.append({
                    "id": int(row[0] or 0) if len(row) > 0 else 0,
                    "filename": row[1] if len(row) > 1 and row[1] is not None else "",
                    "content_text": row[2] if len(row) > 2 and row[2] is not None else "",
                    "created_at": row[3] if len(row) > 3 else None,
                })
            else:
                out.append({
                    "id": int(getattr(row, "id", 0) or 0),
                    "filename": getattr(row, "filename", "") or "",
                    "content_text": getattr(row, "content_text", "") or "",
                    "created_at": getattr(row, "created_at", None),
                })
        return out

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
                "model_name": row[3] if len(row) > 3 else "",
                "temperature": row[4] if len(row) > 4 else 0.3,
                "timeout_sec": row[5] if len(row) > 5 else 120,
                "system_prompt": row[6] if len(row) > 6 else "",
                "chat_mode": row[7] if len(row) > 7 else "GENERAL",
                "rag_source": row[8] if len(row) > 8 else "",
                "created_at": row[9] if len(row) > 9 else None,
                "updated_at": row[10] if len(row) > 10 else None,
                "last_message_preview": row[11] if len(row) > 11 else "",
                "message_count": int(row[12] or 0) if len(row) > 12 else 0,
            }
        return {
            "id": getattr(row, "id", ""),
            "title": getattr(row, "title", "New Chat"),
            "model_type": getattr(row, "model_type", "OPENAI"),
            "model_name": getattr(row, "model_name", ""),
            "temperature": getattr(row, "temperature", 0.3),
            "timeout_sec": getattr(row, "timeout_sec", 120),
            "system_prompt": getattr(row, "system_prompt", ""),
            "chat_mode": getattr(row, "chat_mode", "GENERAL"),
            "rag_source": getattr(row, "rag_source", ""),
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

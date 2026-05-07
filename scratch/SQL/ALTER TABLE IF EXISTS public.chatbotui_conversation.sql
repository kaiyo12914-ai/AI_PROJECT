-- Table: public.chatbotui_conversation

-- DROP TABLE IF EXISTS public.chatbotui_conversation;

CREATE TABLE IF NOT EXISTS public.chatbotui_conversation
(
    id text COLLATE pg_catalog."default" NOT NULL,
    user_id text COLLATE pg_catalog."default" NOT NULL,
    title text COLLATE pg_catalog."default" NOT NULL DEFAULT 'New Chat'::text,
    model_type text COLLATE pg_catalog."default" NOT NULL DEFAULT 'OPENAI'::text,
    is_archived boolean NOT NULL DEFAULT false,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    temperature double precision NOT NULL DEFAULT 0.3,
    timeout_sec integer NOT NULL DEFAULT 120,
    system_prompt text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    chat_mode text COLLATE pg_catalog."default" NOT NULL DEFAULT 'GENERAL'::text,
    rag_source text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    model_name text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    CONSTRAINT chatbotui_conversation_pkey PRIMARY KEY (id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.chatbotui_conversation
    OWNER to projectnotes_user;
-- Index: idx_chatbotui_conversation_user_updated

-- DROP INDEX IF EXISTS public.idx_chatbotui_conversation_user_updated;

CREATE INDEX IF NOT EXISTS idx_chatbotui_conversation_user_updated
    ON public.chatbotui_conversation USING btree
    (user_id COLLATE pg_catalog."default" ASC NULLS LAST, is_archived ASC NULLS LAST, updated_at DESC NULLS FIRST)
    TABLESPACE pg_default;
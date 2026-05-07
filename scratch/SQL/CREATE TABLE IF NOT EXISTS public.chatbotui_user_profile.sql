-- Table: public.chatbotui_user_profile

-- DROP TABLE IF EXISTS public.chatbotui_user_profile;

CREATE TABLE IF NOT EXISTS public.chatbotui_user_profile
(
    user_id text COLLATE pg_catalog."default" NOT NULL,
    model_type text COLLATE pg_catalog."default" NOT NULL DEFAULT 'OPENAI'::text,
    model_name text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    temperature double precision NOT NULL DEFAULT 0.3,
    timeout_sec integer NOT NULL DEFAULT 120,
    system_prompt text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    chat_mode text COLLATE pg_catalog."default" NOT NULL DEFAULT 'GENERAL'::text,
    rag_source text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT chatbotui_user_profile_pkey PRIMARY KEY (user_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.chatbotui_user_profile
    OWNER to projectnotes_user;
-- Index: idx_chatbotui_user_profile_updated

-- DROP INDEX IF EXISTS public.idx_chatbotui_user_profile_updated;

CREATE INDEX IF NOT EXISTS idx_chatbotui_user_profile_updated
    ON public.chatbotui_user_profile USING btree
    (updated_at DESC NULLS FIRST)
    TABLESPACE pg_default;
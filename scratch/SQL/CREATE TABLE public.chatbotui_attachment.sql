-- Table: public.chatbotui_attachment

-- DROP TABLE IF EXISTS public.chatbotui_attachment;

CREATE TABLE IF NOT EXISTS public.chatbotui_attachment
(
    id bigint NOT NULL DEFAULT nextval('chatbotui_attachment_id_seq'::regclass),
    conversation_id text COLLATE pg_catalog."default" NOT NULL,
    user_id text COLLATE pg_catalog."default" NOT NULL,
    filename text COLLATE pg_catalog."default" NOT NULL,
    mime_type text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    size_bytes integer NOT NULL DEFAULT 0,
    content_text text COLLATE pg_catalog."default" NOT NULL DEFAULT ''::text,
    is_deleted boolean NOT NULL DEFAULT false,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT chatbotui_attachment_pkey PRIMARY KEY (id),
    CONSTRAINT chatbotui_attachment_conversation_id_fkey FOREIGN KEY (conversation_id)
        REFERENCES public.chatbotui_conversation (id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.chatbotui_attachment
    OWNER to projectnotes_user;
-- Index: idx_chatbotui_attachment_conversation_created

-- DROP INDEX IF EXISTS public.idx_chatbotui_attachment_conversation_created;

CREATE INDEX IF NOT EXISTS idx_chatbotui_attachment_conversation_created
    ON public.chatbotui_attachment USING btree
    (conversation_id COLLATE pg_catalog."default" ASC NULLS LAST, created_at DESC NULLS FIRST, id DESC NULLS FIRST)
    TABLESPACE pg_default;
-- Table: public.chatbotui_message

-- DROP TABLE IF EXISTS public.chatbotui_message;

CREATE TABLE IF NOT EXISTS public.chatbotui_message
(
    id bigint NOT NULL DEFAULT nextval('chatbotui_message_id_seq'::regclass),
    conversation_id text COLLATE pg_catalog."default" NOT NULL,
    role text COLLATE pg_catalog."default" NOT NULL,
    content text COLLATE pg_catalog."default" NOT NULL,
    model_type text COLLATE pg_catalog."default",
    latency_ms integer NOT NULL DEFAULT 0,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT chatbotui_message_pkey PRIMARY KEY (id),
    CONSTRAINT chatbotui_message_conversation_id_fkey FOREIGN KEY (conversation_id)
        REFERENCES public.chatbotui_conversation (id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.chatbotui_message
    OWNER to projectnotes_user;
-- Index: idx_chatbotui_message_conversation_created

-- DROP INDEX IF EXISTS public.idx_chatbotui_message_conversation_created;

CREATE INDEX IF NOT EXISTS idx_chatbotui_message_conversation_created
    ON public.chatbotui_message USING btree
    (conversation_id COLLATE pg_catalog."default" ASC NULLS LAST, created_at ASC NULLS LAST, id ASC NULLS LAST)
    TABLESPACE pg_default;
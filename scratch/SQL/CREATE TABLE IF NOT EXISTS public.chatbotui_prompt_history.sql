-- Table: public.chatbotui_prompt_history

-- DROP TABLE IF EXISTS public.chatbotui_prompt_history;

CREATE TABLE IF NOT EXISTS public.chatbotui_prompt_history
(
    id bigint NOT NULL DEFAULT nextval('chatbotui_prompt_history_id_seq'::regclass),
    conversation_id text COLLATE pg_catalog."default" NOT NULL,
    user_id text COLLATE pg_catalog."default" NOT NULL,
    prompt_text text COLLATE pg_catalog."default" NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT chatbotui_prompt_history_pkey PRIMARY KEY (id),
    CONSTRAINT chatbotui_prompt_history_conversation_id_fkey FOREIGN KEY (conversation_id)
        REFERENCES public.chatbotui_conversation (id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.chatbotui_prompt_history
    OWNER to projectnotes_user;
-- Index: idx_chatbotui_prompt_history_conversation_created

-- DROP INDEX IF EXISTS public.idx_chatbotui_prompt_history_conversation_created;

CREATE INDEX IF NOT EXISTS idx_chatbotui_prompt_history_conversation_created
    ON public.chatbotui_prompt_history USING btree
    (conversation_id COLLATE pg_catalog."default" ASC NULLS LAST, created_at DESC NULLS FIRST, id DESC NULLS FIRST)
    TABLESPACE pg_default;
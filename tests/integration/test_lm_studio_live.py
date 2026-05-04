import os

from webapps.llm.llm_factory import get_chat_model


def test_lm_studio_live_invoke_returns_text(monkeypatch):
    monkeypatch.setenv("MODEL_TYPE", "LM_STUDIO")
    monkeypatch.setenv("LM_STUDIO_BASE_URL", os.getenv("LM_STUDIO_BASE_URL", "http://mpcai.mpc.mil.tw:1234/v1"))
    monkeypatch.setenv("LM_STUDIO_MODEL", os.getenv("LM_STUDIO_MODEL", "gemma-4"))

    llm = get_chat_model()
    response = llm.invoke("請只回覆兩個中文字：正常")
    text = getattr(response, "content", response)
    text = str(text or "").strip()

    assert "LMStudioChatModel" in repr(llm)
    assert text

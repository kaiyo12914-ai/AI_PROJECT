import os
from types import SimpleNamespace

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes import views


class _FakeConversation:
    def __init__(self, title, cid=7):
        self.id = cid
        self.title = title
        self.saved = False

    def save(self, update_fields=None):
        self.saved = True
        self.update_fields = list(update_fields or [])


def test_suggest_conversation_title_uses_question_text():
    out = views._suggest_conversation_title("  何謂巨額採購？\n請說明定義  ", 7)
    assert out.startswith("何謂巨額採購")
    assert "\n" not in out
    assert len(out) <= 60


def test_maybe_update_conversation_title_replaces_default_title():
    conv = _FakeConversation("New Chat", 11)
    out = views._maybe_update_conversation_title(conv, "巨額採購的定義與門檻為何？")
    assert out.startswith("巨額採購的定義與門檻")
    assert conv.saved is True
    assert conv.title == out


def test_maybe_update_conversation_title_preserves_custom_title():
    conv = _FakeConversation("採購計畫討論", 12)
    out = views._maybe_update_conversation_title(conv, "這個問題不應覆蓋使用者自訂標題")
    assert out == "採購計畫討論"
    assert conv.saved is False

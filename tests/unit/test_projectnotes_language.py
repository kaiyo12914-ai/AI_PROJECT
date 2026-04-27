from webapps.projectnotes.lang_guard import contains_cjk, is_zh_dominant, prefer_traditional_chinese


def test_contains_cjk_happy_path():
    assert contains_cjk("這是中文") is True


def test_contains_cjk_boundary_empty():
    assert contains_cjk("") is False


def test_is_zh_dominant_happy_path():
    assert is_zh_dominant("這是一段中文說明，保留 AI 名詞") is True


def test_is_zh_dominant_boundary_mixed_but_english_heavy():
    assert is_zh_dominant("AI models can improve productivity in many tasks") is False


def test_prefer_traditional_chinese_error_fallback_non_cjk():
    fallback = "依據已選來源，整理如下：1. 範例內容。"
    assert prefer_traditional_chinese("This is English only.", fallback) == fallback
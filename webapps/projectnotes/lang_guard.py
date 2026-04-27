import re


def contains_cjk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(re.search(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]", t))


def is_zh_dominant(text: str, min_ratio: float = 0.35) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    cjk_count = len(re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]", t))
    latin_count = len(re.findall(r"[A-Za-z]", t))
    if cjk_count <= 0:
        return False
    if latin_count <= 0:
        return True
    ratio = cjk_count / max(1, cjk_count + latin_count)
    return ratio >= min_ratio


def prefer_traditional_chinese(answer: str, fallback: str) -> str:
    ans = (answer or "").strip()
    fb = (fallback or "").strip()
    if not ans:
        return fb
    if is_zh_dominant(ans):
        return ans
    if is_zh_dominant(fb):
        return fb
    if contains_cjk(ans):
        return ans
    return fb or ans

from __future__ import annotations

from .transcript_parser import TranscriptParseError


def _pick_title(text: str, index: int) -> str:
    t = (text or "").strip()
    if not t:
        return f"Chapter {index}"
    if len(t) <= 30:
        return t
    return t[:30].rstrip() + "..."


def _pick_summary(text: str) -> str:
    t = (text or "").strip()
    if len(t) <= 120:
        return t
    return t[:120].rstrip() + "..."


def generate_chapters_rule_based(
    cues: list[dict],
    *,
    interval_seconds: int = 180,
    max_chars_per_chapter: int = 300,
) -> list[dict]:
    if not cues:
        raise TranscriptParseError("Transcript is empty.")
    if interval_seconds <= 0:
        raise TranscriptParseError("interval_seconds must be > 0.")
    if max_chars_per_chapter <= 0:
        raise TranscriptParseError("max_chars_per_chapter must be > 0.")

    chapters: list[dict] = []
    chapter_start = None
    chapter_end = None
    texts: list[str] = []
    total_chars = 0

    def flush():
        nonlocal chapter_start, chapter_end, texts, total_chars
        if chapter_start is None or chapter_end is None:
            return
        merged = " ".join([x for x in texts if x]).strip()
        if not merged:
            return
        idx = len(chapters) + 1
        chapters.append(
            {
                "order_index": idx,
                "title": _pick_title(merged, idx),
                "summary": _pick_summary(merged),
                "start_seconds": int(chapter_start),
                "end_seconds": int(chapter_end),
            }
        )
        chapter_start = None
        chapter_end = None
        texts = []
        total_chars = 0

    for cue in cues:
        start = int(cue.get("start_seconds") or 0)
        end = int(cue.get("end_seconds") or start)
        text = str(cue.get("text") or "").strip()
        if end < start:
            raise TranscriptParseError("end_seconds must be >= start_seconds.")
        if not text:
            continue

        if chapter_start is None:
            chapter_start = start
            chapter_end = end
            texts = [text]
            total_chars = len(text)
            continue

        span = end - chapter_start
        next_chars = total_chars + len(text)
        heading_trigger = text.startswith("#") or text.startswith("【")
        need_new = span >= interval_seconds or next_chars >= max_chars_per_chapter or heading_trigger

        if need_new:
            flush()
            chapter_start = start
            chapter_end = end
            texts = [text]
            total_chars = len(text)
        else:
            chapter_end = end
            texts.append(text)
            total_chars = next_chars

    flush()
    if not chapters:
        raise TranscriptParseError("Unable to generate chapters.")
    return chapters

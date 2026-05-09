from __future__ import annotations

import re


class TranscriptParseError(ValueError):
    pass


def parse_time_to_seconds(raw: str) -> int:
    text = (raw or "").strip().replace(",", ".")
    m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$", text)
    if not m:
        raise TranscriptParseError(f"Invalid time format: {raw}")
    hh, mm, ss, ms = m.groups()
    h = int(hh)
    m_ = int(mm)
    s = int(ss)
    if m_ >= 60 or s >= 60:
        raise TranscriptParseError(f"Invalid time value: {raw}")
    return h * 3600 + m_ * 60 + s


def parse_txt_transcript(text: str) -> list[dict]:
    content = (text or "").strip()
    if not content:
        raise TranscriptParseError("Transcript is empty.")
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if not lines:
        raise TranscriptParseError("Transcript is empty.")
    return [{"start_seconds": 0, "end_seconds": 0, "text": " ".join(lines)}]


def _parse_timed_blocks(text: str, *, is_vtt: bool) -> list[dict]:
    content = (text or "").strip()
    if not content:
        raise TranscriptParseError("Transcript is empty.")

    raw_blocks = re.split(r"\r?\n\r?\n+", content)
    cues: list[dict] = []
    for block in raw_blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if is_vtt and lines[0].upper() == "WEBVTT":
            continue

        idx = 0
        if re.match(r"^\d+$", lines[0]):
            idx = 1
        if idx >= len(lines):
            continue

        time_line = lines[idx]
        if "-->" not in time_line:
            if is_vtt and lines[0].upper().startswith("NOTE"):
                continue
            raise TranscriptParseError(f"Missing time range line: {time_line}")
        parts = [x.strip() for x in time_line.split("-->")]
        if len(parts) != 2:
            raise TranscriptParseError(f"Invalid time range line: {time_line}")
        start_s = parse_time_to_seconds(parts[0])
        end_s = parse_time_to_seconds(parts[1].split(" ")[0])
        if end_s < start_s:
            raise TranscriptParseError("end_seconds must be >= start_seconds.")

        text_lines = lines[idx + 1 :]
        cue_text = " ".join(text_lines).strip()
        if not cue_text:
            continue
        cues.append(
            {
                "start_seconds": start_s,
                "end_seconds": end_s,
                "text": cue_text,
            }
        )

    if not cues:
        raise TranscriptParseError("No valid cues found.")
    return cues


def parse_srt_transcript(text: str) -> list[dict]:
    return _parse_timed_blocks(text, is_vtt=False)


def parse_vtt_transcript(text: str) -> list[dict]:
    return _parse_timed_blocks(text, is_vtt=True)

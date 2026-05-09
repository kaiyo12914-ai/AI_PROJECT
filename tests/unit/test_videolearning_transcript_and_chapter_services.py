import pytest

from webapps.videolearning.services import (
    TranscriptParseError,
    generate_chapters_rule_based,
    parse_srt_transcript,
    parse_txt_transcript,
    parse_vtt_transcript,
)


def test_parse_txt_transcript_success():
    cues = parse_txt_transcript("第一段\n第二段")
    assert len(cues) == 1
    assert cues[0]["start_seconds"] == 0
    assert cues[0]["text"] == "第一段 第二段"


def test_parse_srt_transcript_success():
    srt = """1
00:00:00,000 --> 00:00:05,000
開場介紹

2
00:00:05,000 --> 00:00:10,000
重點說明
"""
    cues = parse_srt_transcript(srt)
    assert len(cues) == 2
    assert cues[0]["start_seconds"] == 0
    assert cues[1]["end_seconds"] == 10


def test_parse_vtt_transcript_success():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:03.000
第一段

00:00:03.000 --> 00:00:08.000
第二段
"""
    cues = parse_vtt_transcript(vtt)
    assert len(cues) == 2
    assert cues[0]["text"] == "第一段"
    assert cues[1]["start_seconds"] == 3


def test_empty_transcript_error():
    with pytest.raises(TranscriptParseError):
        parse_txt_transcript("   ")


def test_chapter_start_end_boundary_error():
    cues = [{"start_seconds": 12, "end_seconds": 10, "text": "bad"}]
    with pytest.raises(TranscriptParseError):
        generate_chapters_rule_based(cues)


def test_invalid_time_format_error():
    srt = """1
00:00:AA,000 --> 00:00:05,000
invalid
"""
    with pytest.raises(TranscriptParseError):
        parse_srt_transcript(srt)

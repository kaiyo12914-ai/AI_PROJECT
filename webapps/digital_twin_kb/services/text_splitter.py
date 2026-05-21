def split_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[dict]:
    paragraphs = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    chunks = []
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 2 <= chunk_size:
            buffer = f"{buffer}\n\n{paragraph}".strip()
            continue
        if buffer:
            chunks.append({"content": buffer, "section_title": _section_title(buffer)})
        buffer = paragraph
        while len(buffer) > chunk_size:
            chunks.append({"content": buffer[:chunk_size], "section_title": _section_title(buffer[:chunk_size])})
            buffer = buffer[max(0, chunk_size - overlap):]
    if buffer:
        chunks.append({"content": buffer, "section_title": _section_title(buffer)})
    return chunks


def _section_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip("# -\t ")
        if 2 <= len(line) <= 80:
            return line[:80]
    return ""

from __future__ import annotations
from dataclasses import dataclass
from typing import List

@dataclass
class Chunk:
    no: int
    text: str

def split_text(text: str, max_chars: int = 1400, overlap: int = 180) -> List[Chunk]:
    t = (text or "").replace("\r\n", "\n").strip()
    if not t:
        return []

    out: List[Chunk] = []
    n = len(t)
    i = 0
    c = 1
    while i < n:
        j = min(i + max_chars, n)
        part = t[i:j].strip()
        if part:
            out.append(Chunk(c, part))
            c += 1
        if j >= n:
            break
        i = max(0, j - overlap)
    return out

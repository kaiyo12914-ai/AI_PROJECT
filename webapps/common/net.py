# webapps/common/net.py
from __future__ import annotations

import os
from typing import Iterable, List
from urllib.parse import urlparse


def _split_no_proxy(v: str) -> List[str]:
    parts = [p.strip() for p in (v or "").split(",")]
    return [p for p in parts if p]


def _normalize_host(h: str) -> str:
    """
    NO_PROXY 建議只放 hostname，不放 scheme、不放 path、不放 port
    支援:
      - http://host:11434 -> host
      - host:11434        -> host
      - host              -> host
    """
    s = (h or "").strip()
    if not s:
        return ""

    # 有 scheme：用 urlparse 取 hostname
    if "://" in s:
        try:
            u = urlparse(s)
            return (u.hostname or "").strip()
        except Exception:
            return s

    # 無 scheme 但有 port：host:port
    # 避免搞壞 IPv6（含冒號），IPv6 通常會長得像 [::1]:11434 或 ::1
    if s.count(":") == 1 and "[" not in s and "]" not in s:
        return s.split(":", 1)[0].strip()

    return s


def ensure_no_proxy(hosts: Iterable[str]) -> str:
    """
    確保 NO_PROXY / no_proxy 包含指定 hosts（逗號分隔）
    - 安全可重複呼叫
    - 會同時寫入 NO_PROXY 與 no_proxy
    - 會合併 NO_PROXY 與 no_proxy 既有值，避免漏掉其中一邊
    - 會把 host:port / url 轉成 hostname，提高命中率
    """
    norm_hosts = [_normalize_host(h) for h in hosts if (h or "").strip()]
    norm_hosts = [h for h in norm_hosts if h]
    if not norm_hosts:
        return os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "") or ""

    cur_all: List[str] = []
    for k in ("NO_PROXY", "no_proxy"):
        cur_all += _split_no_proxy(os.environ.get(k, "") or "")

    items: List[str] = []
    seen = set()
    for x in cur_all + norm_hosts:
        x = (x or "").strip()
        if not x:
            continue
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(x)

    merged = ",".join(items)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged
    return merged

# sync_sqlserver_to_chroma.py
# (MOST STABLE + QUEUE THROTTLE + DBFactory + NO_PROXY + PRECHECK + DB OPEN/CLOSE TIMING
#  + READ-ALL-THEN-CLOSE + DATE RANGE + SEGMENT PROCESS + NIGHT ACCEL
#  + FIX INTERNAL LLM PORT/PROXY PATH THROUGH IIS/HTTP PROXY
#  + ✅ SEGMENT HISTORY: 每跑完一個 --segment-days 區間就 append 一筆 sync_history.jsonl)

from __future__ import annotations

import os
import json
import time
import argparse
from collections import deque
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path
import sys

from dotenv import load_dotenv  # type: ignore
import pyodbc
import chromadb
from chromadb.config import Settings
from langchain_ollama import OllamaEmbeddings


# ============================================================
# Project import (DBFactory)
# ============================================================
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from webapps.database.db_factory import db_connect  # type: ignore


# ============================================================
# Helpers
# ============================================================
def env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d).strip()


def env_int(k: str, d: int) -> int:
    try:
        return int(env(k, str(d)))
    except Exception:
        return d


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rows_to_dicts(cursor: pyodbc.Cursor, rows: list) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    out: List[Dict[str, Any]] = []
    for r in rows:
        d: Dict[str, Any] = {}
        for i, k in enumerate(cols):
            d[k] = r[i]
        out.append(d)
    return out


def validate_since_ymd(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"--since 格式必須為 YYYY-MM-DD，例如 2025-01-03；收到：{s}") from e


def parse_ymd_any(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace("/", "-")
    return validate_since_ymd(s)


def to_ymd(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, datetime):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, date):
        return x.strftime("%Y-%m-%d")

    s = str(x).strip()
    if not s:
        return ""
    if len(s) >= 10:
        s10 = s[:10].replace("/", "-")
        try:
            return validate_since_ymd(s10)
        except Exception:
            return ""
    return ""


def coalesce_dt(a: Any, b: Any) -> Any:
    return a if a not in (None, "") else b


def parse_debug_one(s: str) -> Tuple[str, str]:
    s = (s or "").strip()
    if not s:
        return "", ""
    if not s.startswith("cmqna_"):
        return "", ""
    parts = s.split("_", 2)
    if len(parts) != 3:
        return "", ""
    return parts[1].strip(), parts[2].strip()


def pick_field(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\x00", " ")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")
    return s.strip()


def looks_like_gateway_timeout(err: Exception) -> bool:
    msg = (str(err) or "").lower()
    keywords = [
        "gateway timeout",
        "timed out",
        "timeout",
        "read timeout",
        "bad gateway",
        "502",
        "503",
        "504",
        "server error",
        "status code: 500",
        "status code 500",
        "internal server error",
    ]
    return any(k in msg for k in keywords)


# ============================================================
# Normalize internal LLM base url to scheme://host:port
# (env key remains OLLAMA_BASE_URL for compatibility with your infra)
# ============================================================
def normalize_llm_base_url(raw: str, *, default_port: int = 11434) -> str:
    raw = (raw or "").strip()
    if not raw:
        return f"http://127.0.0.1:{default_port}"

    try:
        u = urlparse(raw)
        scheme = (u.scheme or "http").strip()
        host = (u.hostname or "127.0.0.1").strip()
        port = u.port or default_port
        return f"{scheme}://{host}:{port}"
    except Exception as e:
        print(f"[WARN] normalize_llm_base_url failed raw={raw} err={e}; fallback 127.0.0.1:{default_port}")
        return f"http://127.0.0.1:{default_port}"


# ============================================================
# Proxy / NO_PROXY Helpers
# ============================================================
def _split_csv(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _merge_no_proxy(items: List[str]) -> str:
    existing = _split_csv(os.getenv("NO_PROXY", "")) + _split_csv(os.getenv("no_proxy", ""))
    seen = set()
    merged: List[str] = []
    for x in existing + items:
        if not x:
            continue
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(x)
    return ",".join(merged)


def _extract_host_from_url(base_url: str) -> str:
    try:
        u = urlparse(base_url or "")
        return (u.hostname or "").strip()
    except Exception:
        return ""


def ensure_no_proxy_for_llm_base_url(base_url: str) -> None:
    """
    Ensure NO_PROXY/no_proxy includes internal LLM host (and common internal networks),
    so requests/httpx/langchain won't route internal calls through corporate proxy.

    NOTE: env key is still 'OLLAMA_BASE_URL' (legacy / infra compatibility),
    but this helper is provider-agnostic.
    """
    base_url = normalize_llm_base_url(base_url)
    host = _extract_host_from_url(base_url)

    defaults = [
        "localhost", "127.0.0.1", "::1",
        "mpcai.mpc.mil.tw",  # ✅ 必須 bypass proxy
    ]
    if host:
        defaults.append(host)

    internal_prefixes = [
        "10.", "192.168.",
        "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        ".local",
        ".internal",
    ]

    extra = _split_csv(os.getenv("NO_PROXY_EXTRA", ""))
    merged = _merge_no_proxy(defaults + internal_prefixes + extra)

    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def disable_all_proxy_env() -> None:
    for k in [
        "HTTP_PROXY", "http_proxy",
        "HTTPS_PROXY", "https_proxy",
        "ALL_PROXY", "all_proxy",
        "REQUESTS_CA_BUNDLE",
    ]:
        os.environ.pop(k, None)


def force_direct_internal_llm_only() -> None:
    """
    只針對「避免內部 LLM 走 proxy」做最硬的保險：
    - 保留你整體環境的 proxy 也可以，但本 process 先清掉常見 proxy env
    - NO_PROXY 仍然照樣保留/補齊
    """
    for k in [
        "HTTP_PROXY", "http_proxy",
        "HTTPS_PROXY", "https_proxy",
        "ALL_PROXY", "all_proxy",
    ]:
        os.environ.pop(k, None)


# ============================================================
# Night accel helpers
# ============================================================
def parse_hhmm(s: str) -> Tuple[int, int]:
    s = (s or "").strip()
    if not s:
        raise ValueError("time must be HH:MM")
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError("time must be HH:MM")
    hh = int(parts[0]); mm = int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("time must be HH:MM in 00:00~23:59")
    return hh, mm


def is_time_in_window(now: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    sh, sm = parse_hhmm(start_hhmm)
    eh, em = parse_hhmm(end_hhmm)
    t = now.time()
    start_t = datetime(now.year, now.month, now.day, sh, sm).time()
    end_t = datetime(now.year, now.month, now.day, eh, em).time()

    if start_t <= end_t:
        return start_t <= t <= end_t
    return (t >= start_t) or (t <= end_t)


def apply_night_overrides_if_needed(
    *,
    enable: bool,
    start: str,
    end: str,
    night_upsert_batch: int,
    night_rate_limit_ms: int,
    night_queue_max: int,
    night_embed_batch: int,
) -> Dict[str, Any]:
    now = datetime.now()
    active = bool(enable and is_time_in_window(now, start, end))
    out = {"night_active": active}
    if not active:
        return out

    if night_embed_batch and night_embed_batch > 0:
        os.environ["OLLAMA_EMBED_BATCH"] = str(int(night_embed_batch))

    out.update({
        "upsert_batch": night_upsert_batch,
        "rate_limit_ms": night_rate_limit_ms,
        "queue_max": night_queue_max,
        "embed_batch": night_embed_batch,
        "night_window": f"{start}~{end}",
    })
    return out


# ============================================================
# Embeddings
# ============================================================
def langchain_ollama_embed(
    texts: List[str],
    *,
    base_url: str,
    model: str,
    timeout_sec: int,
    batch_size: int,
    max_retries: int,
) -> List[List[float]]:
    _ = timeout_sec

    base_url = normalize_llm_base_url(base_url)
    ensure_no_proxy_for_llm_base_url(base_url)

    # NOTE: this is embedding provider used by your current pipeline
    emb = OllamaEmbeddings(model=model, base_url=base_url)

    vectors: List[List[float]] = []
    i = 0

    while i < len(texts):
        cur = texts[i: i + batch_size]
        last_err: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                vecs = emb.embed_documents(cur)
                if len(vecs) != len(cur):
                    raise RuntimeError(f"Embedding count mismatch: got {len(vecs)} expected {len(cur)}")
                vectors.extend(vecs)
                last_err = None
                break
            except Exception as e:
                last_err = e
                sleep_s = min(2 ** attempt, 12)
                print(f"[WARN] embed failed attempt={attempt+1}/{max_retries+1} batch={len(cur)} err={e} -> sleep {sleep_s}s")
                time.sleep(sleep_s)

                if attempt == max_retries and batch_size > 1:
                    new_bs = max(1, batch_size // 2)
                    if new_bs == batch_size:
                        new_bs = max(1, batch_size - 1)
                    batch_size = new_bs
                    print(f"[WARN] reduce embed batch_size -> {batch_size} (retry same index)")
                    break

        if last_err is not None and batch_size == 1:
            preview = (cur[0] or "")[:160].replace("\n", " ")
            raise RuntimeError(f"Embedding failed even for single item. preview='{preview}'") from last_err

        if last_err is None:
            i += len(cur)

    return vectors


# ============================================================
# Chroma Index
# ============================================================
class ChromaIndex:
    def __init__(self) -> None:
        self.chroma_dir = env("RAG_CHROMA_DIR", r"d:\AI\AI_TOOLS\chroma\rag")
        self.collection_name = env("RAG_CHROMA_COLLECTION", "cm_qna")
        os.makedirs(self.chroma_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=self.chroma_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # env key kept (compat): OLLAMA_BASE_URL / OLLAMA_EMBED_MODEL
        self.llm_url = normalize_llm_base_url(env("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
        self.embed_model = env("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.embed_timeout = env_int("OLLAMA_TIMEOUT_SEC", 240)
        self.embed_batch = env_int("OLLAMA_EMBED_BATCH", 8)
        self.embed_retry = env_int("OLLAMA_RETRY", 5)

        ensure_no_proxy_for_llm_base_url(self.llm_url)
        print(f"[sync] ChromaIndex.llm_url={self.llm_url}")

    def upsert(
        self,
        ids: List[str],
        texts: List[str],
        metas: List[Dict[str, Any]],
        *,
        skip_bad: bool,
        bad_log_path: str,
    ) -> None:
        if not ids:
            return
        if not (len(ids) == len(texts) == len(metas)):
            raise ValueError("ids/texts/metas 長度不一致")

        safe_texts = [(t if (t and t.strip()) else " ") for t in texts]

        try:
            t0 = time.monotonic()
            embs = langchain_ollama_embed(
                safe_texts,
                base_url=self.llm_url,
                model=self.embed_model,
                timeout_sec=self.embed_timeout,
                batch_size=self.embed_batch,
                max_retries=self.embed_retry,
            )
            t1 = time.monotonic()
            self.col.upsert(
                ids=ids,
                embeddings=embs,
                documents=safe_texts,
                metadatas=metas,
            )
            t2 = time.monotonic()
            print(f"[perf] embed_sec={(t1-t0):.3f} upsert_sec={(t2-t1):.3f} total_sec={(t2-t0):.3f} batch={len(ids)} embed_batch={self.embed_batch}")
        except Exception as e:
            print(f"[ERROR] batch embedding/upsert failed size={len(ids)} err={e}")
            if not skip_bad:
                raise
            os.makedirs(os.path.dirname(bad_log_path), exist_ok=True)
            with open(bad_log_path, "a", encoding="utf-8") as f:
                for _id, _txt, _meta in zip(ids, safe_texts, metas):
                    f.write(json.dumps({
                        "id": _id,
                        "meta": _meta,
                        "text_preview": (_txt or "")[:240],
                        "ts": now_str(),
                        "err": str(e),
                    }, ensure_ascii=False) + "\n")
            print(f"[WARN] batch skipped; logged to {bad_log_path}")


# ============================================================
# SQL Server connection (DBFactory)
# ============================================================
def get_sqlserver_conn() -> pyodbc.Connection:
    return db_connect("sqlserver")


# ============================================================
# Preflight: write test
# ============================================================
def preflight_write_check(chroma_dir: str) -> None:
    os.makedirs(chroma_dir, exist_ok=True)
    probe = os.path.join(chroma_dir, f".write_probe_{int(time.time())}.tmp")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok\n")
        os.remove(probe)
    except Exception as e:
        raise RuntimeError(
            f"Chroma 目錄不可寫：{chroma_dir}\n"
            f"請檢查：資料夾權限/是否唯讀/是否被同步或防毒鎖住\n"
            f"err={e}"
        ) from e


# ============================================================
# Date range segmentation
# ============================================================
def iter_segments(from_ymd: str, to_ymd: str, segment_days: int) -> List[Tuple[str, str]]:
    f = datetime.strptime(from_ymd, "%Y-%m-%d").date()
    t = datetime.strptime(to_ymd, "%Y-%m-%d").date()
    if f > t:
        raise ValueError(f"--from-date 必須 <= --to-date (got {from_ymd} > {to_ymd})")

    if segment_days <= 0:
        return [(from_ymd, to_ymd)]

    out: List[Tuple[str, str]] = []
    cur = f
    while cur <= t:
        seg_end = min(t, cur + timedelta(days=segment_days - 1))
        out.append((cur.strftime("%Y-%m-%d"), seg_end.strftime("%Y-%m-%d")))
        cur = seg_end + timedelta(days=1)
    return out


# ============================================================
# Main
# ============================================================
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Sync SQLServer view -> Chroma (read-all-then-close DB, date range + segments, night accel)"
    )

    ap.add_argument("--view", default=env("SQL_SERVER_RAG_VIEW", "dbo.view_rag_cm_qna"), help="抽取視圖名稱")
    ap.add_argument("--limit", type=int, default=0, help="最多同步幾筆（0=不限；套用在整體）")

    ap.add_argument("--fetch-size", type=int, default=int(env("SQL_SERVER_FETCH_SIZE", "200")), help="cursor.fetchmany size")
    ap.add_argument("--upsert-batch", type=int, default=int(env("SQL_SERVER_UPSERT_BATCH", "50")), help="每批 upsert 幾筆")
    ap.add_argument("--text-max-chars", type=int, default=int(env("TEXT_MAX_CHARS", "1500")), help="embedding text 最長字元")
    ap.add_argument("--skip-bad", action="store_true", help="遇到批次仍失敗：跳過並記錄（不中斷）")

    ap.add_argument("--rate-limit-ms", type=int, default=int(env("EMBED_RATE_LIMIT_MS", "350")), help="每次 upsert 後 sleep 幾毫秒")
    ap.add_argument("--burst-sleep-ms", type=int, default=int(env("EMBED_BURST_SLEEP_MS", "1200")), help="遇到 timeout 類錯誤時額外 sleep")
    ap.add_argument("--queue-max", type=int, default=int(env("EMBED_QUEUE_MAX", "500")), help="queue 最大累積筆數")
    ap.add_argument("--timeout-retry", type=int, default=int(env("EMBED_TIMEOUT_RETRY", "15")), help="timeout 類錯誤額外重試次數")

    ap.add_argument("--disable-proxy", action="store_true", help="移除 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY（整個程式都不走 proxy）")

    # ✅ 只針對 internal LLM 強制不要走 proxy（預設啟用）
    ap.add_argument("--no-force-direct-ollama", dest="force_direct_ollama", action="store_false", help="關閉『內部 LLM 強制直連（清 proxy env）』")
    ap.set_defaults(force_direct_ollama=True)

    ap.add_argument("--no-preflight-write-check", dest="preflight_write_check", action="store_false", help="關閉啟動前寫入測試")
    ap.set_defaults(preflight_write_check=True)

    ap.add_argument("--no-read-uncommitted", dest="read_uncommitted", action="store_false", help="關閉 READ UNCOMMITTED")
    ap.set_defaults(read_uncommitted=True)

    ap.add_argument("--since", default="", help="只同步 COALESCE(Dte_Verify,Dte_Finish) > since（YYYY-MM-DD）")
    ap.add_argument("--use-last-sync", action="store_true", help="使用 last_sync.txt 當 since")
    ap.add_argument("--no-save-last-sync", action="store_true", help="不同步寫回 last_sync.txt（除錯用）")
    ap.add_argument("--debug-one", default="", help="只同步指定 doc_id（cmqna_{CaseID}_{ItemNo}）")

    ap.add_argument("--from-date", default="", help="區間起日（YYYY-MM-DD 或 YYYY/MM/DD）")
    ap.add_argument("--to-date", default="", help="區間迄日（YYYY-MM-DD 或 YYYY/MM/DD）")
    ap.add_argument("--segment-days", type=int, default=0, help="把日期區間切段處理（例如 7=每7天一段；0=不切段）")

    ap.add_argument("--night-accel", action="store_true", help="啟用夜間加速")
    ap.add_argument("--night-start", default=env("NIGHT_START", "22:00"))
    ap.add_argument("--night-end", default=env("NIGHT_END", "06:00"))
    ap.add_argument("--night-upsert-batch", type=int, default=env_int("NIGHT_UPSERT_BATCH", 64))
    ap.add_argument("--night-rate-limit-ms", type=int, default=env_int("NIGHT_RATE_LIMIT_MS", 0))
    ap.add_argument("--night-queue-max", type=int, default=env_int("NIGHT_QUEUE_MAX", 2000))
    ap.add_argument("--night-embed-batch", type=int, default=env_int("NIGHT_EMBED_BATCH", 64))

    args = ap.parse_args()

    load_dotenv(override=False)

    # 1) normalize base url first (env key kept for compatibility)
    fixed_base = normalize_llm_base_url(env("OLLAMA_BASE_URL", "http://127.0.0.1:11434"), default_port=11434)
    os.environ["OLLAMA_BASE_URL"] = fixed_base

    # 2) proxy strategy
    if args.disable_proxy:
        disable_all_proxy_env()
    elif args.force_direct_ollama:
        # ✅ 只為了避免內部 LLM 走 proxy（IIS/HTTP proxy 環境常見）
        force_direct_internal_llm_only()

    # 3) no_proxy ensure
    ensure_no_proxy_for_llm_base_url(fixed_base)

    print(f"[sync] OLLAMA_BASE_URL(fixed)={fixed_base}")
    print(f"[sync] force_direct_internal_llm={args.force_direct_ollama} disable_proxy={args.disable_proxy}")
    print(f"[sync] NO_PROXY={os.getenv('NO_PROXY','')}")

    chroma_dir = env("RAG_CHROMA_DIR", r"d:\AI\AI_TOOLS\chroma\rag")
    last_sync_file = os.path.join(chroma_dir, "last_sync.txt")
    bad_log_file = os.path.join(chroma_dir, "bad_rows.jsonl")

    # ✅ NEW: segment history (append-only)
    history_file = os.path.join(chroma_dir, "sync_history.jsonl")

    def append_history(rec: Dict[str, Any]) -> None:
        os.makedirs(chroma_dir, exist_ok=True)
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if args.preflight_write_check:
        preflight_write_check(chroma_dir)
        print(f"[preflight] chroma_dir writable OK: {chroma_dir}")

    dbg_caseid, dbg_itemno = parse_debug_one(args.debug_one)

    from_ymd = parse_ymd_any(args.from_date) if args.from_date else ""
    to_ymd = parse_ymd_any(args.to_date) if args.to_date else ""
    since = validate_since_ymd(args.since)

    if args.use_last_sync and not since and not args.debug_one and (not from_ymd and not to_ymd):
        try:
            raw = (open(last_sync_file, "r", encoding="utf-8").read() or "").strip()
            since = validate_since_ymd(raw)
        except Exception:
            since = ""

    if (from_ymd and not to_ymd) or (to_ymd and not from_ymd):
        raise ValueError("--from-date 與 --to-date 必須同時提供")

    night_info = apply_night_overrides_if_needed(
        enable=args.night_accel,
        start=args.night_start,
        end=args.night_end,
        night_upsert_batch=args.night_upsert_batch,
        night_rate_limit_ms=args.night_rate_limit_ms,
        night_queue_max=args.night_queue_max,
        night_embed_batch=args.night_embed_batch,
    )

    effective_upsert_batch = args.upsert_batch
    effective_rate_limit_ms = args.rate_limit_ms
    effective_queue_max = args.queue_max

    if night_info.get("night_active"):
        effective_upsert_batch = int(night_info["upsert_batch"])
        effective_rate_limit_ms = int(night_info["rate_limit_ms"])
        effective_queue_max = int(night_info["queue_max"])
        print(f"[night] ACTIVE {night_info.get('night_window')} -> "
              f"upsert_batch={effective_upsert_batch} rate_limit_ms={effective_rate_limit_ms} "
              f"queue_max={effective_queue_max} embed_batch_env={night_info.get('embed_batch')}")

    print(f"[sync] time={now_str()} view={args.view}")
    if from_ymd:
        print(f"[sync] date_range={from_ymd}~{to_ymd} segment_days={args.segment_days}")
    elif since:
        print(f"[sync] since={since}")
    elif dbg_caseid and dbg_itemno:
        print(f"[sync] debug_one={args.debug_one} -> CaseID={dbg_caseid} ItemNo={dbg_itemno}")

    idx = ChromaIndex()

    total_rows_seen = 0
    total_queued = 0
    total_upserted = 0
    max_updated_seen: Optional[str] = None

    q = deque()

    def consume_queue(force: bool = False) -> None:
        nonlocal total_upserted
        while q and (force or len(q) >= effective_upsert_batch):
            ids: List[str] = []
            texts: List[str] = []
            metas: List[Dict[str, Any]] = []

            n = min(max(1, effective_upsert_batch), len(q))
            for _ in range(n):
                _id, _txt, _meta = q.popleft()
                ids.append(_id); texts.append(_txt); metas.append(_meta)

            retry_left = max(0, int(args.timeout_retry))

            while True:
                try:
                    idx.upsert(ids, texts, metas, skip_bad=args.skip_bad, bad_log_path=bad_log_file)
                    total_upserted += len(ids)
                    print(f"[sync] upserted: +{len(ids)} (rows_seen={total_rows_seen}, upserted={total_upserted}, queue={len(q)})")
                    if effective_rate_limit_ms > 0:
                        time.sleep(effective_rate_limit_ms / 1000.0)
                    break
                except Exception as e:
                    print(f"[ERROR] consume_queue failed size={len(ids)} err={e}")

                    for _id, _txt, _meta in reversed(list(zip(ids, texts, metas))):
                        q.appendleft((_id, _txt, _meta))

                    if looks_like_gateway_timeout(e) and retry_left > 0:
                        retry_left -= 1
                        if args.burst_sleep_ms > 0:
                            time.sleep(args.burst_sleep_ms / 1000.0)
                        else:
                            time.sleep(2.0)

                        ids.clear(); texts.clear(); metas.clear()
                        n2 = min(max(1, effective_upsert_batch), len(q))
                        for _ in range(n2):
                            _id, _txt, _meta = q.popleft()
                            ids.append(_id); texts.append(_txt); metas.append(_meta)
                        continue

                    if args.skip_bad:
                        drop_ids: List[str] = []
                        drop_texts: List[str] = []
                        drop_metas: List[Dict[str, Any]] = []

                        n3 = min(max(1, effective_upsert_batch), len(q))
                        for _ in range(n3):
                            _id, _txt, _meta = q.popleft()
                            drop_ids.append(_id); drop_texts.append(_txt); drop_metas.append(_meta)

                        os.makedirs(os.path.dirname(bad_log_file), exist_ok=True)
                        with open(bad_log_file, "a", encoding="utf-8") as f:
                            for _id, _txt, _meta in zip(drop_ids, drop_texts, drop_metas):
                                f.write(json.dumps({
                                    "id": _id,
                                    "meta": _meta,
                                    "text_preview": (_txt or "")[:240],
                                    "ts": now_str(),
                                    "consume_queue_err": str(e),
                                }, ensure_ascii=False) + "\n")
                        print(f"[WARN] batch dropped due to error; logged to {bad_log_file}")

                        if effective_rate_limit_ms > 0:
                            time.sleep(effective_rate_limit_ms / 1000.0)
                        break

                    raise

    def build_sql_and_params(seg_from: Optional[str], seg_to: Optional[str]) -> Tuple[str, List[Any]]:
        sql = f"SELECT * FROM {args.view}"
        params: List[Any] = []
        where: List[str] = []

        if dbg_caseid and dbg_itemno:
            where.append("CaseID = ? AND ItemNo = ?")
            params.extend([dbg_caseid, dbg_itemno])
        elif seg_from and seg_to:
            where.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) >= CONVERT(date, ?)")
            where.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) <= CONVERT(date, ?)")
            params.extend([seg_from, seg_to])
        elif since:
            where.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) > CONVERT(date, ?)")
            params.append(since)

        if where:
            sql += " WHERE " + " AND ".join(where)

        sql += " ORDER BY COALESCE(Dte_Verify, Dte_Finish) ASC"
        return sql, params

    def fetch_all_then_close(seg_from: Optional[str], seg_to: Optional[str]) -> List[Dict[str, Any]]:
        sql, params = build_sql_and_params(seg_from, seg_to)

        db_connect_begin_ts = now_str()
        db_connect_begin_mon = time.monotonic()
        db_open_ts = ""
        db_open_mon = time.monotonic()

        conn: Optional[pyodbc.Connection] = None
        all_dicts: List[Dict[str, Any]] = []
        try:
            conn = get_sqlserver_conn()

            db_open_ts = now_str()
            db_open_mon = time.monotonic()

            cur = conn.cursor()
            if args.read_uncommitted:
                try:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;")
                except Exception as e:
                    print(f"[WARN] cannot set READ UNCOMMITTED: {e}")

            cur.execute(sql, params)

            while True:
                rows = cur.fetchmany(args.fetch_size)
                if not rows:
                    break
                all_dicts.extend(rows_to_dicts(cur, rows))

                if args.limit and (total_rows_seen + len(all_dicts)) >= args.limit:
                    remain = max(0, args.limit - total_rows_seen)
                    all_dicts = all_dicts[:remain]
                    break

            cur.close()

        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            db_close_ts = now_str()
            db_close_mon = time.monotonic()

        print("========================================================")
        print("[DB] segment fetch & close (avoid long locks)")
        if seg_from and seg_to:
            print(f"[DB] segment={seg_from}~{seg_to}")
        print(f"[DB] connect_begin_ts={db_connect_begin_ts}")
        print(f"[DB] opened_ts={db_open_ts}")
        print(f"[DB] closed_ts={db_close_ts}")
        print(f"[DB] connect_wait_sec={(db_open_mon - db_connect_begin_mon):.3f}")
        print(f"[DB] open_to_close_sec={(db_close_mon - db_open_mon):.3f}")
        print(f"[DB] rows_fetched={len(all_dicts)}")
        print("========================================================")
        return all_dicts

    def process_dicts(dicts: List[Dict[str, Any]]) -> None:
        nonlocal total_rows_seen, total_queued, max_updated_seen
        for d in dicts:
            total_rows_seen += 1
            if args.limit and total_rows_seen > args.limit:
                break

            case_id = str(d.get("CaseID") or "").strip()
            item_no = str(d.get("ItemNo") or "").strip()
            if not case_id or not item_no:
                continue

            doc_id = f"cmqna_{case_id}_{item_no}"
            case_name = str(d.get("CaseName") or "").strip()

            directive_val = pick_field(d, ["CONTENTS", "Case_ITEMS.CONTENTS", "CONTENTS1"])
            status_val = pick_field(d, ["DeptContents", "ITEMS_ASSIGN.DeptContents", "DeptContents1"])

            directive = normalize_text(str(directive_val or ""))
            status = normalize_text(str(status_val or ""))

            dept_factory = str(d.get("DeptCode_Factory") or "").strip()
            dept_code = str(d.get("DeptCode") or "").strip()

            if not directive or not status:
                continue

            dte_finish = d.get("Dte_Finish")
            dte_verify = d.get("Dte_Verify")

            updated_dt = coalesce_dt(dte_verify, dte_finish)
            updated_at = to_ymd(updated_dt)
            if updated_at:
                max_updated_seen = updated_at

            title = f"{case_name} | CaseID={case_id} ItemNo={item_no}"

            body = "\n".join([
                f"案件名稱：{case_name}",
                f"CaseID：{case_id}",
                f"ItemNo：{item_no}",
                f"指裁示：{directive}",
                f"辦況：{status}",
                f"廠別：{dept_factory}",
                f"承辦單位：{dept_code}",
                f"完成日：{dte_finish if dte_finish else ''}",
                f"核定日：{dte_verify if dte_verify else ''}",
            ]).strip()
            body = normalize_text(body)

            text_for_embed = body
            if args.text_max_chars > 0 and len(text_for_embed) > args.text_max_chars:
                text_for_embed = text_for_embed[: args.text_max_chars]

            meta: Dict[str, Any] = {
                "doc_id": doc_id,
                "doc_type": "cm_qna",
                "title": title,
                "updated_at": updated_at,
                "dept": dept_factory,
                "case_id": case_id,
                "item_no": item_no,
                "dept_code": dept_code,
                "chunk_no": item_no,
            }

            q.append((doc_id, text_for_embed, meta))
            total_queued += 1

            if effective_queue_max > 0 and len(q) >= effective_queue_max:
                consume_queue(force=False)
            if len(q) >= max(1, effective_upsert_batch):
                consume_queue(force=False)

        consume_queue(force=True)

    # ---- execute ----
    if from_ymd and to_ymd:
        segments = iter_segments(from_ymd, to_ymd, int(args.segment_days))
        for i, (sf, st) in enumerate(segments, 1):
            print(f"[segment] {i}/{len(segments)} range={sf}~{st}")

            seen0 = total_rows_seen
            queued0 = total_queued
            upsert0 = total_upserted

            dicts = fetch_all_then_close(sf, st)

            if not dicts:
                append_history({
                    "ts": now_str(),
                    "mode": "segment",
                    "segment_index": i,
                    "segment_total": len(segments),
                    "segment_from": sf,
                    "segment_to": st,
                    "rows_fetched": 0,
                    "rows_seen_delta": 0,
                    "queued_delta": 0,
                    "upserted_delta": 0,
                    "segment_max_updated_seen": "",
                    "view": args.view,
                    "collection": env("RAG_CHROMA_COLLECTION", "cm_qna"),
                    "llm_base_url": os.getenv("OLLAMA_BASE_URL", ""),
                    "chroma_dir": chroma_dir,
                })
                continue

            seg_max = ""
            for d in dicts:
                updated_dt = coalesce_dt(d.get("Dte_Verify"), d.get("Dte_Finish"))
                u = to_ymd(updated_dt)
                if u and (not seg_max or u > seg_max):
                    seg_max = u

            process_dicts(dicts)

            append_history({
                "ts": now_str(),
                "mode": "segment",
                "segment_index": i,
                "segment_total": len(segments),
                "segment_from": sf,
                "segment_to": st,
                "rows_fetched": len(dicts),
                "rows_seen_delta": total_rows_seen - seen0,
                "queued_delta": total_queued - queued0,
                "upserted_delta": total_upserted - upsert0,
                "segment_max_updated_seen": seg_max,
                "view": args.view,
                "collection": env("RAG_CHROMA_COLLECTION", "cm_qna"),
                "llm_base_url": os.getenv("OLLAMA_BASE_URL", ""),
                "chroma_dir": chroma_dir,
            })

            if args.limit and total_rows_seen >= args.limit:
                break
    else:
        dicts = fetch_all_then_close(None, None)
        process_dicts(dicts)

    print(f"[sync] done. rows_seen={total_rows_seen}, queued={total_queued}, upserted={total_upserted}, max_updated_seen={max_updated_seen}")

    if (not args.debug_one) and (not from_ymd) and args.use_last_sync and (not args.no_save_last_sync) and max_updated_seen:
        os.makedirs(chroma_dir, exist_ok=True)
        with open(os.path.join(chroma_dir, "last_sync.txt"), "w", encoding="utf-8") as f:
            f.write(max_updated_seen)
        print(f"[sync] wrote last_sync: {os.path.join(chroma_dir, 'last_sync.txt')} = {max_updated_seen}")


if __name__ == "__main__":
    main()




# ============================================================
# 使用範例（含你要的：快速關 DB / 避免 lock）
# ============================================================
# ① 正式環境／遠端 Ollama（穩定優先，DB 很快關）
# python sync_sqlserver_to_chroma.py --use-last-sync --upsert-batch 4 --text-max-chars 800 --rate-limit-ms 150 --burst-sleep-ms 3000 --queue-max 800 --timeout-retry 15 --skip-bad --fail-exit-code
#
# ② 本機 GPU（速度優先，DB 很快關）
# python sync_sqlserver_to_chroma.py --use-last-sync --upsert-batch 32 --text-max-chars 900 --rate-limit-ms 0 --queue-max 2000 --timeout-retry 5 --skip-bad --fail-exit-code
#
# ③ 若 DB 常被鎖：設定 LOCK_TIMEOUT 10 秒（避免卡很久）
# python sync_sqlserver_to_chroma.py --use-last-sync --db-lock-timeout-ms 10000
#
# ④ proxy 很兇：停用 proxy（隻影響本程式）
# python sync_sqlserver_to_chroma.py --disable-proxy --use-last-sync --upsert-batch 4 --text-max-chars 800 --rate-limit-ms 150 --skip-bad --fail-exit-code



# ============================================================
# 使用範例（可貼到操作手冊）
# ============================================================
# ① 最穩定（正式環境／遠端 Ollama，避免 timeout；且若丟資料就讓排程知道）
# python sync_sqlserver_to_chroma.py --use-last-sync --upsert-batch 2 --text-max-chars 800 --rate-limit-ms 500 --burst-sleep-ms 3000 --queue-max 300 --skip-bad --fail-exit-code
#
# ② 全量同步（不限制筆數、不用 last_sync）
# python sync_sqlserver_to_chroma.py
#
# ③ 增量同步（指定日期之後）
# python sync_sqlserver_to_chroma.py --since 2025-01-03
#
# ④ 依上次同步日期增量（正式排程常用）
# python sync_sqlserver_to_chroma.py --use-last-sync
#
# ⑤ 依上次同步但不寫回（測試用）
# python sync_sqlserver_to_chroma.py --use-last-sync --no-save-last-sync
#
# ⑥ 只同步單一案件／項次（Debug 用）
# python sync_sqlserver_to_chroma.py --debug-one cmqna_12345_7 --upsert-batch 1 --text-max-chars 800
#
# ⑦ 限制同步筆數（快速驗證）
# python sync_sqlserver_to_chroma.py --limit 200
#
# ⑧ 高速模式（本機 Ollama、資料量小）
# python sync_sqlserver_to_chroma.py --upsert-batch 20 --text-max-chars 1200 --rate-limit-ms 0
#
# ⑨ 只換資料來源 View
# python sync_sqlserver_to_chroma.py --view dbo.view_rag_cm_qna
#
# ⑩ 一旦寫入失敗就立刻中止（最嚴格）
# python sync_sqlserver_to_chroma.py --fail-fast
#
# ⑪ proxy 環境太兇：直接停用 proxy（隻影響本程式）
# python sync_sqlserver_to_chroma.py --disable-proxy --use-last-sync --upsert-batch 1 --text-max-chars 800 --rate-limit-ms 700 --burst-sleep-ms 4000 --queue-max 200 --skip-bad --fail-exit-code
#
# ⑫ 臨時加入更多 NO_PROXY（不改程式）
# Windows CMD:
#   set NO_PROXY_EXTRA=ollama.internal,10.0.1.23,mpcai.mpc.mil.tw
# PowerShell:
#   $env:NO_PROXY_EXTRA="ollama.internal,10.0.1.23,mpcai.mpc.mil.tw"
#
# ⑬ 關閉啟動前寫入測試（不建議）

# 例如你要：`2025/10/01~2025/11/30` 一次處理完：

# python sync_sqlserver_to_chroma.py --from-date 2025/10/01 --to-date 2025/11/30




# * `[segment] 1/9 range=2025-10-01~2025-10-07`
# * `[DB] segment fetch & close... opened_ts=... closed_ts=... open_to_close_sec=... rows_fetched=...`
# * `[segment] 2/9 range=...`

# ## 3) 切段 + 夜間加速（晚上自動加大 batch、減少 sleep）
# python sync_sqlserver_to_chroma.py --from-date 2025/10/01 --to-date 2025/11/30 --segment-days 7 --night-accel

# 預設夜間 22:00~06:00 生效；可自訂：
# python sync_sqlserver_to_chroma.py --from-date 2025/10/01 --to-date 2025/11/30 --segment-days 7  --night-accel --night-start 18:00 --night-end 07:00 #  --night-upsert-batch 64 --night-rate-limit-ms 0 --night-queue-max 2000 --night-embed-batch 64

# ## 2) 建議用法：切段處理（每 7 天一段）
# python sync_sqlserver_to_chroma.py --from-date 2022/01/01 --to-date 2025/12/30 --segment-days 30
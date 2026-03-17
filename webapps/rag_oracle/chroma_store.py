# webapps/rag_oracle/chroma_store.py
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import chromadb
from chromadb.config import Settings as ChromaSettings
import requests

from . import rag_settings as S


# ============================================================
# requests session (project rule: avoid proxy side-effects)
# ============================================================
_sess = requests.Session()
# ✅ 專案規範：避免喫到環境 proxy 導致 localhost/內網被轉出外網
_sess.trust_env = False


# ---------------------------
# Utils
# ---------------------------
def _as_str_list(texts: Sequence[str]) -> List[str]:
    return [("" if t is None else str(t)).strip() for t in (texts or [])]


def _sleep_backoff(attempt: int, base: float = 0.6, cap: float = 6.0) -> None:
    s = min(base * (2 ** (attempt - 1)), cap)
    time.sleep(s)


def _host_from_url(url: str) -> str:
    try:
        u = urlparse(url)
        return (u.hostname or "").strip().lower()
    except Exception:
        return ""


def _try_post_json(
    url: str,
    payload: Dict[str, Any],
    timeout: Tuple[int, int] = (10, 120),
) -> Tuple[int, str, Any]:
    """
    回傳 (status_code, text_head, json_or_None)
    - text_head: response 前 200 字，方便 debug（避免太長）
    """
    r = _sess.post(url, json=payload, timeout=timeout)
    txt = (r.text or "")
    head = txt[:200]
    try:
        js = r.json()
    except Exception:
        js = None
    return r.status_code, head, js


def _parse_embed_batch_json(js: Any) -> Optional[List[List[float]]]:
    """
    /api/embed 常見回傳格式：
      A) {"embeddings": [[...],[...]]}
      B) {"data":[{"embedding":[...]}, {"embedding":[...]}]}
    """
    if not isinstance(js, dict):
        return None

    embs = js.get("embeddings")
    if isinstance(embs, list) and embs and isinstance(embs[0], list):
        return embs

    data = js.get("data")
    if isinstance(data, list) and data:
        out: List[List[float]] = []
        for it in data:
            if isinstance(it, dict) and isinstance(it.get("embedding"), list) and it["embedding"]:
                out.append(it["embedding"])
            else:
                return None
        return out if out else None

    return None


def _ollama_embed(texts: Sequence[str]) -> List[List[float]]:
    """
    Ollama embeddings（強化版、穩定版）：
    依序嘗試：
      1) POST /api/embed         {"model":..., "input": [..]} -> {"embeddings":[[..],[..]]} 或 {"data":[{"embedding":[..]}]}
      2) POST /api/embeddings    {"model":..., "prompt": "..."} -> {"embedding":[..]} (逐筆)
      3) POST /api/embedding     (某些代理/包裝可能用這個) 同 2 (逐筆)

    ✅ 專案規範：避免 proxy 影響（session.trust_env=False）
    ✅ 失敗時：回傳包含各端點嘗試的 debug_lines（利於定位）
    """
    base_url = (getattr(S, "OLLAMA_BASE_URL", "") or "http://127.0.0.1:11434").rstrip("/")
    model = (getattr(S, "OLLAMA_EMBED_MODEL", "") or "nomic-embed-text").strip()

    clean_texts = _as_str_list(texts)
    if not clean_texts:
        return []

    # 空字串避免 embedding 端點抱怨
    clean_texts = [t if t else " " for t in clean_texts]

    debug_lines: List[str] = []

    # 0) 探測 /api/version（用於 debug）
    try:
        vr = _sess.get(f"{base_url}/api/version", timeout=(5, 10))
        debug_lines.append(f"GET /api/version -> {vr.status_code} {str(vr.text)[:80]}")
    except Exception as e:
        debug_lines.append(f"GET /api/version -> EXC {e}")

    # 1) 新端點：/api/embed（批次）
    for attempt in range(1, 4):
        try:
            st, head, js = _try_post_json(
                f"{base_url}/api/embed",
                {"model": model, "input": clean_texts},
                timeout=(10, 180),
            )
            debug_lines.append(f"POST /api/embed -> {st} head={head!r}")

            if st == 404:
                break
            if st >= 400:
                raise RuntimeError(f"/api/embed HTTP {st}: {head}")

            embs = _parse_embed_batch_json(js)
            if embs is None:
                raise RuntimeError(f"/api/embed JSON 格式異常：{js}")
            if len(embs) != len(clean_texts):
                raise RuntimeError(f"/api/embed 向量數量不符：got={len(embs)} expected={len(clean_texts)}")

            return embs

        except Exception as e:
            debug_lines.append(f"/api/embed attempt={attempt} EXC: {e}")
            if attempt < 3:
                _sleep_backoff(attempt)

    # 2) 舊端點：/api/embeddings（逐筆）
    def _single_prompt(url: str) -> List[List[float]]:
        vectors: List[List[float]] = []
        for idx, t in enumerate(clean_texts, start=1):
            prompt = t if t else " "
            last_err: Optional[Exception] = None

            for attempt in range(1, 4):
                try:
                    st, head, js = _try_post_json(url, {"model": model, "prompt": prompt}, timeout=(10, 180))
                    if st == 404:
                        raise RuntimeError(f"404 Not Found: {url}")
                    if st >= 400:
                        raise RuntimeError(f"HTTP {st}: {head}")

                    if not isinstance(js, dict):
                        raise RuntimeError(f"非 JSON 回應：{head}")

                    emb = js.get("embedding")
                    if not isinstance(emb, list) or not emb:
                        raise RuntimeError(f"JSON 格式異常：{js}")

                    vectors.append(emb)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    if attempt < 3:
                        _sleep_backoff(attempt)

            if last_err is not None:
                raise RuntimeError(
                    f"Ollama embeddings 失敗：idx={idx}/{len(clean_texts)}, model={model}, url={url}, err={last_err}"
                ) from last_err

        return vectors

    try:
        vectors = _single_prompt(f"{base_url}/api/embeddings")
        debug_lines.append("POST /api/embeddings -> OK")
        return vectors
    except Exception as e:
        debug_lines.append(f"/api/embeddings FAIL: {e}")

    # 3) 某些代理/包裝：/api/embedding
    try:
        vectors = _single_prompt(f"{base_url}/api/embedding")
        debug_lines.append("POST /api/embedding -> OK")
        return vectors
    except Exception as e:
        debug_lines.append(f"/api/embedding FAIL: {e}")

    raise RuntimeError(
        "Ollama embeddings 端點皆不可用。請確認 OLLAMA_BASE_URL / 11434 可連線且支援 embedding API。\n"
        + "\n".join(debug_lines)
    )


# ---------------------------
# Chroma Store
# ---------------------------
class ChromaStore:
    def __init__(self) -> None:
        self._client: Optional[chromadb.PersistentClient] = None
        self._col = None

    def _persist_dir(self) -> Path:
        """
        ✅ 專案規範：persist_dir 唯一來源
        - 優先：S.CHROMA_PERSIST_DIR（你已在 rag_settings 統一定義）
        - 相容：舊版若仍有 S.CHROMA_DIR，就 fallback
        """
        v = getattr(S, "CHROMA_PERSIST_DIR", None)
        if v:
            return Path(str(v)).resolve()

        v2 = getattr(S, "CHROMA_DIR", None)
        if v2:
            return Path(str(v2)).resolve()

        raise RuntimeError("[RAG CONFIG ERROR] CHROMA_PERSIST_DIR 未設定（請檢查 .env / rag_settings.py）")

    def _ensure_ready(self) -> None:
        persist_dir = self._persist_dir()
        os.makedirs(persist_dir, exist_ok=True)

        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )

        if self._col is None:
            self._col = self._client.get_or_create_collection(
                name=getattr(S, "CHROMA_COLLECTION", "cm_qna"),
                metadata={"hnsw:space": "cosine"},
            )

    def count(self) -> int:
        self._ensure_ready()
        return int(self._col.count() or 0)

    def get(self, limit: int = 3) -> Dict[str, Any]:
        self._ensure_ready()
        limit = max(1, min(int(limit), 100))
        return self._col.get(limit=limit, include=["documents", "metadatas"])

    def upsert(self, ids: List[str], texts: List[str], metas: List[Dict[str, Any]]) -> None:
        self._ensure_ready()

        ids2 = [str(x).strip() for x in (ids or []) if str(x).strip()]
        texts2 = _as_str_list(texts)
        metas2 = list(metas or [])

        if not ids2:
            return
        if not (len(ids2) == len(texts2) == len(metas2)):
            raise ValueError(f"ids/texts/metas 長度不一致：{len(ids2)}/{len(texts2)}/{len(metas2)}")

        texts2 = [t if t else " " for t in texts2]

        embs = _ollama_embed(texts2)
        if len(embs) != len(ids2):
            raise RuntimeError(f"embedding 數量不符：got={len(embs)} expected={len(ids2)}")

        self._col.upsert(ids=ids2, documents=texts2, embeddings=embs, metadatas=metas2)

    def query(
        self,
        q: str,
        k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        include_documents: bool = True,
    ) -> Dict[str, Any]:
        self._ensure_ready()

        query = (q or "").strip()
        if not query:
            return {"ids": [[]], "metadatas": [[]], "distances": [[]], "documents": [[]]}

        top_k = int(k or 5)
        if top_k <= 0:
            top_k = 5
        top_k = min(top_k, 50)

        qemb = _ollama_embed([query])[0]

        include = ["metadatas", "distances"]
        if include_documents:
            include.append("documents")

        # ✅ Chroma where=None 有些版本會炸：只有 where 有值才帶入
        if where:
            return self._col.query(
                query_embeddings=[qemb],
                n_results=top_k,
                where=where,
                include=include,
            )

        return self._col.query(
            query_embeddings=[qemb],
            n_results=top_k,
            include=include,
        )

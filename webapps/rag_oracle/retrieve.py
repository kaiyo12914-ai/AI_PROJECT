# webapps/rag_oracle/retrieve.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import time
import re
import os
from pathlib import Path

from django.conf import settings

from webapps.rag_oracle.chroma_store import ChromaStore
from webapps.rag_oracle import rag_settings as S

# ✅ Oracle lookup (via DBFactory) — 統一走 db_query_*
from webapps.database.db_factory import db_query_all  # type: ignore


def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _safe_first_2d(x: Any) -> List[Any]:
    """
    Chroma query 回傳常見結構是 2D list：[[...]]
    這裡保守取第一列，取不到就回空 list。
    """
    outer = _safe_list(x)
    if not outer:
        return []
    first = outer[0]
    return first if isinstance(first, list) else []


# ============================================================
# ✅ Chroma persist dir guard (ABS path)
# - IIS/反代環境 CWD 可能改變；若 persist_dir 使用相對路徑 => 讀到空庫 => hits=0
# - 這裡把 rag_settings 內常見 persist 變數統一改成 BASE_DIR 下的絕對路徑
# ============================================================
_PERSIST_KEYS = (
    "CHROMA_PERSIST_DIR",
    "CHROMA_DIR",
    "CHROMA_PATH",
    "PERSIST_DIR",
    "PERSIST_DIRECTORY",
)

_DEFAULT_REL_PERSIST = "data/chroma"


def _as_str(v: Any) -> str:
    return str(v or "").strip()


def _is_abs_path(p: str) -> bool:
    try:
        return Path(p).is_absolute()
    except Exception:
        return False


def _join_base(p: str) -> str:
    base = Path(getattr(settings, "BASE_DIR", Path("."))).resolve()
    return str((base / p).resolve())


def _normalize_persist_dir(p: str) -> str:
    p = _as_str(p)
    if not p:
        return _join_base(_DEFAULT_REL_PERSIST)

    # 若是相對路徑，統一掛到 BASE_DIR 下，避免 CWD 變動
    if not _is_abs_path(p):
        return _join_base(p)

    return str(Path(p).resolve())


def _ensure_chroma_persist_dir() -> str:
    """
    回傳最終 persist_dir，並同步寫回 rag_settings + env。
    """
    # 1) 嘗試從 rag_settings 找到既有 persist 設定
    raw = ""
    for k in _PERSIST_KEYS:
        if hasattr(S, k):
            raw = _as_str(getattr(S, k))
            if raw:
                break

    # 2) 若 settings / env 有明確指定，也允許覆蓋（但仍做 abs）
    env_p = _as_str(os.getenv("CHROMA_PERSIST_DIR"))
    if env_p:
        raw = env_p

    final_dir = _normalize_persist_dir(raw)

    # 3) 同步寫回 rag_settings（不確定你 ChromaStore 用哪個 key，就全寫）
    for k in _PERSIST_KEYS:
        try:
            if hasattr(S, k):
                setattr(S, k, final_dir)
        except Exception:
            pass

    # 4) 同步寫 env（若 ChromaStore / chromadb 有讀 env 的情況）
    os.environ["CHROMA_PERSIST_DIR"] = final_dir

    return final_dir


# ============================================================
# ✅ Factory code -> name cache (Oracle CT_DEPARTMENT)
# ============================================================
_FACTORY_CACHE: Dict[str, Any] = {
    "ts": 0.0,
    "ttl_sec": 3600.0,  # 1 hour
    "map": {},          # code -> name
    "last_err": "",
}


def _load_factory_map_from_oracle() -> Tuple[Dict[str, str], str]:
    """
    Load CT_DEPARTMENT.DEPTCODE_FACTORY -> CT_DEPARTMENT.NAME
    Return (map, err). err=="" means OK.

    ✅ 統一走 DBFactory：db_query_all("oracle", sql)
    """
    sql = """
        SELECT
            TRIM(DEPTCODE_FACTORY) AS CODE,
            TRIM(NAME) AS NAME
        FROM CT_DEPARTMENT
        WHERE DEPTCODE_FACTORY IS NOT NULL
          AND DEPT_STATUS='Y'
    """

    m: Dict[str, str] = {}
    try:
        rows = db_query_all("oracle", sql) or []
        for row in rows:
            if not row:
                continue
            code = row[0] if len(row) > 0 else ""
            name = row[1] if len(row) > 1 else ""
            c = (str(code or "").strip())
            n = (str(name or "").strip())
            if c and n:
                m[c] = n
        return m, ""
    except Exception as e:
        return {}, str(e)


def _get_factory_map() -> Dict[str, str]:
    now = time.time()
    ts = float(_FACTORY_CACHE.get("ts") or 0.0)
    ttl = float(_FACTORY_CACHE.get("ttl_sec") or 3600.0)
    m = _FACTORY_CACHE.get("map") if isinstance(_FACTORY_CACHE.get("map"), dict) else {}

    if m and (now - ts) < ttl:
        return m  # cached OK

    new_map, err = _load_factory_map_from_oracle()
    if new_map:
        _FACTORY_CACHE["map"] = new_map
        _FACTORY_CACHE["ts"] = now
        _FACTORY_CACHE["last_err"] = ""
        return new_map

    _FACTORY_CACHE["ts"] = now
    _FACTORY_CACHE["last_err"] = err
    return m or {}


def _extract_factory_code(meta: Dict[str, Any]) -> str:
    code = (
        (meta.get("dept_factory_code") or "")
        or (meta.get("dept") or "")
        or (meta.get("DeptCode_Factory") or "")
    )
    return str(code or "").strip()


_FACTORY_LINE_RE = re.compile(r"(廠別：)\s*([^\n\r]+)")


def _rewrite_snippet_factory(snippet: str, factory_display: str) -> str:
    s = snippet or ""
    if not s:
        return s

    def _repl(m: re.Match) -> str:
        prefix = m.group(1)
        return f"{prefix}{factory_display}"

    return _FACTORY_LINE_RE.sub(_repl, s, count=1)


# ============================================================
# API: rag_search
# ============================================================
def rag_search(
    q: str,
    k: int | None = None,
    where: Optional[Dict[str, Any]] = None,
    include_documents: bool = True,
) -> Dict[str, Any]:
    """
    Minimal RAG retrieval (UI debug friendly):
    - Query Chroma
    - Return sources (ids + metadatas + distances + optional snippets)
    """
    query = (q or "").strip()
    if not query:
        # ✅ 仍回 debug info（含 persist_dir），方便看目前指向哪個庫
        persist_dir = _ensure_chroma_persist_dir()
        return {
            "ok": True,
            "answer": "",
            "sources": [],
            "top_k": 0,
            "collection": S.CHROMA_COLLECTION,
            "count": 0,
            "persist_dir": persist_dir,
        }

    top_k = int(k if k is not None else getattr(S, "TOP_K", 10) or 10)
    if top_k <= 0:
        top_k = int(getattr(S, "TOP_K", 10) or 10)
    top_k = min(top_k, 50)

    # ✅ 關鍵：先固定 persist_dir（ABS）再初始化 store，避免 IIS/反代 CWD 影響
    persist_dir = _ensure_chroma_persist_dir()

    store = ChromaStore()

    try:
        count = store.count()
        res = store.query(query, k=top_k, where=where, include_documents=include_documents)
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "answer": "（RAG：查詢失敗）",
            "sources": [],
            "top_k": top_k,
            "collection": S.CHROMA_COLLECTION,
            "count": 0,
            "persist_dir": persist_dir,
        }

    ids_0 = _safe_first_2d(res.get("ids"))
    metas_0 = _safe_first_2d(res.get("metadatas"))
    dists_0 = _safe_first_2d(res.get("distances"))
    docs_0 = _safe_first_2d(res.get("documents")) if include_documents else []

    # 取最小共同長度，避免任何一個欄位短於其他造成 IndexError
    n_items = min(
        len(ids_0),
        len(metas_0),
        len(dists_0) if dists_0 else len(ids_0),
        len(docs_0) if docs_0 else len(ids_0),
    )

    # ✅ lazy-load oracle factory map once per request (cached by TTL)
    factory_map = _get_factory_map()

    sources: List[Dict[str, Any]] = []
    for i in range(n_items):
        meta = metas_0[i] or {}
        if not isinstance(meta, dict):
            meta = {}

        # ✅ chunk_no 對齊：優先 chunk_no，否則 fallback item_no 或 CHUNK_NO 欄位名
        chunk_no = (
            meta.get("chunk_no")
            or meta.get("item_no")
            or meta.get(getattr(S, "CHUNK_NO", "CHUNK_NO"), "")
            or ""
        )

        # ✅ factory code -> name
        factory_code = _extract_factory_code(meta)
        factory_name = factory_map.get(factory_code, "") if factory_code else ""
        factory_display = (
            factory_name + (f"（{factory_code}）" if factory_name and factory_code else "")
            or factory_code
        )

        # ✅ enrich metadata for UI / downstream
        if factory_code and "dept_factory_code" not in meta:
            meta["dept_factory_code"] = factory_code
        if factory_name and "dept_factory_name" not in meta:
            meta["dept_factory_name"] = factory_name

        snippet = (docs_0[i] if i < len(docs_0) else "")
        if factory_display:
            snippet = _rewrite_snippet_factory(snippet, factory_display)

        sources.append(
            {
                "id": ids_0[i],
                "distance": dists_0[i] if i < len(dists_0) else None,
                "doc_id": meta.get("doc_id", "") or meta.get(getattr(S, "DOC_ID", "DOC_ID"), ""),
                "doc_type": meta.get("doc_type", "") or meta.get(getattr(S, "DOC_TYPE", "DOC_TYPE"), ""),
                "title": meta.get("title", "") or meta.get(getattr(S, "TITLE", "TITLE"), ""),
                "chunk_no": chunk_no,
                "snippet": snippet,
                "metadata": meta,
                # ✅ optional convenience fields
                "dept_factory_code": factory_code,
                "dept_factory_name": factory_name,
            }
        )

    if not sources:
        # ✅ 這裡把 persist_dir / count 一併提示，方便你一眼判斷是不是打到空庫
        answer = f"（RAG：找不到相似內容；collection={S.CHROMA_COLLECTION}；count={count}；persist={persist_dir}）"
    else:
        lines = [f"（RAG 檢索 Top {len(sources)} / k={top_k}；collection={S.CHROMA_COLLECTION}；count={count}；persist={persist_dir}）"]
        for n, s in enumerate(sources, start=1):
            lines.append(
                f"{n}. {s.get('title') or '（無標題）'}"
                f" | doc_id={s.get('doc_id')}"
                f" | type={s.get('doc_type')}"
                f" | chunk={s.get('chunk_no')}"
                f" | dist={s.get('distance')}"
            )
        answer = "\n".join(lines)

    return {
        "ok": True,
        "answer": answer,
        "sources": sources,
        "top_k": top_k,
        "collection": S.CHROMA_COLLECTION,
        "count": count,
        "persist_dir": persist_dir,
    }

from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
import time

from webapps.rag_oracle import rag_settings as S
from webapps.database.db_factory import db_query_all


_FACTORY_CACHE: Dict[str, Any] = {
    "ts": 0.0,
    "ttl_sec": 3600.0,
    "map": {},
    "last_err": "",
}


def _as_int(v: Any, default: int, *, min_v: Optional[int] = None, max_v: Optional[int] = None) -> int:
    try:
        n = int(v)
    except Exception:
        n = default
    if min_v is not None and n < min_v:
        n = min_v
    if max_v is not None and n > max_v:
        n = max_v
    return n


def _build_keyword_terms(q: str, *, max_terms: int = 12) -> List[str]:
    text = (q or "").strip()
    if not text:
        return []

    pieces = [
        p.strip()
        for p in re.split(r"[\s,，。；;：:、|()（）\[\]{}<>《》「」『』\"'`~!@#$%^&*_+=?！？／\\\-]+", text)
        if p and p.strip()
    ]

    terms: List[str] = []

    def _push(term: str) -> None:
        t = (term or "").strip()
        if not t:
            return
        if len(t) > 32:
            t = t[:32]
        if len(t) < 2:
            return
        if t not in terms:
            terms.append(t)

    for p in pieces:
        _push(p)
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", p))
        if has_cjk and len(p) >= 8:
            step = 2
            size = 4
            for i in range(0, max(1, len(p) - size + 1), step):
                _push(p[i : i + size])
                if len(terms) >= max_terms:
                    break
        if len(terms) >= max_terms:
            break

    if not terms and text:
        _push(text)

    return terms[:max_terms]


def _load_factory_map_from_oracle() -> tuple[Dict[str, str], str]:
    sql = """
        SELECT TRIM(DEPTCODE_FACTORY) AS CODE, TRIM(NAME) AS NAME
        FROM CT_DEPARTMENT
        WHERE DEPTCODE_FACTORY IS NOT NULL
          AND DEPT_STATUS='Y'
    """
    m: Dict[str, str] = {}
    try:
        rows = db_query_all("oracle", sql) or []
        for row in rows:
            code = str((row[0] if len(row) > 0 else "") or "").strip()
            name = str((row[1] if len(row) > 1 else "") or "").strip()
            if code and name:
                m[code] = name
        return m, ""
    except Exception as e:
        return {}, str(e)


def _get_factory_map() -> Dict[str, str]:
    now = time.time()
    ts = float(_FACTORY_CACHE.get("ts") or 0.0)
    ttl = float(_FACTORY_CACHE.get("ttl_sec") or 3600.0)
    m = _FACTORY_CACHE.get("map") if isinstance(_FACTORY_CACHE.get("map"), dict) else {}

    if m and (now - ts) < ttl:
        return m

    new_map, err = _load_factory_map_from_oracle()
    if new_map:
        _FACTORY_CACHE["map"] = new_map
        _FACTORY_CACHE["ts"] = now
        _FACTORY_CACHE["last_err"] = ""
        return new_map

    _FACTORY_CACHE["ts"] = now
    _FACTORY_CACHE["last_err"] = err
    return m or {}


def rag_search(
    q: str,
    k: int | None = None,
    where: Optional[Dict[str, Any]] = None,
    include_documents: bool = True,
) -> Dict[str, Any]:
    query = (q or "").strip()
    if not query:
        return {
            "ok": True,
            "answer": "",
            "sources": [],
            "top_k": 0,
            "source_table": S.PG_RAG_TABLE,
            "count": 0,
            "backend": "postgres",
        }

    top_k = _as_int(k if k is not None else S.TOP_K, S.TOP_K, min_v=1, max_v=50)
    terms = _build_keyword_terms(query, max_terms=12)
    if not terms:
        return {
            "ok": True,
            "answer": "",
            "sources": [],
            "top_k": top_k,
            "source_table": S.PG_RAG_TABLE,
            "count": 0,
            "backend": "postgres",
        }

    where_parts: List[str] = []
    where_params: List[str] = []
    score_parts: List[str] = []
    score_params: List[str] = []

    for t in terms:
        like = f"%{t}%"
        cond = (
            "(directive ILIKE %s OR title ILIKE %s OR case_name ILIKE %s "
            "OR status ILIKE %s OR dept_name ILIKE %s)"
        )
        where_parts.append(cond)
        where_params.extend([like, like, like, like, like])
        score_parts.append(f"(CASE WHEN {cond} THEN 1 ELSE 0 END)")
        score_params.extend([like, like, like, like, like])

    sql = (
        "SELECT doc_id, case_id, item_no, case_name, title, directive, status, dept_name, updated_at, "
        f"({ ' + '.join(score_parts) }) AS hit_score "
        f"FROM {S.PG_RAG_TABLE} "
        f"WHERE {' OR '.join(where_parts)} "
        "ORDER BY hit_score DESC, updated_at DESC NULLS LAST LIMIT %s"
    )

    params = tuple(score_params + where_params + [top_k])

    try:
        rows = db_query_all("postgresql", sql, params) or []
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "answer": "（RAG：查詢失敗）",
            "sources": [],
            "top_k": top_k,
            "source_table": S.PG_RAG_TABLE,
            "count": 0,
            "backend": "postgres",
        }

    factory_map = _get_factory_map()

    sources: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        doc_id = row[0] if len(row) > 0 else ""
        case_id = row[1] if len(row) > 1 else ""
        item_no = row[2] if len(row) > 2 else ""
        case_name = row[3] if len(row) > 3 else ""
        title = row[4] if len(row) > 4 else ""
        directive = row[5] if len(row) > 5 else ""
        status = row[6] if len(row) > 6 else ""
        dept_name = row[7] if len(row) > 7 else ""
        updated_at = row[8] if len(row) > 8 else None
        hit_score = row[9] if len(row) > 9 else 0

        factory_code = ""
        for token in (str(dept_name or "").split(), [str(dept_name or "")]):
            if isinstance(token, list):
                for part in token:
                    part = (part or "").strip()
                    if part in factory_map:
                        factory_code = part
                        break
            if factory_code:
                break

        factory_name = factory_map.get(factory_code, "") if factory_code else ""
        dist = 0.1 + ((idx - 1) * 0.01)

        snippet = ""
        if include_documents:
            snippet = (
                f"會議名稱：{case_name}\n"
                f"指裁示內容：{directive}\n"
                f"辦理情形/擬答：{status}\n"
                f"主辦單位：{dept_name}"
            )

        sources.append(
            {
                "id": str(doc_id or ""),
                "distance": dist,
                "doc_id": str(doc_id or ""),
                "doc_type": "meeting_record",
                "title": str(title or ""),
                "chunk_no": str(item_no or ""),
                "snippet": snippet,
                "metadata": {
                    "case_id": str(case_id or ""),
                    "item_no": str(item_no or ""),
                    "case_name": str(case_name or ""),
                    "title": str(title or ""),
                    "directive": str(directive or ""),
                    "status": str(status or ""),
                    "dept_name": str(dept_name or ""),
                    "updated_at": updated_at.isoformat() if updated_at else "",
                    "hit_score": hit_score,
                    "dept_factory_code": factory_code,
                    "dept_factory_name": factory_name,
                },
                "dept_factory_code": factory_code,
                "dept_factory_name": factory_name,
            }
        )

    if not sources:
        answer = f"（RAG：找不到相似內容；source_table={S.PG_RAG_TABLE}）"
    else:
        lines = [f"（RAG 檢索 Top {len(sources)} / k={top_k}；source_table={S.PG_RAG_TABLE}）"]
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
        "source_table": S.PG_RAG_TABLE,
        "count": len(sources),
        "backend": "postgres",
    }

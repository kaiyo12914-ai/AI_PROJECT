import os
from typing import List, Any, Dict, Optional

import chromadb
from chromadb.config import Settings

from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough


# =========================
# Config
# =========================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434").rstrip("/")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_MODEL = os.getenv("OLLAMA_NAME", "magistral-smal")  # 改成你有的模型

CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "demo_collection")

TOP_K = int(os.getenv("TOP_K", "3"))
TOP_K = max(1, min(TOP_K, 50))
# =========================


def _safe_2d_first(x: Any) -> List[Any]:
    """Chroma 常見回傳 2D list：[[...]]，保守取第一列。"""
    if not isinstance(x, list) or not x:
        return []
    first = x[0]
    return first if isinstance(first, list) else []


def ensure_seed_data(col, emb: OllamaEmbeddings) -> None:
    """第一次跑時灌入示範資料；之後就只做讀取 + RAG。"""
    total = col.count()
    print(f"[CHECK] Chroma count(before) = {total}")

    if total > 0:
        # ✅ 最小持久化檢查：抽 1~3 筆看看（你一跑就知道是不是讀到持久化資料）
        peek = col.get(limit=min(3, total), include=["documents", "metadatas"])
        print("[CHECK] Peek existing documents:")
        ids = peek.get("ids", [])
        metas = peek.get("metadatas", []) or []
        docs = peek.get("documents", []) or []
        for i, _id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            doc = docs[i] if i < len(docs) else ""
            print(f" - id={_id}")
            print("   meta:", meta)
            print("   doc :", str(doc)[:120].replace("\n", " "), "...")
        return

    ids = ["doc1", "doc2", "doc3"]
    docs = [
        "製造中心：設備保養流程與點檢表說明。點檢應包含日檢、週檢、月檢，並記錄異常。",
        "RAG 系統：ChromaDB 是常見的向量資料庫，可用 embeddings 做相似度檢索，搭配 LLM 回答。",
        "Ollama Embedding：使用 nomic-embed-text 可將文字轉向量。可用 embed_documents 與 embed_query。",
    ]
    metas = [
        {"source": "manual", "tag": "maint"},
        {"source": "note", "tag": "rag"},
        {"source": "note", "tag": "ollama"},
    ]

    # ✅ 避免空字串 embedding 造成模型端異常
    docs_safe = [d if (d and d.strip()) else " " for d in docs]

    vectors = emb.embed_documents(docs_safe)
    col.upsert(ids=ids, documents=docs_safe, metadatas=metas, embeddings=vectors)
    print(f"✅ Seeded {len(ids)} docs into Chroma: {CHROMA_DIR} / {COLLECTION_NAME}")

    total2 = col.count()
    print(f"[CHECK] Chroma count(after) = {total2}")

    peek = col.get(limit=min(3, total2), include=["documents", "metadatas"])
    print("[CHECK] Peek documents:")
    for i, _id in enumerate(peek.get("ids", [])):
        meta = (peek.get("metadatas") or [])[i] if peek.get("metadatas") else {}
        doc = (peek.get("documents") or [])[i] if peek.get("documents") else ""
        print(f" - id={_id}")
        print("   meta:", meta)
        print("   doc :", str(doc)[:120].replace("\n", " "), "...")


class ChromaOllamaRetriever(BaseRetriever):
    """
    LangChain Retriever：用 OllamaEmbeddings 產生 query 向量，
    然後呼叫 Chroma collection.query 取回 Documents。

    ✅ 相容新版 langchain-core：run_manager 參數
    """
    collection: Any
    embeddings: Any
    k: int = 3

    def _get_relevant_documents(self, query: str, *, run_manager: Optional[Any] = None) -> List[Document]:
        _ = run_manager

        q = (query or "").strip()
        if not q:
            return []

        qvec = self.embeddings.embed_query(q)
        res = self.collection.query(
            query_embeddings=[qvec],
            n_results=int(self.k),
            include=["documents", "metadatas", "distances"],
        )

        ids = _safe_2d_first(res.get("ids"))
        documents = _safe_2d_first(res.get("documents"))
        metadatas = _safe_2d_first(res.get("metadatas"))
        distances = _safe_2d_first(res.get("distances"))

        # 取共同最小長度，避免欄位不齊爆掉
        n = min(len(ids), len(documents), len(metadatas) if metadatas else len(ids))
        docs: List[Document] = []

        for i in range(n):
            meta: Dict[str, Any] = dict(metadatas[i] or {})
            meta["id"] = ids[i]
            if i < len(distances):
                meta["distance"] = distances[i]
            docs.append(Document(page_content=documents[i] or "", metadata=meta))

        return docs

    async def _aget_relevant_documents(self, query: str, *, run_manager: Optional[Any] = None) -> List[Document]:
        # 目前 embeddings/chroma 都是 sync，async 先包回 sync
        return self._get_relevant_documents(query, run_manager=run_manager)


def format_docs(docs: List[Document]) -> str:
    """把檢索結果格式化成可餵給 LLM 的 context。"""
    if not docs:
        return "（無檢索結果）"
    blocks = []
    for i, d in enumerate(docs, 1):
        src = d.metadata.get("source", "")
        tag = d.metadata.get("tag", "")
        _id = d.metadata.get("id", "")
        dist = d.metadata.get("distance", "")
        header = f"[{i}] id={_id} source={src} tag={tag} distance={dist}"
        blocks.append(header + "\n" + (d.page_content or ""))
    return "\n\n".join(blocks)


def main():
    # 1) Embeddings + Chroma client/collection
    emb = OllamaEmbeddings(model=OLLAMA_EMBED_MODEL, base_url=OLLAMA_BASE_URL)

    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # 2) Seed data if empty + minimal persistence checks
    ensure_seed_data(col, emb)

    # 3) Build Retriever
    retriever = ChromaOllamaRetriever(collection=col, embeddings=emb, k=TOP_K)

    # 4) LLM + Prompt
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是嚴謹的助理。只能根據提供的context回答；若context不足，請明確說不知道並提出你需要的資訊。"),
        ("human", "Context:\n{context}\n\nQuestion:\n{question}\n\n請用繁體中文作答。"),
    ])

    # ✅ 不要用 get_relevant_documents，改用 retriever.invoke
    def retrieve_docs(q: str) -> List[Document]:
        out = retriever.invoke(q)
        return out if isinstance(out, list) else []

    chain = (
        {
            "context": RunnableLambda(retrieve_docs) | RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    # 6) Interactive loop
    print("\n✅ RAG ready. 輸入問題開始查詢（輸入 exit 結束）\n")
    while True:
        q = input("Q> ").strip()
        if not q or q.lower() in ("exit", "quit"):
            break

        try:
            ans = chain.invoke(q)
            print("\nA>\n" + ans + "\n")
        except Exception as e:
            print(f"\n[ERROR] RAG failed: {e}\n")


if __name__ == "__main__":
    main()

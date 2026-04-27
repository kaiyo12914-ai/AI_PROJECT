import os
import chromadb
from chromadb.config import Settings
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

# ====== 你可以改這些 ======
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "demo_collection")
# =========================


def main():
    # 1) Embeddings (LangChain Ollama)
    emb = OllamaEmbeddings(
        model=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
        # client_kwargs={"httpx_args":{"timeout":300.0}}
    )

    
    # 2) Chroma persistent client
    # client = chromadb.PersistentClient(
    #     path=CHROMA_DIR,
    #     settings=Settings(anonymized_telemetry=False)        
    # )
    # col = client.get_or_create_collection(
    #     name=COLLECTION_NAME,
    #     metadata={"hnsw:space": "cosine"},
    # )

    # 3) Prepare documents
    ids = ["doc1", "doc2", "doc3"]
    docs = [
        "製造中心：設備保養流程與點檢表說明。",
        "RAG 系統：ChromaDB 向量資料庫的基本用法。",
        "Ollama Embedding：使用 nomic-embed-text 產生向量。",
    ]
    metas = [
        {"source": "manual", "tag": "maint"},
        {"source": "note", "tag": "rag"},
        {"source": "note", "tag": "ollama"},
    ]

    _docs = []

    # for i in range(0 ,len(docs)):
    #     _docs.append(Document(page_content=docs[i],metadata=metas[i]))

    # vectorstore = Chroma.from_documents(documents=_docs,embedding=emb,persist_directory=CHROMA_DIR)
    
    # 4) Embed -> upsert to Chroma
    vectors = emb.embed_documents(docs)  # List[List[float]]
    # col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vectors)
    print(f"✅ Upserted {len(ids)} docs into Chroma: {CHROMA_DIR} / {COLLECTION_NAME}")

    # ---------------------------------------------------------------------
    # ✅ Minimal persistence checks: col.count() + col.get()
    # ---------------------------------------------------------------------
    total = col.count()
    print(f"\n[CHECK] Chroma count = {total}")

    peek = col.get(
        limit=min(3, total),
        include=["documents", "metadatas"],
    )

    print("[CHECK] Peek documents:")
    for i, _id in enumerate(peek["ids"]):
        print(f" - id={_id}")
        print("   meta:", peek["metadatas"][i])
        doc_preview = (peek["documents"][i] or "")[:120].replace("\n", " ")
        print("   doc :", doc_preview, "...")
    # ---------------------------------------------------------------------

    # 5) Query
    query = "如何用 Ollama 產生 embedding？"
    qvec = emb.embed_query(query)  # List[float]

    res = col.query(
        query_embeddings=[qvec],
        n_results=2,
        include=["documents", "metadatas", "distances"],  # ✅ include 不要放 "ids"
    )

    print("\n=== Query ===")
    print(query)

    print("\n=== Top Results ===")
    for i in range(len(res["ids"][0])):  # ids 仍然會回傳
        _id = res["ids"][0][i]
        _doc = res["documents"][0][i]
        _meta = res["metadatas"][0][i]
        _dist = res["distances"][0][i]
        print(f"\n#{i+1} id={_id} distance={_dist}")
        print("meta:", _meta)
        print("doc :", _doc)


if __name__ == "__main__":
    main()

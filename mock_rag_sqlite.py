import sqlite3
import json
import requests
import os
import sys

def get_env(k, d=""):
    return os.getenv(k, d).strip()

def _ollama_embed(texts, base_url, model):
    try:
        r = requests.post(f"{base_url}/api/embed", json={"model": model, "input": texts}, timeout=60)
        if r.status_code == 200:
            return r.json().get("embeddings")
        # Fallback to /api/embeddings
        embs = []
        for t in texts:
            r2 = requests.post(f"{base_url}/api/embeddings", json={"model": model, "prompt": t}, timeout=60)
            embs.append(r2.json().get("embedding"))
        return embs
    except Exception as e:
        print(f"Embedding Error: {e}")
        return None

def mock_rag_search(q, k=5):
    db_path = r'H:\AI\Django\chroma\rag\chroma.sqlite3'
    base_url = "http://192.168.0.137:11434"
    model = "nomic-embed-text"
    
    print(f"Querying: {q} (k={k})")
    qemb = _ollama_embed([q], base_url, model)
    if not qemb:
        return {"ok": False, "error": "Embedding failed"}
    qvector = qemb[0]
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. 取得所有 embedding
        cursor.execute("SELECT id, vector FROM embeddings")
        rows = cursor.fetchall()
        
        results = []
        for rid, blob in rows:
            # 解析 blob (Chroma 通常存為 float32 list)
            import struct
            # Chroma 向量通常是 float32 (4 bytes per dim)
            dim = len(blob) // 4
            vector = struct.unpack(f'{dim}f', blob)
            
            # 計算 Cosine Similarity (或 Dot Product, 假設已歸一化)
            dot = sum(a*b for a, b in zip(qvector, vector))
            mag1 = sum(a*a for a in qvector)**0.5
            mag2 = sum(a*a for a in vector)**0.5
            score = dot / (mag1 * mag2) if (mag1 * mag2) > 0 else 0
            
            results.append((rid, score))
        
        # 2. 排序並取前 K
        results.sort(key=lambda x: x[1], reverse=True)
        top_ids = [r[0] for r in results[:k]]
        
        # 3. 取得 Document 內容
        sources = []
        for rid in top_ids:
            cursor.execute("SELECT document, metadata FROM embedding_fulltext WHERE id=?", (rid,))
            doc, meta = cursor.fetchone()
            sources.append({
                "id": rid,
                "document": doc,
                "metadata": json.loads(meta) if meta else {},
                "score": results[[r[0] for r in results].index(rid)][1]
            })
            
        conn.close()
        return {"ok": True, "sources": sources, "hits_count": len(sources)}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    res = mock_rag_search("資安", k=3)
    print(json.dumps(res, indent=2, ensure_ascii=False))

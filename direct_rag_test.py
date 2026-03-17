import os
import django

# 設定環境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

from webapps.rag_oracle.retrieve import rag_search

def test_rag():
    q = "資安"
    print(f"--- 執行 RAG 核心直接測試 (Query: {q}) ---")
    try:
        res = rag_search(q, k=10)
        print(f"RAG OK: {res.get('ok')}")
        print(f"Chroma Count: {res.get('count')}")
        print(f"Hits: {len(res.get('sources', []))}")
        print(f"Persist Dir: {res.get('persist_dir')}")
        print(f"Error Msg: {res.get('error')}")
        
        if res.get('sources'):
            print("\n[第一筆結果摘要]")
            print(res.get('sources')[0].get('text', '')[:100])
            
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    test_rag()

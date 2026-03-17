import os
import sys
import time
import requests

# Add project root to sys.path
sys.path.append(r'H:\AI\Django')
os.environ['DJANGO_SETTINGS_MODULE'] = 'webproj.settings'

import django
django.setup()

from webapps.rag_oracle import rag_settings as S
from webapps.rag_oracle.chroma_store import _ollama_embed

def debug_rag_query(q):
    print(f"--- RAG Debug Start ---")
    print(f"Target Persist Dir: {S.CHROMA_PERSIST_DIR}")
    print(f"Target Collection: {S.CHROMA_COLLECTION}")
    
    print(f"1. Testing Ollama Embedding for '{q}'...")
    try:
        t0 = time.time()
        emb = _ollama_embed([q])
        print(f"   Embedding Success in {time.time()-t0:.2f}s (dim={len(emb[0])})")
    except Exception as e:
        print(f"   Embedding FAILED: {e}")
        return

    print(f"2. Initializing ChromaStore and Querying...")
    from webapps.rag_oracle.chroma_store import ChromaStore
    try:
        t0 = time.time()
        store = ChromaStore()
        # Explicit count check
        count = store.count()
        print(f"   Chroma count: {count}")
        
        # Actual query
        res = store.query(q, k=2)
        print(f"   Query Success in {time.time()-t0:.2f}s")
        print(f"   Hits found: {len(res.get('ids', [[]])[0])}")
    except Exception as e:
        print(f"   Chroma Query FAILED: {e}")

if __name__ == "__main__":
    debug_rag_query("資安")

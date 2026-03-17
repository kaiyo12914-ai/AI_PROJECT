import os
import sys
import time

# 精確模擬 Django 環境
os.chdir(r'H:\AI\Django')
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')

import django
django.setup()

from webapps.rag_oracle import rag_settings as S
from webapps.rag_oracle.chroma_store import ChromaStore

print(f"--- RAG Final Test ---")
print(f"Settings.CHROMA_PERSIST_DIR: {S.CHROMA_PERSIST_DIR}")
print(f"Settings.CHROMA_COLLECTION: {S.CHROMA_COLLECTION}")

try:
    print("Initializing ChromaStore...")
    t0 = time.time()
    store = ChromaStore()
    count = store.count()
    print(f"Collection count: {count}")
    
    print("Querying '資安'...")
    res = store.query("資安", k=2)
    print(f"Query took {time.time()-t0:.2f}s")
    print(f"Result OK: {len(res.get('ids', [[]])[0]) > 0}")
    print(f"First result title: {res.get('metadatas', [[]])[0][0].get('title') if res.get('metadatas') else 'N/A'}")
except Exception as e:
    print(f"ERROR: {e}")

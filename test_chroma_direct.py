import os
import django
from django.conf import settings
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings

def test_chroma_direct(path_str):
    print(f"\n--- Testing Chroma Direct: {path_str} ---")
    if not os.path.exists(path_str):
        print("Path does not exist.")
        return
        
    try:
        client = chromadb.PersistentClient(
            path=path_str,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        cols = client.list_collections()
        print(f"Collections found: {[c.name for c in cols]}")
        
        for c_info in cols:
            col = client.get_collection(name=c_info.name)
            print(f"Collection '{c_info.name}' count: {col.count()}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_chroma_direct("H:\\AI\\Django\\chroma")
    test_chroma_direct("H:\\AI\\Django\\chroma\\rag")

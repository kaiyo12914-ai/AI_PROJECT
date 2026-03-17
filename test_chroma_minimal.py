import os
import django
from django.conf import settings
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings

# 設定環境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

def test_chroma_minimal(path_str):
    print(f"\n--- Testing Chroma Minimal: {path_str} ---")
    if not os.path.exists(path_str):
        print("Path does not exist.")
        return
        
    try:
        client = chromadb.PersistentClient(
            path=path_str,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        print("Client initialized.")
        col = client.get_collection(name="cm_qna")
        print(f"Collection 'cm_qna' ready. Count: {col.count()}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_chroma_minimal("H:\\AI\\Django\\chroma\\rag")

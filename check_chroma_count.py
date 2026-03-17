import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

from webapps.rag_oracle.chroma_store import ChromaStore

def check_chroma():
    store = ChromaStore()
    try:
        count = store.count()
        print(f"Chroma Record Count: {count}")
        print(f"Persist Dir: {store._persist_dir()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_chroma()

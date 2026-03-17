import os
import sys
import chromadb
from chromadb.config import Settings

# 設定環境變數供 django 使用
os.environ['DJANGO_SETTINGS_MODULE'] = 'webproj.settings'
sys.path.append('H:\\AI\\Django')

try:
    persist_dir = r'H:\AI\Django\chroma\rag'
    client = chromadb.PersistentClient(path=persist_dir, settings=Settings(anonymized_telemetry=False))
    col_name = 'cm_qna'
    collection = client.get_collection(name=col_name)
    count = collection.count()
    print(f"SUCCESS: Collection '{col_name}' in '{persist_dir}' contains {count} items.")
except Exception as e:
    print(f"FAILED: {e}")

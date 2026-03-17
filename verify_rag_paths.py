import os
import django
from django.conf import settings
from pathlib import Path
import json

# 設定環境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

from webapps.rag_oracle.chroma_store import ChromaStore
from webapps.rag_oracle import rag_settings as S

def test_rag_path(path_label, path_str):
    print(f"\n--- Testing Path: {path_label} ({path_str}) ---")
    if not os.path.exists(path_str):
        print(f"FAILED: Path does not exist.")
        return
    
    # 暫時覆寫 settings 中的路徑
    S.CHROMA_PERSIST_DIR = Path(path_str).resolve()
    
    try:
        store = ChromaStore()
        # 強制重新初始化客戶端
        store._client = None
        store._col = None
        
        count = store.count()
        print(f"SUCCESS: Chroma Record Count = {count}")
        
        # 嘗試簡單查詢
        print("Executing test query for '資安'...")
        res = store.query("資安", k=2)
        hits = len(res.get("ids", [[]])[0])
        print(f"Query Results: {hits} hits.")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    # 測試目前的路徑
    test_rag_path("Current (H:\\AI\\Django\\chroma)", "H:\\AI\\Django\\chroma")
    
    # 測試舊的路徑
    test_rag_path("Old (H:\\AI\\Django\\chroma\\rag)", "H:\\AI\\Django\\chroma\\rag")

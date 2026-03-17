import os
import requests
from pathlib import Path

# 直接從 .env 讀取，不透過 Django
def load_env_manually():
    vars = {}
    with open("H:/AI/Django/.env", "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                vars[k.strip()] = v.strip()
    return vars

def test_ollama_simple():
    env = load_env_manually()
    base_url = env.get("OLLAMA_BASE_URL", "http://192.168.0.137:11434")
    model = env.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    
    print(f"Testing Ollama Embedding: {base_url} with model {model}")
    
    payload = {
        "model": model,
        "input": ["測試文字"]
    }
    
    try:
        start = time.time()
        r = requests.post(f"{base_url}/api/embed", json=payload, timeout=10)
        dur = time.time() - start
        print(f"Status: {r.status_code}, Duration: {dur:.2f}s")
        if r.status_code == 200:
            print("Embedding SUCCESS")
        else:
            print(f"FAILED: {r.text}")
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")

if __name__ == "__main__":
    import time
    test_ollama_simple()

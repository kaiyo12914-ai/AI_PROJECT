import requests
import os
from dotenv import load_dotenv

load_dotenv("H:/AI/Django/.env")
url = os.getenv("OLLAMA_BASE_URL")
print(f"Testing connection to: {url}")
try:
    r = requests.get(f"{url}/api/tags", timeout=5)
    print(f"Status Code: {r.status_code}")
    print(f"Models: {len(r.json().get('models', []))}")
except Exception as e:
    print(f"Connection FAILED: {e}")

import os
import django
import sys

# 載入 Django settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
django.setup()

from django.conf import settings
from webapps.llm.embedding_factory import get_shared_embedding_model, get_shared_embedding_provider, get_shared_embedding_model_name, get_shared_embedding_base_url

print("----- Embedding Settings -----")
print("GLOBAL_EMBEDDING_PROVIDER :", getattr(settings, "GLOBAL_EMBEDDING_PROVIDER", "None"))
print("GLOBAL_EMBEDDING_MODEL    :", getattr(settings, "GLOBAL_EMBEDDING_MODEL", "None"))
print("OLLAMA_BASE_URL           :", getattr(settings, "OLLAMA_BASE_URL", "None"))
print("Resolved Provider         :", get_shared_embedding_provider())
print("Resolved Model Name       :", get_shared_embedding_model_name())
print("Resolved Base URL         :", get_shared_embedding_base_url())
print("------------------------------")

try:
    print("Initializing embedding model...")
    model = get_shared_embedding_model()
    print("Model initialized successfully.")
    
    print("Testing embed_query...")
    vector = model.embed_query("[人事]205廠在職人數")
    print(f"Success! Vector length: {len(vector)}")
except Exception as e:
    print(f"Error testing embedding model: {type(e).__name__}: {e}")

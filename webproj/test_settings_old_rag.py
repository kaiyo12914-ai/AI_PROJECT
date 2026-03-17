from .settings import *
import os

# 覆蓋路徑以指向舊的正確資料夾
_TARGET_DRIVE = "H:" if os.getenv("ENV", "EXT") == "EXT" else "D:"
_PROJECT_ROOT_STR = f"{_TARGET_DRIVE}\\AI\\DJANGO"

# 強制指向 rag 子目錄 (三天前正常的版本)
RAG_CHROMA_DIR = f"{_PROJECT_ROOT_STR}\\chroma\\rag"
CHROMA_PERSIST_DIR = f"{_PROJECT_ROOT_STR}\\chroma\\rag"
CHROMA_DIR = f"{_PROJECT_ROOT_STR}\\chroma\\rag"

# 保留其他
PORTAL_ACL_ENABLED = False
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8001']
MIDDLEWARE = [m for m in MIDDLEWARE if 'CsrfViewMiddleware' not in m]
DEBUG = True

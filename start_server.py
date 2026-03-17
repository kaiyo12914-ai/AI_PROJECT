import os
import sys

ROOT = r'H:\AI\Django'
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')

import django
django.setup()

from django.core.servers.basehttp import run

print("DEBUG: Manually starting server...")
from django.core.handlers.wsgi import WSGIHandler
handler = WSGIHandler()
try:
    # 嘗試手動啟動 WSGI 服務器
    run('0.0.0.0', 8001, handler)
except Exception as e:
    print(f"MANUAL RUN CRASH: {e}")

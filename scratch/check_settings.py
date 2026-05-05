import os, sys
sys.path.append(r'H:\AI\AI_TOOLS')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
import django; django.setup()
from django.conf import settings
print(f"DEBUG={settings.DEBUG}")
print(f"ENV={os.getenv('ENV')}")
print(f"MODEL_TYPE={os.getenv('MODEL_TYPE')}")
print(f"DEV_LOGIN_USER={os.getenv('DEV_LOGIN_USER')}")

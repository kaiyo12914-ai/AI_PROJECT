import os
import sys
sys.path.append(r'H:\AI\AI_TOOLS')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
import django
django.setup()
from django.conf import settings
print("ACL_BACKEND_EFFECTIVE:", getattr(settings, "ACL_BACKEND_EFFECTIVE", None))
print("PORTAL_ACL_BACKEND:", getattr(settings, "PORTAL_ACL_BACKEND", None))

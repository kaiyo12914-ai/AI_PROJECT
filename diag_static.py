import os
import django
from django.conf import settings
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

def diagnostic():
    print(f"--- Static Files Diagnostic ---")
    print(f"BASE_DIR: {settings.BASE_DIR}")
    print(f"STATIC_ROOT: {settings.STATIC_ROOT}")
    print(f"STATICFILES_DIRS: {settings.STATICFILES_DIRS}")
    
    # 檢查路徑是否存在
    for d in settings.STATICFILES_DIRS:
        p = Path(d)
        print(f"Dir {p} exists: {p.exists()}")
    
    sr = Path(settings.STATIC_ROOT)
    print(f"STATIC_ROOT {sr} exists: {sr.exists()}")

    # 檢查 W004 邏輯：STATIC_ROOT 是否在任何 STATICFILES_DIRS 內
    for d in settings.STATICFILES_DIRS:
        try:
            if Path(settings.STATIC_ROOT).is_relative_to(Path(d)):
                print(f"!! CONFLICT: STATIC_ROOT is inside {d}")
        except ValueError:
            pass

if __name__ == "__main__":
    diagnostic()

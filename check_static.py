import os
import django
from django.conf import settings
from django.core.checks import run_checks

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

def check_static():
    print(f"STATIC_ROOT: {settings.STATIC_ROOT}")
    print(f"STATICFILES_DIRS: {settings.STATICFILES_DIRS}")
    print(f"BASE_DIR: {settings.BASE_DIR}")
    
    errors = run_checks()
    for error in errors:
        if "staticfiles.W004" in str(error.id):
            print(f"Found Warning: {error}")

if __name__ == "__main__":
    check_static()

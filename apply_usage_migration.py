import os
import sys

# 切換到專案根目錄
ROOT = r'H:\AI\Django'
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# 設定 Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')

import django
django.setup()

from django.core.management import call_command

if __name__ == "__main__":
    print("--- Starting Migration for Portal ---")
    try:
        print("1. Running makemigrations portal...")
        call_command('makemigrations', 'portal')
        
        print("2. Running migrate portal...")
        call_command('migrate', 'portal')
        
        print("\nSUCCESS: Database schema updated.")
    except Exception as e:
        print(f"\nERROR: {e}")

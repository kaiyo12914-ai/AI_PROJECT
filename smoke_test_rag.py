import os
import sys

# Add project root to sys.path
sys.path.append(r'H:\AI\Django')
os.environ['DJANGO_SETTINGS_MODULE'] = 'webproj.settings'

import django
django.setup()

print("Django setup OK.")

try:
    from webapps.rag_oracle.retrieve import rag_search
    print("Import rag_search OK.")
    
    # Test a simple search
    print("Testing rag_search('資安')...")
    res = rag_search('資安', k=1)
    print(f"Result: {res['ok']}")
    if res['ok']:
        print(f"Hits: {res['count']}")
        print(f"Persist Dir: {res['persist_dir']}")
    else:
        print(f"Error: {res.get('error')}")
except Exception as e:
    print(f"Exception: {e}")

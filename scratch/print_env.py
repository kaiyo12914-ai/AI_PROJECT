import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load django settings so that load_dotenv gets triggered
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django
django.setup()

keys = [
    "ENV",
    "ORACLE_EMP_DB_PROFILE",
    "ORACLE_ENABLED",
    "ORACLE_EMP_ENABLED",
    "MOCK_DB_JSON",
    "ORA_HOST",
    "ORA_PORT",
    "ORA_SERVICE_NAME",
    "ORA_USER",
    "ORA_PASS",
]

print("--- Settings / Environment Variables ---")
for k in keys:
    print(f"{k}: {os.getenv(k)}")

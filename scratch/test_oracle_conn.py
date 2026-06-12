import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapps.database.db_factory import db_connect, load_db_config

print("--- Testing Global Oracle Config ---")
try:
    cfg = load_db_config("oracle")
    print(f"Global Config: host={cfg.ora_host}, port={cfg.ora_port}, service={cfg.ora_service}, user={cfg.ora_user}")
    conn = db_connect("oracle")
    print("SUCCESS: Connected to global Oracle DB!")
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")

print("\n--- Testing MPC Profile Oracle Config ---")
try:
    cfg = load_db_config("oracle", profile="MPC")
    print(f"MPC Profile Config: host={cfg.ora_host}, port={cfg.ora_port}, service={cfg.ora_service}, user={cfg.ora_user}")
    conn = db_connect("oracle", profile="MPC")
    print("SUCCESS: Connected to MPC profile Oracle DB!")
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")

import os
print(f"ENV_GOOGLE_API_KEY_LEN: {len(os.environ.get('GOOGLE_API_KEY', ''))}")

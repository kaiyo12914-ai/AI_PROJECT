import os
print(f"ENV_GEMINI_API_KEY_LEN: {len(os.environ.get('GEMINI_API_KEY', ''))}")

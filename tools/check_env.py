import os
from dotenv import load_dotenv
load_dotenv()
print(f"API_KEY_LEN: {len(os.getenv('GEMINI_API_KEY') or '')}")
print(f"MODEL: {os.getenv('GOOGLE_MODEL')}")

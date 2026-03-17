import requests
try:
    print("Testing connection to OpenAI...")
    r = requests.get('https://api.openai.com/v1/models', timeout=10)
    print(f"Status Code: {r.status_code}")
except Exception as e:
    print(f"Connection Failed: {e}")

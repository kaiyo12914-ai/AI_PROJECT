import os
import sys
from dotenv import load_dotenv

# 強制輸出為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# 設定 Django 環境
sys.path.append('H:/AI/DJANGO')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')

try:
    load_dotenv()
    from langchain_google_genai import ChatGoogleGenerativeAI
    from google.generativeai.types import HarmCategory, HarmBlockThreshold

    # 使用 OpenClaw 設定檔中的 API Key
    api_key = "AIzaSyDD0U8AHoFni90d8FZthWRILOLp1CrMjgg"
    model = os.getenv('GOOGLE_MODEL', 'gemini-flash-latest')

    print(f"Testing Google LLM with OpenClaw API Key (Model: {model})...")
    
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    llm = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        safety_settings=safety_settings,
        timeout=30
    )

    response = llm.invoke("Hi, please confirm you are working correctly by replying 'GOOGLE_OK'.")
    print(f"Response: {response.content}")

except Exception as e:
    print(f"FATAL_ERROR: {str(e)}")
    sys.exit(1)

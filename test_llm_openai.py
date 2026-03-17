import os
import django
import json

# 設定 Django 環境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

from webapps.doc.prompt import build_prompt
from webapps.llm.llm_factory import get_chat_model

def run_test():
    # 強制使用 OpenAI
    os.environ['MODEL_TYPE'] = 'OPENAI'
    
    print(f"Using Model Type: {os.getenv('MODEL_TYPE')}")
    print(f"Using OpenAI Model: {os.getenv('OPENAI_MODEL')}")

    prompt = build_prompt(
        doc_type='簽',
        requirement='針對「115 年 Django 數位化轉型專案」實施計畫，擬辦簽呈呈閱並發文各廠遵照辦理。',
        incoming_text='國防部軍備局檢發「115 年 Django 數位化轉型專案」實施計畫乙份，請查照辦理。',
        incoming_level='FROM_SUPERIOR'
    )

    try:
        llm = get_chat_model()
        print('--- INVOKING LLM (OpenAI) ---')
        result = llm.invoke(prompt)
        
        print('--- GENERATED DRAFT ---')
        if hasattr(result, 'content'):
            print(result.content)
        else:
            print(str(result))
            
    except Exception as e:
        print(f'ERROR: {str(e)}')

if __name__ == "__main__":
    run_test()

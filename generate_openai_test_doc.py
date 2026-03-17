import os
import django
import json

# 設定 Django 環境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

from webapps.doc.prompt import build_prompt
from webapps.llm.llm_factory import get_chat_model

def generate_test_doc():
    # 強制執行 OpenAI 測試 (已在 .env 中設定，此處僅為輔助說明)
    os.environ['MODEL_TYPE'] = 'OPENAI'
    
    print(f"--- 開始測試 OpenAI LLM (Django 系統) ---")
    print(f"後端模型: {os.getenv('OPENAI_MODEL', 'gpt-4o-mini')}")

    # 範例來文內容
    incoming_agency = "國防部軍備局"
    incoming_subject = "有關「115 年全軍 AI 基礎設施升級專案」軟體建置案，請查照辦理。"
    incoming_text = f"機關：{incoming_agency}\n主旨：{incoming_subject}\n說明：一、本局規劃於 115 年度進行全軍 AI 基礎設施升級，其中軟體建置部分需 貴中心協助評估人力及後續維運方案。二、請於 3 月 15 日前函復本局。"

    print(f"\n【來文主旨】: {incoming_subject}")

    # 建立生成 Prompt
    prompt = build_prompt(
        doc_type='簽',
        requirement='擬辦簽呈，陳報本中心參與專案之人力編組與後續維護計畫。',
        incoming_text=incoming_text,
        incoming_level='FROM_SUPERIOR'
    )

    try:
        llm = get_chat_model()
        print('--- 正在調用 OpenAI API 生成簽呈... ---')
        result = llm.invoke(prompt)
        
        print('\n--- 【生成簽呈結果】 ---')
        if hasattr(result, 'content'):
            draft_content = result.content
        else:
            draft_content = str(result)
        
        print(draft_content)
        return incoming_subject, draft_content
            
    except Exception as e:
        print(f'ERROR: {str(e)}')
        return None, None

if __name__ == "__main__":
    generate_test_doc()

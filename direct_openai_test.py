import os
from openai import OpenAI

try:
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    print(f"Using API Key: {os.getenv('OPENAI_API_KEY')[:10]}...")
    
    response = client.chat.completions.create(
      model="gpt-4o-mini",
      messages=[
        {"role": "system", "content": "你是一位專業的國軍公文秘書。"},
        {"role": "user", "content": "請根據國防部軍備局來文『115 年全軍 AI 基礎設施升級專案』，擬辦一份簡短的簽呈主旨與擬辦建議。"}
      ],
      temperature=0.2,
      max_tokens=500
    )
    
    print("--- GENERATED RESPONSE ---")
    print(response.choices[0].message.content)

except Exception as e:
    print(f"Error: {e}")

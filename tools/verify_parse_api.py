# H:\AI\DJANGO\tools\verify_parse_api.py
import asyncio
import os
import json
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def verify_parse_focus():
    # 測試 sharp-orbit 伺服器
    BASE_URL = "http://192.168.0.139:8000/djangoai/doc/"
    AUTH_PARAM = "?aaa=Fy1o2u9r1a9s5t6u0p0i"
    
    print(f"🚀 開始驗證解析功能... URL: {BASE_URL}{AUTH_PARAM}")
    
    async with async_playwright() as p:
        # 使用 headless=False 可以更清楚看到發生什麼事，但伺服器端建議用 True
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # 1. 進入頁面
            response = await page.goto(f"{BASE_URL}{AUTH_PARAM}")
            if response.status != 200:
                print(f"❌ 頁面載入失敗: {response.status}")
                return

            print("✅ 頁面載入成功，等待附件列表...")
            await page.wait_for_timeout(3000) # 等待列表載入

            # 2. 獲取所有附件 Checkbox
            checkboxes = await page.query_selector_all("input[type='checkbox']")
            if not checkboxes:
                print("❌ 未發現附件 Checkbox")
                return
                
            print(f"✅ 發現 {len(checkboxes)} 個附件。開始逐筆測試「解析附件」...")

            # 測試前兩筆即可
            for i in range(min(len(checkboxes), 2)):
                print(f"\n--- 測試附件 {i+1} ---")
                # 先清除所有勾選
                for cb in checkboxes: await cb.uncheck()
                # 勾選當前目標
                await checkboxes[i].check()
                
                # 3. 點擊「解析附件」按鈕
                parse_btn = await page.query_selector("button:has-text('解析附件')")
                if not parse_btn:
                    print("❌ 找不到「解析附件」按鈕")
                    break
                
                await parse_btn.click()
                print("🖱️ 已點擊解析附件，等待結果...")

                # 4. 監聽 API 回傳與前端反應
                # 等待結果填入 #attachFocusResult 或報錯彈窗
                try:
                    # 等待一段時間讓 API 完成
                    await page.wait_for_timeout(5000)
                    
                    result_value = await page.input_value("#attachFocusResult")
                    if "重點1" in result_value:
                        print(f"✅ 解析成功！結果摘要：\n{result_value[:100]}...")
                    else:
                        # 檢查是否有錯誤顯示
                        print(f"⚠️ 解析結果異常。當前內容：{result_value}")
                        # 擷圖存證
                        await page.screenshot(path=f"H:/AI/DJANGO/tools/parse_fail_{i}.png")
                except Exception as e:
                    print(f"❌ 解析過程發生錯誤: {str(e)}")

            print("\n✅ Playwright 功能驗證完畢。")

        except Exception as e:
            print(f"❌ 發生致命錯誤: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(verify_parse_focus())


import asyncio
import os
import json
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def run_audit():
    # 既然 sharp-orbit 伺服器綁定在 192.168.0.139，且 127.0.0.1 在 PowerShell 下報 INVALID_ARGUMENT
    # 代表 Playwright 可能無法正確路由 127.0.0.1。
    # 我們改回 192.168.0.139 並「不帶額外 Header」，直接嘗試
    BASE_URL = "http://192.168.0.139:8000/djangoai/doc/"
    AUTH_PARAM = "?aaa=Fy1o2u9r1a9s5t6u0p0i"
    
    print("START_TEST: 開始驗證四筆 Mock 公文重點一格式...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        target_url = f"{BASE_URL}{AUTH_PARAM}"
        print(f"URL: {target_url}")
        
        try:
            await page.goto(target_url, timeout=60000)
            print("STEP: 頁面已載入")
            
            # 檢測是否有 DisallowedHost
            content = await page.content()
            if "DisallowedHost" in content:
                print("ERROR: Django 拒絕了連線 (DisallowedHost)。")
                return

            await page.wait_for_timeout(5000)
            checkboxes = await page.query_selector_all("input[type='checkbox']")
            
            if not checkboxes:
                print("ERROR: 未發現任何附件勾選框。")
                return

            results = []
            for i in range(min(len(checkboxes), 4)):
                print(f"\n--- 測試第 {i+1} 筆 ---")
                await checkboxes[i].check()
                
                parse_btn = await page.query_selector("button:has-text('解析附件')")
                if parse_btn:
                    await parse_btn.click()
                    await page.wait_for_selector("#attachFocusResult", timeout=45000)
                    result_text = await page.input_value("#attachFocusResult")
                    lines = result_text.splitlines()
                    point_one = next((l for l in lines if l.startswith("重點1：")), "未找到重點一")
                    results.append({"id": i+1, "point1": point_one})
                    print(f"RESULT: {point_one}")
                
            print("\n" + "="*50)
            print("🏆 四筆公文重點一驗證報告")
            print("="*50)
            for r in results:
                print(f"序號：{r['id']}\n內容：{r['point1']}\n" + "-"*30)

        except Exception as e:
            print(f"FATAL_ERROR: {str(e)}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_audit())

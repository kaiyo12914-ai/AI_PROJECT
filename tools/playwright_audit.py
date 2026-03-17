import asyncio
from playwright.async_api import async_playwright
import sys
import os

# 強制輸出為 UTF-8
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

async def verify_site_status():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        results = []
        
        # 1. 驗證 Django AI (Port 8000)
        try:
            await page.goto("http://127.0.0.1:8000/djangoai/", timeout=5000)
            results.append("[OK] Django AI (Port 8000)")
        except Exception as e:
            results.append(f"[FAIL] Django AI (Port 8000): {str(e)[:50]}")

        # 2. 驗證 班級網站 (Port 8001)
        try:
            await page.goto("http://127.0.0.1:8001/dashboard/", timeout=5000)
            results.append("[OK] Class Dashboard (Port 8001)")
        except Exception as e:
            results.append(f"[FAIL] Class Dashboard (Port 8001): {str(e)[:50]}")

        # 3. 驗證 無人機管理 (Port 8002)
        try:
            await page.goto("http://127.0.0.1:8002/service/unit/", timeout=5000)
            results.append("[OK] Drone Service (Port 8002)")
        except Exception as e:
            results.append(f"[FAIL] Drone Service (Port 8002): {str(e)[:50]}")
            
        await browser.close()
        return results

if __name__ == "__main__":
    report = asyncio.run(verify_site_status())
    print("--- PLAYWRIGHT AUDIT REPORT ---")
    for line in report:
        print(line)

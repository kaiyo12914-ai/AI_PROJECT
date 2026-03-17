import asyncio
from playwright.async_api import async_playwright
import sys

async def check_static_404():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 測試靜態檔案 (嘗試 localhost)
        url = "http://localhost:8000/djangoai/static/portal/css/index.css"
        print(f"Checking: {url}")
        try:
            response = await page.goto(url, timeout=10000)
            print(f"Status: {response.status}")
            return response.status
        except Exception as e:
            print(f"Error: {e}")
            return None
        finally:
            await browser.close()

if __name__ == "__main__":
    status = asyncio.run(check_static_404())
    if status == 200:
        print("SUCCESS: Static file found.")
    else:
        print(f"FAILED: Static file returned {status}")

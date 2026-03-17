import asyncio
import os
import subprocess
import time
from playwright.async_api import async_playwright

async def run_test():
    # 1. 啟動 Django Server (背景)
    server_process = subprocess.Popen(
        ["H:\\AI\\Django\\venv3.12\\Scripts\\python.exe", "manage.py", "runserver", "8001", "--noreload"],
        cwd="H:\\AI\\Django",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print("Waiting for server to start...")
    time.sleep(5)  # 給伺服器一點啟動時間
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 捕捉 Console 訊息（特別是靜態檔案 404）
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
        page.on("requestfailed", lambda request: print(f"REQUEST FAILED: {request.url} ({request.failure.error_text})"))
        
        print("Navigating to portal...")
        try:
            # 存取入口網頁
            await page.goto("http://127.0.0.1:8001/djangoai/", timeout=10000)
            print(f"Page Title: {await page.title()}")
            
            # 檢查是否有靜態資源載入失敗
            # Playwright 會自動記錄 requestfailed
            
        except Exception as e:
            print(f"Test failed: {e}")
            
        await browser.close()
    
    # 關閉伺服器
    server_process.terminate()
    print("Test finished and server closed.")

if __name__ == "__main__":
    asyncio.run(run_test())

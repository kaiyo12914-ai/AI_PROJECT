import asyncio
import os
import subprocess
import time
import requests
from playwright.async_api import async_playwright

# 姚承佑 的 Mock Token
AAA_TOKEN = "Fy1o2u9r1a9s5t6u0p0i"

async def test_meeting_rag():
    # 1. 啟動 Django Server (背景)
    env = os.environ.copy()
    env["PYTHONPATH"] = "H:\\AI\\Django"
    
    # 使用臨時測試設定
    test_settings_path = "H:\\AI\\Django\\webproj\\test_settings_sub.py"
    with open(test_settings_path, "w", encoding="utf-8") as f:
        f.write("from .settings import *\n")
        f.write("PORTAL_ACL_ENABLED = False\n")
        f.write("CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8001']\n")
        f.write("MIDDLEWARE = [m for m in MIDDLEWARE if 'CsrfViewMiddleware' not in m]\n")

    server_process = subprocess.Popen(
        ["H:\\AI\\Django\\venv3.12\\Scripts\\python.exe", "manage.py", "runserver", "8001", "--noreload", "--settings=webproj.test_settings_sub"],
        cwd="H:\\AI\\Django",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    print("Waiting for server...")
    time.sleep(5)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 測試目標：會議擬答頁面的 RAG 檢索功能
        url = f"http://127.0.0.1:8001/djangoai/meetingreply/?aaa={AAA_TOKEN}"
        print(f"Navigating to: {url}")
        await page.goto(url, timeout=30000)
        
        # 1. 輸入查詢關鍵字
        print("Entering query keyword...")
        await page.fill("#directive", "資安")
        
        # 2. 點擊 RAG 檢索按鈕
        print("Clicking RAG Search button...")
        await page.click("#btnRag")
        
        # 3. 等待檢索結果
        print("Waiting for RAG results...")
        start_time = time.time()
        found = False
        while time.time() - start_time < 45:
            hits_text = await page.inner_text("#hitCount")
            # 去除空白
            hits_text = hits_text.strip()
            if hits_text and hits_text != "0":
                print(f"RAG SUCCESS: Found {hits_text} hits!")
                found = True
                break
            
            # 檢查是否有噴錯 (避免 Unicode 輸出問題)
            status_text = await page.inner_text("#ragStatus")
            if "fail" in status_text.lower() or "error" in status_text.lower():
                print("RAG Status reported an ERROR.")
                break
                
            await asyncio.sleep(3)
        
        if not found:
            print("RAG Search: TIMEOUT or No results found.")
            await page.screenshot(path="rag_test_fail_screenshot.png")
            
        await browser.close()
    
    server_process.terminate()
    print("Test completed.")

if __name__ == "__main__":
    asyncio.run(test_meeting_rag())

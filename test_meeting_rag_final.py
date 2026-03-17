import asyncio
import os
import subprocess
import time
import requests
from playwright.async_api import async_playwright

AAA_TOKEN = "Fy1o2u9r1a9s5t6u0p0i"

async def test_meeting_rag():
    env = os.environ.copy()
    env["PYTHONPATH"] = "H:\\AI\\Django"
    
    test_settings_path = "H:\\AI\\Django\\webproj\\test_settings_final.py"
    with open(test_settings_path, "w", encoding="utf-8") as f:
        f.write("from .settings import *\n")
        f.write("PORTAL_ACL_ENABLED = False\n")
        f.write("CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8001']\n")
        f.write("MIDDLEWARE = [m for m in MIDDLEWARE if 'CsrfViewMiddleware' not in m]\n")

    server_process = subprocess.Popen(
        ["H:\\AI\\Django\\venv3.12\\Scripts\\python.exe", "manage.py", "runserver", "8001", "--noreload", "--settings=webproj.test_settings_final"],
        cwd="H:\\AI\\Django",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    print("Waiting for server...")
    time.sleep(10)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        url = f"http://127.0.0.1:8001/djangoai/meetingreply/?aaa={AAA_TOKEN}"
        print(f"Navigating to: {url}")
        await page.goto(url, timeout=30000)
        
        print("Entering query...")
        await page.fill("#directive", "資安")
        print("Clicking RAG...")
        await page.click("#btnRag")
        
        print("Waiting for hits...")
        start_time = time.time()
        found = False
        while time.time() - start_time < 60:
            hits_text = (await page.inner_text("#hitCount")).strip()
            if hits_text and hits_text != "0":
                print(f"RAG FINAL SUCCESS: Found {hits_text} hits!")
                found = True
                break
            
            status = await page.inner_text("#ragStatus")
            # 避免 Unicode 報錯
            if "fail" in status.lower() or "error" in status.lower() or "失敗" in status:
                print("RAG Error detected (string matched).")
                # 截圖以供參考
                await page.screenshot(path="rag_final_error.png")
                break
                
            await asyncio.sleep(5)
        
        if not found:
            print("RAG failed or no hits found.")
            
        await browser.close()
    
    server_process.terminate()

if __name__ == "__main__":
    asyncio.run(test_meeting_rag())

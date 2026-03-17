import asyncio
import os
import subprocess
import time
import requests
from playwright.async_api import async_playwright

# 從 Mock Data (psid) 獲取的測試參數
# F129195600 -> 姚承佑
AAA_TOKEN = "Fy1o2u9r1a9s5t6u0p0i" 

async def test_subsystems():
    # 1. 啟動 Django Server (背景)
    env = os.environ.copy()
    env["PYTHONPATH"] = "H:\\AI\\Django"
    env["DJANGO_DEBUG"] = "TRUE"
    
    # 建立臨時測試設定 (關閉防禦以便 E2E)
    test_settings_path = "H:\\AI\\Django\\webproj\\test_settings_sub.py"
    with open(test_settings_path, "w", encoding="utf-8") as f:
        f.write("from .settings import *\n")
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
    
    print("Waiting for server to start...")
    success = False
    for _ in range(20):
        try:
            r = requests.get(f"http://127.0.0.1:8001/djangoai/?aaa={AAA_TOKEN}", timeout=1)
            if r.status_code == 200:
                print(f"Server is UP! Logged in as: {AAA_TOKEN}")
                success = True
                break
        except:
            pass
        time.sleep(1)
    
    if not success:
        print("Server failed to start or Login failed.")
        server_process.terminate()
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 使用同一個 context 以保持登入態 (Cookie/Session)
        context = await browser.new_context()
        
        # --- 測試 1: 公文系統 (doc) ---
        print("\n--- [E2E] Testing doc system ---")
        page = await context.new_page()
        url_doc = f"http://127.0.0.1:8001/djangoai/doc/?aaa={AAA_TOKEN}"
        await page.goto(url_doc, timeout=30000)
        await page.wait_for_timeout(2000)
        
        if await page.query_selector("#requirement"):
            print("Page doc loaded. Executing generation...")
            await page.fill("#requirement", "擬辦一份有關辦公室自動化升級的簽呈。")
            await page.click("#btnGenerate")
            
            # 等待生成
            start = time.time()
            while time.time() - start < 45:
                val = await page.input_value("#docResult")
                if val and "這裡會顯示" not in val and "生成中" not in val:
                    print(f"PASS: doc system generation OK. ({len(val)} chars)")
                    break
                await asyncio.sleep(3)
            else:
                print("FAIL: doc system timeout or error.")
        else:
            print(f"FAIL: doc system page load failed. (Status: {page.url})")

        # --- 測試 2: 會議擬答 (meetingreply) ---
        print("\n--- [E2E] Testing meetingreply system ---")
        page = await context.new_page()
        url_mr = f"http://127.0.0.1:8001/djangoai/meetingreply/?aaa={AAA_TOKEN}"
        await page.goto(url_mr, timeout=30000)
        await page.wait_for_timeout(2000)
        
        if await page.query_selector("#directive"):
            print("Page meetingreply loaded. Executing generation...")
            await page.fill("#directive", "請各單位落實資安教育訓練。")
            await page.click("#btnGen")
            
            start = time.time()
            while time.time() - start < 45:
                text = await page.inner_text("#genOut")
                if text and "尚未生成" not in text:
                    print(f"PASS: meetingreply generation OK. ({len(text)} chars)")
                    break
                await asyncio.sleep(3)
            else:
                print("FAIL: meetingreply timeout or error.")
        else:
            print("FAIL: meetingreply page load failed.")

        # --- 測試 3: 人員評語 (comment) ---
        print("\n--- [E2E] Testing comment system ---")
        page = await context.new_page()
        url_com = f"http://127.0.0.1:8001/djangoai/comment/?aaa={AAA_TOKEN}"
        await page.goto(url_com, timeout=30000)
        await page.wait_for_timeout(2000)
        
        if await page.query_selector("#studentList"):
            print("Page comment loaded. Executing generation...")
            await page.fill("#studentList", "1.姚承佑")
            await page.click("#btnGenerateStudents")
            await page.wait_for_selector(".student-btn", timeout=5000)
            await page.click(".student-btn")
            await page.click("[data-tab='performance']")
            await page.wait_for_selector(".trait-btn", timeout=5000)
            await page.click(".trait-btn")
            await page.click("#btnGenerateComment")
            
            start = time.time()
            while time.time() - start < 45:
                preview = await page.inner_text("#commentPreview")
                if preview and "生成中" not in preview and len(preview.strip()) > 10:
                    print(f"PASS: comment system generation OK. ({len(preview)} chars)")
                    break
                await asyncio.sleep(3)
            else:
                print("FAIL: comment timeout or error.")
        else:
            print("FAIL: comment page load failed.")

        await browser.close()
    
    server_process.terminate()
    print("\nE2E Tests Finished.")

if __name__ == "__main__":
    asyncio.run(test_subsystems())

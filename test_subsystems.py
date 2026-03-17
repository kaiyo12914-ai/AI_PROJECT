import asyncio
import os
import subprocess
import time
import requests
from playwright.async_api import async_playwright

async def test_subsystems():
    # 1. 啟動 Django Server (背景)
    env = os.environ.copy()
    env["PYTHONPATH"] = "H:\\AI\\Django"
    env["PORTAL_ACL_ENABLED"] = "FALSE"
    env["DJANGO_DEBUG"] = "TRUE"
    env["DEV_LOGIN_USER"] = "F129195600"
    env["EMP_NAME_LOOKUP"] = "0"
    
    # 建立臨時測試設定
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
    
    print("Waiting for server to start...")
    success = False
    for _ in range(30):
        try:
            r = requests.get("http://127.0.0.1:8001/djangoai/", timeout=1)
            if r.status_code < 500:
                print(f"Server is UP! (Status: {r.status_code})")
                success = True
                break
        except:
            pass
        time.sleep(1)
    
    if not success:
        print("Server failed to start.")
        server_process.terminate()
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # --- 測試 1: 公文系統 (doc) ---
        print("\n--- Testing Subsystem: doc ---")
        page = await context.new_page()
        page.on("console", lambda msg: print(f"[DOC CONSOLE] {msg.type}: {msg.text}"))
        
        await page.goto("http://127.0.0.1:8001/djangoai/doc/", timeout=30000)
        await page.wait_for_timeout(2000)
        
        req_field = await page.query_selector("#requirement")
        if req_field:
            print("Requirement field found. Filling content...")
            await req_field.fill("測試公文生成功能。")
            await page.click("#btnGenerate")
            
            print("Waiting for generation result...")
            start_time = time.time()
            found = False
            while time.time() - start_time < 30:
                content = await page.input_value("#docResult")
                if content and "生成中" not in content and "這裡會顯示" not in content:
                    print(f"DOC Generation SUCCESS. Content length: {len(content)}")
                    found = True
                    break
                await asyncio.sleep(2)
            if not found:
                print("DOC Generation: TIMEOUT or EMPTY")
        else:
            print("DOC Page failed to load correctly (Field #requirement missing)")
            # 偵錯：列出所有 H1
            h1s = await page.query_selector_all("h1")
            for h1 in h1s:
                print(f"H1 content: {await h1.inner_text()}")

        # --- 測試 2: 會議擬答 (meetingreply) ---
        print("\n--- Testing Subsystem: meetingreply ---")
        page = await context.new_page()
        await page.goto("http://127.0.0.1:8001/djangoai/meetingreply/", timeout=30000)
        await page.wait_for_timeout(2000)
        
        directive_field = await page.query_selector("#directive")
        if directive_field:
            print("Directive field found. Filling content...")
            await directive_field.fill("測試會議擬答生成。")
            await page.click("#btnGen")
            
            print("Waiting for generation result...")
            start_time = time.time()
            found = False
            while time.time() - start_time < 30:
                content = await page.inner_text("#genOut")
                if content and "尚未生成" not in content:
                    print(f"MEETING Generation SUCCESS. Content length: {len(content)}")
                    found = True
                    break
                await asyncio.sleep(2)
            if not found:
                print("MEETING Generation: TIMEOUT or EMPTY")
        else:
            print("MEETING Page failed to load correctly")

        # --- 測試 3: 人員評語 (comment) ---
        print("\n--- Testing Subsystem: comment ---")
        page = await context.new_page()
        await page.goto("http://127.0.0.1:8001/djangoai/comment/", timeout=30000)
        await page.wait_for_timeout(2000)
        
        student_field = await page.query_selector("#studentList")
        if student_field:
            print("Student list field found. Generating students...")
            await student_field.fill("1.測試員")
            await page.click("#btnGenerateStudents")
            await page.wait_for_selector(".student-btn")
            await page.click(".student-btn")
            await page.click("[data-tab='performance']")
            await page.wait_for_selector(".trait-btn")
            await page.click(".trait-btn")
            await page.click("#btnGenerateComment")
            
            print("Waiting for generation result...")
            start_time = time.time()
            found = False
            while time.time() - start_time < 30:
                content = await page.inner_text("#commentPreview")
                if content and "生成中" not in content and len(content.strip()) > 10:
                    print(f"COMMENT Generation SUCCESS. Content length: {len(content)}")
                    found = True
                    break
                await asyncio.sleep(2)
            if not found:
                print("COMMENT Generation: TIMEOUT or EMPTY")
        else:
            print("COMMENT Page failed to load correctly")

        await browser.close()
    
    server_process.terminate()
    print("\nTests completed.")

if __name__ == "__main__":
    asyncio.run(test_subsystems())

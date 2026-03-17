import asyncio
import os
import subprocess
import time
import requests
from playwright.async_api import async_playwright

async def run_test():
    # 1. 啟動 Django Server (背景)
    env = os.environ.copy()
    env["PYTHONPATH"] = "H:\\AI\\Django"
    
    server_process = subprocess.Popen(
        ["H:\\AI\\Django\\venv3.12\\Scripts\\python.exe", "manage.py", "runserver", "8001", "--noreload"],
        cwd="H:\\AI\\Django",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    print("Waiting for server to start (polling http://127.0.0.1:8001/djangoai/)...")
    success = False
    for _ in range(30): # 30 seconds max
        try:
            r = requests.get("http://127.0.0.1:8001/djangoai/", timeout=1)
            if r.status_code < 500:
                print(f"Server is UP! (Status: {r.status_code})")
                success = True
                break
        except:
            pass
        time.sleep(1)
        if server_process.poll() is not None:
            print("Server CRASHED during startup!")
            out, _ = server_process.communicate()
            print(out)
            break
    
    if not success:
        print("Server failed to start in time.")
        server_process.terminate()
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 捕捉 Console 訊息
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: [{msg.type}] {msg.text}"))
        page.on("requestfailed", lambda req: print(f"REQUEST FAILED: {req.url}"))
        
        print("Navigating to portal...")
        try:
            # 存取入口網頁
            await page.goto("http://127.0.0.1:8001/djangoai/", timeout=30000)
            print(f"Page Title: {await page.title()}")
            
            # 獲取所有的 404 資源 (特別是靜態檔)
            # 這裡可以透過監聽 response 達到
            page.on("response", lambda res: print(f"HTTP {res.status}: {res.url}") if res.status >= 400 else None)
            
            # 等待一段時間讓 JS 執行
            await page.wait_for_timeout(3000)
            
        except Exception as e:
            print(f"Playwright error: {e}")
            
        await browser.close()
    
    # 關閉伺服器
    server_process.terminate()
    print("Test finished and server closed.")

if __name__ == "__main__":
    asyncio.run(run_test())

import asyncio
import os
import subprocess
import time
import requests
from playwright.async_api import async_playwright

AAA_TOKEN = "Fy1o2u9r1a9s5t6u0p0i"

async def test_old_rag():
    env = os.environ.copy()
    env["PYTHONPATH"] = "H:\\AI\\Django"
    
    server_process = subprocess.Popen(
        ["H:\\AI\\Django\\venv3.12\\Scripts\\python.exe", "manage.py", "runserver", "8002", "--noreload", "--settings=webproj.test_settings_old_rag"],
        cwd="H:\\AI\\Django",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    print("Waiting for server on port 8002...")
    time.sleep(8)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        url = f"http://127.0.0.1:8002/djangoai/meetingreply/?aaa={AAA_TOKEN}"
        await page.goto(url, timeout=30000)
        await page.fill("#directive", "資安")
        await page.click("#btnRag")
        
        print("Checking RAG hits for old path...")
        start_time = time.time()
        found = False
        while time.time() - start_time < 20:
            hits_text = (await page.inner_text("#hitCount")).strip()
            if hits_text and hits_text != "0":
                print(f"OLD PATH RAG SUCCESS: Found {hits_text} hits!")
                found = True
                break
            await asyncio.sleep(2)
        
        if not found:
            print("OLD PATH RAG failed or timed out.")
            
        await browser.close()
    
    server_process.terminate()

if __name__ == "__main__":
    asyncio.run(test_old_rag())

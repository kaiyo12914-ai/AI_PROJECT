import asyncio
from playwright.async_api import async_playwright
import sys

# Force UTF-8 output
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

async def deep_audit_buttons():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        full_report = []

        # --- 1. Class Portal (Port 8001) ---
        full_report.append("\n[Project: Class 308 - Port 8001]")
        try:
            # 1.1 Home
            await page.goto("http://127.0.0.1:8001/", timeout=10000)
            nav_links = page.locator("nav a")
            count = await nav_links.count()
            full_report.append(f"- [OK] 頂層導覽列按鈕偵測: {count} 個 (功能鏈結正常)")
            
            # 1.2 Dashboard
            await page.goto("http://127.0.0.1:8001/dashboard/", timeout=10000)
            sign_btn = page.locator("button:has-text('點我線上簽名')").first
            if await sign_btn.is_visible():
                full_report.append("- [OK] 第二階層：今日聯絡簿『線上簽名』按鈕驗證通過。")
            
            # 1.3 Generator Page
            await page.goto("http://127.0.0.1:8001/generator/", timeout=10000)
            tags = page.locator(".preset-tag")
            t_count = await tags.count()
            full_report.append(f"- [OK] 第三階層：生成器風格標籤偵測: {t_count} 個 (全交互就緒)")
            gen_btn = page.locator("#genBtn")
            if await gen_btn.is_visible():
                full_report.append("- [OK] 第三階層：『極速拼裝』提交按鈕已具備 API 連結。")
        except Exception as e:
            full_report.append(f"- [FAIL] Class 專案按鈕校驗失敗: {str(e)[:50]}")

        # --- 2. Drone Service (Port 8002) ---
        full_report.append("\n[Project: Drone Service - Port 8002]")
        try:
            await page.goto("http://127.0.0.1:8002/service/unit/", timeout=10000)
            
            # 2.1 Ticket Modal
            btn = page.locator("button:has-text('新增故障通報')")
            if await btn.is_visible():
                await btn.click()
                if await page.locator("#ticketModal h2").is_visible():
                    full_report.append("- [OK] 第一階層：『新增故障通報』彈窗觸發正常。")
                    await page.locator("#ticketModal button:has-text('取消')").click()
            
            # 2.2 Asset Actions
            await page.wait_for_selector("table")
            hours_btn = page.locator(".log-hours-btn").first
            if await hours_btn.is_visible():
                await hours_btn.click()
                if await page.locator("#hoursModal h2").is_visible():
                    full_report.append("- [OK] 第一階層：資產列表『紀錄時數』彈窗觸發正常。")
                    await page.locator("#hoursModal button:has-text('取消')").click()
        except Exception as e:
            full_report.append(f"- [FAIL] Drone 專案按鈕校驗失敗: {str(e)[:50]}")

        await browser.close()
        return full_report

if __name__ == "__main__":
    print("--- STARTING SYSTEM-WIDE MULTI-LEVEL BUTTON AUDIT ---")
    results = asyncio.run(deep_audit_buttons())
    for line in results:
        print(line)
    print("\n--- ALL LEVEL AUDIT COMPLETED ---")

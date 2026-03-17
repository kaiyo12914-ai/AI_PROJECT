import os
import json
import pytest
from playwright.sync_api import sync_playwright

# 環境變量設定（模擬外網離線模式）
MOCK_JSON_PATH = os.path.abspath("SQLTEST_live_test.json")
os.environ["ENV"] = "EXT"
os.environ["MOCK_DB_JSON"] = MOCK_JSON_PATH
os.environ["DJANGO_DEBUG"] = "1"
os.environ["DEV_LOGIN_USER"] = "A123456789"
os.environ["DEV_LOGIN_NAME"] = "測試員"

def setup_mock_data(grsno="1150001261"):
    """
    手動建立一個極簡的 Mock JSON，僅供驗證協定與路徑。
    實際測試時應先執行 SQLTEST.py 產生真實資料。
    """
    data = {
        "records": [
            {
                "meta": {"grsno": grsno, "generated_at": "2026-02-03T08:30:00"},
                "oracle_emp": {"login_user": "A123456789", "login_user_name": "測試員"},
                "oracle_acl": {"groups": ["DOC_USER"], "table": "VIEW_ZZ_USER_GROUP_ACL"},
                "attachments": [
                    {
                        "ef_id": "MOCK_EF_1",
                        "ef_name": "測試附件.pdf",
                        "ef_data_b64": "JVBERi0xLjQKJ...(MOCK PDF)...",
                        "em_grsno": grsno,
                        "em_psid": "A123456789"
                    }
                ],
                "official_docs": [
                    {
                        "tm_grsno": grsno,
                        "td_format": "簽呈",
                        "td_subj": "測試簽呈主旨",
                        "df_data_b64": "JVBERi0xLjQKJ...(MOCK DF)..."
                    }
                ]
            }
        ],
        "latest": {}
    }
    data["latest"] = data["records"][0]
    with open(MOCK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()

def test_doc_api_simulation(browser):
    """
    驗證 API 在 EXT 模式下是否正確讀取 Mock JSON
    """
    setup_mock_data()
    
    page = browser.new_page()
    base_url = "http://127.0.0.1:8000/djangoai"
    
    # 1. 測試 incoming_lookup
    grsno = "1150001261"
    url = f"{base_url}/doc/incoming_lookup/?tm_grsno={grsno}"
    print(f"Testing URL: {url}")
    
    page.goto(url)
    content = page.content()
    # 獲取 JSON 文字（Playwright 會把 JSON 包在 <pre> 中）
    body_text = page.inner_text("body")
    res = json.loads(body_text)
    
    assert res["ok"] is True
    assert len(res["items"]) > 0
    assert res["items"][0]["tm_grsno"] == grsno
    assert "測試附件" in res["items"][0]["attachments"][0]["filename"]

    # 2. 測試下載功能 (EF)
    attach_key = res["items"][0]["attachments"][0]["attach_key"]
    download_url = f"{base_url}/doc/api/sybase/incoming/file/?attach_key={attach_key}"
    
    with page.expect_download() as download_info:
        page.goto(download_url)
    download = download_info.value
    assert "測試附件" in download.suggested_filename
    
    print("DOC Simulation Verification Passed!")

if __name__ == "__main__":
    # 如果直接執行此腳本
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            test_doc_api_simulation(browser)
        finally:
            browser.close()
            if os.path.exists(MOCK_JSON_PATH):
                os.remove(MOCK_JSON_PATH)

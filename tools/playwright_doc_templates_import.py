import argparse
import json
import os
from typing import Any, Dict, Optional

from playwright.sync_api import sync_playwright


def _parse_json_payload(request) -> Optional[Dict[str, Any]]:
    try:
        return request.post_data_json()
    except Exception:
        try:
            raw = request.post_data() or ""
            return json.loads(raw) if raw else None
        except Exception:
            return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate doc templates sybase preview via Playwright")
    parser.add_argument("--url", default=os.getenv("DOC_TEMPLATES_URL", "http://127.0.0.1/djangoai/doc/templates/"))
    parser.add_argument("--grsno", default=os.getenv("DOC_TEMPLATES_GRSNO", "1150000712"))
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    target_url = args.url
    grsno = str(args.grsno)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headful)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector("#sybImportGrsno", timeout=8000)
        page.fill("#sybImportGrsno", grsno)

        with page.expect_response("**/api/sybase/template/import/**", timeout=20000) as resp_info:
            page.click("#btnImportTplFromSybase")

        resp = resp_info.value
        status = resp.status
        ct = resp.headers.get("content-type", "")
        body_text = resp.text()

        print(f"status={status}")
        print(f"content-type={ct}")
        print(f"url={resp.url}")

        if status >= 400:
            print("ERROR: preview request failed")
            print(body_text[:2000])
            return 2

        if "application/json" in ct:
            try:
                data = resp.json()
            except Exception:
                data = None
            print("json:", json.dumps(data, ensure_ascii=False)[:2000] if data is not None else "null")
        else:
            print(body_text[:2000])

        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

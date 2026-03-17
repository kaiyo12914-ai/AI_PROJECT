import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8", errors="ignore"))


def _strip_ctrl(s: str) -> str:
    return re.sub(r"[\x00-\x1f]+", "", s or "")


def main() -> int:
    json_path = os.getenv("DOC_MOCK_JSON", "SQLTEST_output1150001261.json")
    base_url = os.getenv("DOC_URL", "http://127.0.0.1/djangoai/doc/")

    data = _load_json(json_path)
    mock = data.get("mock_api", {})

    lookup_payload = mock.get("incoming_lookup") or {"ok": True, "items": []}
    files_payload = mock.get("incoming_files") or {"ok": True, "attachments": [], "items": []}

    # Expected subject from lookup (fallback: "(無主旨)")
    items = lookup_payload.get("items") or []
    subj = ""
    if items:
        subj = (items[0].get("td_subj") or items[0].get("subject") or "").strip()
    expected_subj = subj if subj else "(無主旨)"

    # Expected filenames (strip control chars for UI display)
    filenames = [_strip_ctrl(a.get("filename", "")) for a in (files_payload.get("attachments") or [])]
    filenames = [f for f in filenames if f]

    # Stash mock: create stable tokens per attach_key
    stash_tokens = {}

    def is_api(url: str, suffix: str) -> bool:
        return url.lower().endswith(suffix.lower())

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        def route_handler(route):
            url = route.request.url
            if is_api(url, "/doc/api/sybase/incoming/lookup/"):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(lookup_payload))
                return
            if is_api(url, "/doc/api/sybase/incoming/files/"):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(files_payload))
                return
            if is_api(url, "/doc/api/sybase/blob/stash/"):
                req = route.request
                body = req.post_data or ""
                try:
                    payload = json.loads(body) if body else {}
                except Exception:
                    payload = {}
                attach_key = (payload.get("attach_key") or "").strip()
                if attach_key not in stash_tokens:
                    stash_tokens[attach_key] = f"t_{len(stash_tokens)+1:02d}"
                token = stash_tokens[attach_key]
                filename = ""
                for a in (files_payload.get("attachments") or []):
                    if (a.get("attach_key") or "").strip() == attach_key:
                        filename = _strip_ctrl(a.get("filename", ""))
                        break
                resp = {"ok": True, "token": token, "filename": filename or "attachment.bin", "size": 1234}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(resp))
                return
            if "/doc/api/sybase/blob/download/" in url:
                route.fulfill(status=200, body=b"MOCK-PDF", content_type="application/pdf")
                return
            if "/doc/api/sybase/incoming/file/" in url:
                route.fulfill(status=200, body=b"MOCK-PDF", content_type="application/pdf")
                return
            # passthrough others
            route.continue_()

        page.route("**/*", route_handler)

        page.goto(base_url, wait_until="networkidle")

        # Query and load attachments
        page.fill("#qEmGrsno", data.get("meta", {}).get("grsno", ""))
        page.click("#btnLookupIncoming")
        page.wait_for_timeout(500)

        # select first option if present
        if page.locator("#incomingPick option").count() > 1:
            page.select_option("#incomingPick", index=1)

        # subject displayed in dropdown
        page.get_by_text(expected_subj).wait_for(timeout=3000)

        page.click("#btnLoadIncomingAttachments")
        page.wait_for_timeout(500)

        # Assertions: filenames rendered
        for name in filenames:
            if not name:
                continue
            # UI may show name within attachment list
            page.get_by_text(name).wait_for(timeout=3000)

        # Click select all and stash
        if page.locator("#btnIncomingAttachAll").count() > 0:
            page.click("#btnIncomingAttachAll")
        if page.locator("#btnStashIncomingAttachments").count() > 0:
            page.click("#btnStashIncomingAttachments")
            page.wait_for_timeout(500)

        # Click first download link if present
        if page.locator(".incoming-attach-actions a").count() > 0:
            page.locator(".incoming-attach-actions a").first.click()
            page.wait_for_timeout(300)

        print("OK: attachments displayed", filenames)

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

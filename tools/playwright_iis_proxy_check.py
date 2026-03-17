from __future__ import annotations

import argparse
import sys
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


def _abs_url(base: str, maybe_relative: str) -> str:
    if not maybe_relative:
        return ""
    if maybe_relative.startswith("http://") or maybe_relative.startswith("https://"):
        return maybe_relative
    return urljoin(base, maybe_relative)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check IIS reverse proxy via Playwright")
    parser.add_argument(
        "--url",
        default="https://127.0.0.1/djangoai/doc/",
        help="Full external URL of the doc page",
    )
    args = parser.parse_args()

    base_url = args.url

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        resp = page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
        status = resp.status if resp else None
        if not resp or status is None or status >= 400:
            print(f"FAIL: page response status = {status}")
            return 2

        page.wait_for_selector("body", timeout=5000)

        final_url = page.url
        base_prefix = page.evaluate("document.body && document.body.dataset && document.body.dataset.baseUrl || ''")

        expect_proxy = "/djangoai/" in base_url
        if expect_proxy:
            if "/djangoai/" not in final_url:
                print(f"FAIL: page URL does not include /djangoai/: {final_url}")
                return 3
            if not str(base_prefix).startswith("/djangoai/"):
                print(f"FAIL: data-base-url does not start with /djangoai/: {base_prefix!r}")
                return 4
        else:
            if "/djangoai/" in final_url:
                print(f"FAIL: page URL unexpectedly includes /djangoai/: {final_url}")
                return 3
            if str(base_prefix) not in ("/doc", "/doc/"):
                print(f"FAIL: data-base-url should be /doc for non-proxy: {base_prefix!r}")
                return 4

        api_templates = page.evaluate(
            "window.DocDocApp && window.DocDocApp.api && window.DocDocApp.api.templates || ''"
        )
        if not api_templates:
            print("FAIL: window.DocDocApp.api.templates not found")
            return 5

        expected_api_prefix = "/djangoai/doc" if expect_proxy else "/doc"
        if not str(api_templates).startswith(expected_api_prefix):
            print(
                f"FAIL: api.templates does not start with {expected_api_prefix}: {api_templates!r}"
            )
            return 6

        api_url = _abs_url(final_url, str(api_templates))
        api_resp = context.request.get(api_url, timeout=15000)
        api_status = api_resp.status
        if api_status in (401, 403):
            print(f"FAIL: api.templates returned {api_status} (auth/ACL issue)")
            return 7
        if api_status >= 400:
            print(f"FAIL: api.templates returned {api_status}")
            return 8

        css_href = page.evaluate(
            "(document.querySelector('link[rel=stylesheet]') || {}).href || ''"
        )
        css_url = _abs_url(final_url, str(css_href))
        if css_url:
            css_resp = context.request.get(css_url, timeout=15000)
            css_status = css_resp.status
            if css_status >= 400:
                print(f"FAIL: stylesheet returned {css_status}: {css_url}")
                return 9

        print("OK: IIS reverse proxy looks healthy")
        print(f"page: {final_url}")
        print(f"data-base-url: {base_prefix}")
        print(f"api.templates: {api_url} ({api_status})")
        if css_url:
            print(f"stylesheet: {css_url} ({css_status})")

        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

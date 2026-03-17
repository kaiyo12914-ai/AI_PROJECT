import argparse
import json
import os
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright


def _log(msg: str) -> None:
    print(msg, flush=True)


def _parse_json_payload(request) -> Optional[Dict[str, Any]]:
    try:
        return request.post_data_json()
    except Exception:
        try:
            raw = request.post_data() or ""
            return json.loads(raw) if raw else None
        except Exception:
            return None


def _mock_templates(doc_type: str) -> Dict[str, Any]:
    return {
        "templates": [
            {
                "id": 101,
                "title": "範例A（可勾選）",
                "doc_type": doc_type,
                "tags": ["資訊", "測試"],
                "description": "用於 Playwright 驗證",
                "content_text": "這是範例A內容。",
                "scope": "public",
            },
            {
                "id": 102,
                "title": "範例B（可勾選）",
                "doc_type": doc_type,
                "tags": ["資訊"],
                "description": "用於 Playwright 驗證",
                "content_text": "這是範例B內容。",
                "scope": "public",
            },
        ]
    }


def _mock_incoming_lookup(grsno: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "items": [
            {
                "tm_grsno": grsno,
                "td_subj": f"測試主旨 {grsno}",
                "tm_text": "測試內容（incoming lookup）",
            }
        ],
    }


def _mock_incoming_files() -> Dict[str, Any]:
    return {
        "ok": True,
        "attachments": [
            {"attach_key": "A1", "filename": "附件A.pdf", "size": "12KB"},
            {"attach_key": "B2", "filename": "附件B.pdf", "size": "8KB"},
        ],
    }


def _mock_template_import_preview(grsno: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "grsno": grsno,
        "count": 2,
        "docs": [
            {"key": "簽呈::row1", "format": "簽呈", "title": f"簽呈: {grsno} (1)", "doc_type": "sign_memo"},
            {"key": "令::row2", "format": "令", "title": f"令: {grsno} (2)", "doc_type": "order_draft"},
        ],
    }


def _mock_template_import_result(selected: List[str], grsno: str) -> Dict[str, Any]:
    results = []
    for i, key in enumerate(selected, start=1):
        fmt = key.split("::", 1)[0] if "::" in key else "簽呈"
        results.append(
            {
                "id": 2000 + i,
                "created": True,
                "title": f"{fmt}: {grsno}",
                "format": fmt,
                "doc_type": "sign_memo" if fmt == "簽呈" else "order_draft",
                "scope": "personal",
                "on_conflict": "suffix",
                "status": "created",
                "doc_key": key,
            }
        )
    return {
        "ok": True,
        "created": len(results),
        "created_count": len(results),
        "count": len(results),
        "skipped": 0,
        "results": results,
    }


def _mock_parse_focus(tokens: str) -> Dict[str, Any]:
    return {
        "summary_text": f"附件摘要（tokens={tokens or 'none'}）",
        "files": [{"name": "附件A.pdf"}, {"name": "附件B.pdf"}],
    }


def _mock_generate(example_ids: List[int]) -> Dict[str, Any]:
    return {
        "prompt": f"PROMPT_OK example_ids={example_ids}",
        "draft_text": f"DRAFT_OK example_ids={example_ids}",
        "provider": "mock",
        "model": "mock-model",
        "rag_backend": "mock-rag",
    }


def _diagnose_checkbox(page) -> Dict[str, Any]:
    return page.evaluate(
        """() => {
          const el = document.querySelector(".tplCk");
          if (!el) return { ok: false, reason: "no .tplCk" };
          const rect = el.getBoundingClientRect();
          const cx = rect.left + rect.width / 2;
          const cy = rect.top + rect.height / 2;
          const hit = document.elementFromPoint(cx, cy);
          const style = window.getComputedStyle(el);
          const hitStyle = hit ? window.getComputedStyle(hit) : null;
          return {
            ok: true,
            checked: el.checked,
            disabled: el.disabled,
            visible: !!(rect.width && rect.height),
            pointerEvents: style.pointerEvents,
            display: style.display,
            visibility: style.visibility,
            opacity: style.opacity,
            hitTag: hit ? hit.tagName : null,
            hitClass: hit ? hit.className : null,
            hitPointerEvents: hitStyle ? hitStyle.pointerEvents : null,
          };
        }"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright full doc flow validation")
    parser.add_argument("--url", default=os.getenv("DOC_URL", "http://127.0.0.1/djangoai/doc/"))
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--no-mock", action="store_true", help="Do not mock API endpoints")
    parser.add_argument("--screenshot", default="tools/playwright_doc_full_flow.png")
    args = parser.parse_args()

    grsno = "1150001261"
    diag = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headful)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        if not args.no_mock:
            def route_json(url_glob: str, payload: Dict[str, Any], status: int = 200):
                def handler(route, request):
                    route.fulfill(
                        status=status,
                        content_type="application/json",
                        body=json.dumps(payload, ensure_ascii=False),
                    )
                context.route(url_glob, handler)

            def templates_handler(route, request):
                doc_type = "sign_memo"
                try:
                    url = request.url or ""
                    if "doc_type=" in url:
                        doc_type = url.split("doc_type=", 1)[1].split("&", 1)[0] or doc_type
                except Exception:
                    pass
                payload = _mock_templates(doc_type)
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

            def generate_handler(route, request):
                payload = _parse_json_payload(request) or {}
                example_ids = payload.get("example_ids") or []
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(_mock_generate(example_ids), ensure_ascii=False),
                )

            def parse_focus_handler(route, request):
                # Tokens are stored in hidden input; we can't parse multipart reliably here.
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(_mock_parse_focus("mocked"), ensure_ascii=False),
                )

            def import_handler(route, request):
                payload = _parse_json_payload(request) or {}
                action = str(payload.get("action") or "").lower()
                if action in ("preview", "list"):
                    resp = _mock_template_import_preview(grsno)
                else:
                    selected = payload.get("doc_keys") or []
                    if not isinstance(selected, list):
                        selected = [selected] if selected else []
                    resp = _mock_template_import_result([str(x) for x in selected if str(x).strip()], grsno)
                route.fulfill(status=200, content_type="application/json", body=json.dumps(resp, ensure_ascii=False))

            def stash_handler(route, request):
                payload = _parse_json_payload(request) or {}
                key = str(payload.get("attach_key") or "").strip() or "A1"
                resp = {"ok": True, "token": f"t_{key}", "filename": f"{key}.pdf", "size": 1234}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(resp, ensure_ascii=False))

            context.route("**/api/templates/**", templates_handler)
            context.route("**/api/generate/**", generate_handler)
            context.route("**/api/parse_focus/**", parse_focus_handler)
            context.route("**/api/sybase/template/import/**", import_handler)
            context.route("**/doc/api/sybase/template/import/**", import_handler)
            context.route("**/api/sybase/incoming/lookup/**", lambda r, req: r.fulfill(
                status=200, content_type="application/json", body=json.dumps(_mock_incoming_lookup(grsno), ensure_ascii=False)
            ))
            context.route("**/doc/api/sybase/incoming/lookup/**", lambda r, req: r.fulfill(
                status=200, content_type="application/json", body=json.dumps(_mock_incoming_lookup(grsno), ensure_ascii=False)
            ))
            context.route("**/api/sybase/incoming/files/**", lambda r, req: r.fulfill(
                status=200, content_type="application/json", body=json.dumps(_mock_incoming_files(), ensure_ascii=False)
            ))
            context.route("**/doc/api/sybase/incoming/files/**", lambda r, req: r.fulfill(
                status=200, content_type="application/json", body=json.dumps(_mock_incoming_files(), ensure_ascii=False)
            ))
            context.route("**/api/sybase/blob/stash/**", stash_handler)
            context.route("**/doc/api/sybase/blob/stash/**", stash_handler)
            context.route("**/api/sybase/blob/download/**", lambda r, req: r.fulfill(status=200, body=b"MOCK-PDF", content_type="application/pdf"))
            context.route("**/doc/api/sybase/blob/download/**", lambda r, req: r.fulfill(status=200, body=b"MOCK-PDF", content_type="application/pdf"))
            context.route("**/api/sybase/incoming/file/**", lambda r, req: r.fulfill(status=200, body=b"MOCK-PDF", content_type="application/pdf"))
            context.route("**/doc/api/sybase/incoming/file/**", lambda r, req: r.fulfill(status=200, body=b"MOCK-PDF", content_type="application/pdf"))

        page.goto(args.url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector("body", timeout=8000)

        # Ensure templates list exists
        page.wait_for_selector(".tplCk", timeout=8000)
        tpl_count = page.locator(".tplCk").count()
        _log(f"templates checkboxes: {tpl_count}")

        # Try checking first template
        ck = page.locator(".tplCk").first
        ck.scroll_into_view_if_needed()
        ck.click()
        page.wait_for_timeout(200)

        is_checked = ck.is_checked()
        _log(f"tplCk checked after click: {is_checked}")

        if not is_checked:
            diag = _diagnose_checkbox(page)
            _log(f"tplCk diagnose: {json.dumps(diag, ensure_ascii=False)}")

        # Example preview should update
        hint_text = page.locator("#exampleHint").inner_text()
        _log(f"exampleHint: {hint_text}")

        # Incoming sybase lookup + attachments
        if page.locator("#qEmGrsno").count() > 0:
            page.fill("#qEmGrsno", grsno)
            page.click("#btnLookupIncoming")
            page.wait_for_timeout(300)
            if page.locator("#incomingPick option").count() > 1:
                page.select_option("#incomingPick", index=1)
            page.click("#btnLoadIncomingAttachments")
            page.wait_for_timeout(300)
            if page.locator(".incomingAttachCk").count() > 0:
                page.click("#btnIncomingAttachAll")
                page.click("#btnStashIncomingAttachments")
                page.wait_for_timeout(300)

        # Parse attachments (uses sybAttachTokens)
        if page.locator("#btnParseAttach").count() > 0:
            page.click("#btnParseAttach")
            page.wait_for_timeout(300)

        # Generate doc
        page.fill("#requirement", "測試需求：請產出範例公文。")
        page.click("#btnGenerate")
        page.wait_for_timeout(500)

        prompt_val = page.locator("#promptOut").input_value()
        draft_val = page.locator("#docResult").input_value()
        _log(f"promptOut len={len(prompt_val)} draft len={len(draft_val)}")

        page.screenshot(path=args.screenshot, full_page=True)
        _log(f"screenshot: {args.screenshot}")

        context.close()
        browser.close()

    if diag:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

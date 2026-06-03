from __future__ import annotations

from django.shortcuts import render

from webapps.portal.decorators import require_node
from webapps.vanna.vanna_adapter import VENDOR_ROOT, VENDOR_SRC, ensure_vanna_vendor_loaded


@require_node("nl2sql")
def page_index(request):
    runtime = ensure_vanna_vendor_loaded()
    return render(
        request,
        "vanna/index.html",
        {
            "vanna_version": runtime.version,
            "vendor_ready": VENDOR_SRC.exists(),
            "vendor_path": str(VENDOR_ROOT),
            "runtime_error": runtime.error,
        },
    )

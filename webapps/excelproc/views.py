# webapps/excelproc/views.py
from __future__ import annotations

import os
from urllib.parse import quote

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node, ensure_no_proxy
from .services import (
    import_contact_data_bytes,
    compare_data_bytes,
    export_mpc_employee_data_bytes,
)

ALLOWED_EXTS = {".xlsx", ".xls", ".xlsm"}
MAX_UPLOAD_MB = 20


@require_node("excelproc")
def index(request):
    return render(request, "excelproc/index.html")


def _validate_upload(f) -> str:
    name = os.path.basename(getattr(f, "name", "upload.xlsx"))
    _, ext = os.path.splitext(name)
    ext = (ext or "").lower()

    if ext not in ALLOWED_EXTS:
        raise ValueError(f"僅支援 Excel 檔：{', '.join(sorted(ALLOWED_EXTS))}")

    if getattr(f, "size", 0) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"檔案過大（上限 {MAX_UPLOAD_MB}MB）")

    return name


def _read_upload_bytes(f) -> bytes:
    buf = bytearray()
    for chunk in f.chunks():
        buf.extend(chunk)
    return bytes(buf)


def _download_excel(filename: str, content: bytes) -> HttpResponse:
    filename = (filename or "report.xlsx").strip()
    safe_filename = quote(filename)

    resp = HttpResponse(
        content or b"",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{safe_filename}"
    resp["Cache-Control"] = "no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@require_POST
@require_node("excelproc", api=True)
@csrf_exempt  # ✅ 直接避免 CSRF 403 HTML（內網系統常見更穩）
def run(request):
    """
    POST /excelproc/run/
    FormData:
      action = compare | import | export
      file (optional for compare/import)

    回應：
      - 成功：回 Excel 檔案（attachment）
      - 失敗：回 JSON（ok:false, error）
    """

    # ✅ 若你的環境會喫到公司 HTTP Proxy，避免內部呼叫被 proxy 攔截
    # excelproc 本身不一定用得到，但放著無害（你要求 NO_PROXY）
    ensure_no_proxy(["127.0.0.1", "localhost", "mpcai.mpc.mil.tw", "mpcai.mpc.mil.tw:11434"])

    action = (request.POST.get("action") or "").strip().lower()

    try:
        if action in ("compare", "import"):
            f = request.FILES.get("file")
            if not f:
                return JsonResponse({"ok": False, "error": "請上傳 Excel 檔案"}, status=400)

            upload_name = _validate_upload(f)
            excel_bytes = _read_upload_bytes(f)

            if action == "compare":
                result = compare_data_bytes(excel_bytes, filename=upload_name)
            else:
                result = import_contact_data_bytes(excel_bytes, filename=upload_name)

            if not isinstance(result, dict):
                return JsonResponse({"ok": False, "error": "服務回傳格式錯誤（非 dict）"}, status=500)

            if not result.get("ok"):
                return JsonResponse(result, status=400)

            return _download_excel(
                result.get("filename") or "report.xlsx",
                result.get("content") or b"",
            )

        if action == "export":
            result = export_mpc_employee_data_bytes()

            if not isinstance(result, dict):
                return JsonResponse({"ok": False, "error": "服務回傳格式錯誤（非 dict）"}, status=500)

            if not result.get("ok"):
                return JsonResponse(result, status=400)

            return _download_excel(
                result.get("filename") or "export.xlsx",
                result.get("content") or b"",
            )

        return JsonResponse({"ok": False, "error": "未知 action"}, status=400)

    except RuntimeError as e:
        # DB 友善錯誤
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

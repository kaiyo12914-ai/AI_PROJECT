# webapps/portal/middleware_proxy_prefix.py
from __future__ import annotations

import logging
import re
from django.conf import settings
from django.http import HttpResponseRedirect

logger = logging.getLogger("webapps.proxy_prefix")


def _norm_prefix(p: str) -> str:
    """
    Normalize a URL path prefix:
    - "" -> ""
    - "djangoai" -> "/djangoai"
    - "/djangoai/" -> "/djangoai"
    - "/" -> ""  (treat root as no prefix)
    """
    p = (p or "").strip()
    # IIS sometimes yields "/=/prefix" in forwarded headers; normalize it.
    if p.startswith("/=/"):
        p = "/" + p[3:]
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    if p == "/":
        return ""
    return p.rstrip("/")


def _choose_external_prefix(request) -> tuple[str, str]:
    """
    選擇「外部 prefix」（僅供少數必須手動組外部 URL 的場景）

    優先序：
    1) X-Forwarded-Prefix（僅 TRUST_X_FORWARDED_PREFIX=True 才信）
    2) PROXY_PREFIX（部署固定值）
    3) FORCE_SCRIPT_NAME（最後才用）
    """
    trust_hdr = bool(getattr(settings, "TRUST_X_FORWARDED_PREFIX", False))

    hdr_raw = request.META.get("HTTP_X_FORWARDED_PREFIX", "") or ""
    hdr = _norm_prefix(hdr_raw) if trust_hdr else ""

    cfg_raw = getattr(settings, "PROXY_PREFIX", "") or ""
    cfg = _norm_prefix(cfg_raw)

    force_raw = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
    force = _norm_prefix(force_raw)

    if hdr:
        return hdr, "x_forwarded_prefix"
    if cfg:
        return cfg, "proxy_prefix"
    if force:
        return force, "force_script_name"
    return "", "none"


def _strip_prefix_path(path: str, prefix: str) -> str:
    """
    Strip prefix from PATH_INFO when proxy doesn't remove it.
    - "/djangoai/usage/" + "/djangoai" -> "/usage/"
    - "/djangoai" + "/djangoai" -> "/"
    - otherwise unchanged
    """
    if not path or not prefix:
        return path
    if path == prefix:
        return "/"
    if path.startswith(prefix + "/"):
        return path[len(prefix):]
    return path


class ForwardedPrefixMiddleware:
    """
    反向代理前綴支援（專案規範版）

    規範核心：
    - reverse() / {% url %} 是否帶 prefix：只看 settings.FORCE_SCRIPT_NAME
    - 前端/模板組 URL：只看 request.script_name（唯一真相）
    - 少數需要外部 prefix：用 request.external_prefix（唯一欄位）
    - 不改 PATH_INFO，避免影響路由判斷
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Canonicalize duplicated slashes in URL path to avoid routing/static anomalies,
        # e.g. "/djangoai//" -> "/djangoai/".
        raw_path = request.META.get("PATH_INFO", "") or ""
        norm_path = re.sub(r"/{2,}", "/", raw_path)
        if norm_path and norm_path != raw_path:
            qs = request.META.get("QUERY_STRING", "") or ""
            target = norm_path + (f"?{qs}" if qs else "")
            return HttpResponseRedirect(target)

        external_prefix, source = _choose_external_prefix(request)
        request.proxy_prefix_source = source

        force_now = _norm_prefix(getattr(settings, "FORCE_SCRIPT_NAME", "") or "")

        # ✅ 有 FORCE_SCRIPT_NAME 時禁止再讓前端拼 prefix（防 /djangoai/djangoai）
        request.proxy_prefix = "" if force_now else external_prefix

        # ✅ 唯一對外 prefix 欄位
        request.external_prefix = external_prefix
        # ============================================================
        # Optional: strip prefix from PATH_INFO (IIS may not strip it)
        # - guarded by PROXY_PREFIX_WRITE_SCRIPT_NAME to avoid surprises
        # ============================================================
        if external_prefix and bool(getattr(settings, "PROXY_PREFIX_WRITE_SCRIPT_NAME", False)):
            raw_path = request.META.get("PATH_INFO", "") or ""
            new_path = _strip_prefix_path(raw_path, external_prefix)
            if new_path != raw_path:
                request.META["PATH_INFO"] = new_path
                try:
                    request.path_info = new_path  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    sn = request.META.get("SCRIPT_NAME", "") or ""
                    request.path = f"{sn}{new_path}"  # type: ignore[attr-defined]
                except Exception:
                    pass

        # ============================================================
        # ✅ 核心：固定同步 SCRIPT_NAME / request.script_name
        # - 只要 external_prefix 存在且 WRITE 開啟：一定寫回
        # - 不看 source（避免條件判斷造成漏寫）
        # ============================================================
        write_sn = bool(getattr(settings, "PROXY_PREFIX_WRITE_SCRIPT_NAME", False))
        if write_sn and external_prefix:
            request.META["SCRIPT_NAME"] = external_prefix

        # ✅ template 唯一真相：request.script_name
        try:
            request.script_name = request.META.get("SCRIPT_NAME", "") or external_prefix  # type: ignore[attr-defined]
        except Exception:
            pass

        # Debug log
        if bool(getattr(settings, "PROXY_PREFIX_DEBUG_LOG", False)):
            logger.info(
                "[proxy_prefix] source=%s external=%r force=%r cfg=%r SCRIPT_NAME=%r request.script_name=%r path=%s path_info=%s xfp=%r",
                source,
                external_prefix,
                getattr(settings, "FORCE_SCRIPT_NAME", ""),
                getattr(settings, "PROXY_PREFIX", ""),
                request.META.get("SCRIPT_NAME", ""),
                getattr(request, "script_name", ""),
                getattr(request, "path", ""),
                getattr(request, "path_info", ""),
                request.META.get("HTTP_X_FORWARDED_PREFIX", ""),
            )

        return self.get_response(request)


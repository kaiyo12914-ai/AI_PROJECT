from __future__ import annotations

from django.conf import settings
from django.shortcuts import render

from webapps.portal.acl import can_access
from webapps.portal.decorators import require_node
from webapps.portal.identity import resolve_effective_user_id
from webapps.vanna.vanna_adapter import VENDOR_ROOT, VENDOR_SRC, ensure_vanna_vendor_loaded


VANNA_ADMIN_USERS = {"h121356578"}


def _configured_vanna_admin_users() -> set[str]:
    raw = str(getattr(settings, "VANNA_ADMIN_USERS", "") or "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_vanna_admin(request) -> bool:
    user = getattr(request, "user", None)
    if bool(user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))):
        return True
    if can_access(user, "portal"):
        return True
    user_id = resolve_effective_user_id(request).strip().lower()
    return user_id in (VANNA_ADMIN_USERS | _configured_vanna_admin_users())


def _login_display_name(request) -> str:
    return str(
        getattr(request, "login_user_name", "")
        or getattr(request, "login_user", "")
        or resolve_effective_user_id(request)
        or "使用者"
    ).strip()


def _is_named_system_admin(request) -> bool:
    return resolve_effective_user_id(request).strip().lower() == "h121356578"


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
            "can_manage_vanna": is_vanna_admin(request),
            "login_display_name": _login_display_name(request),
            "is_named_system_admin": _is_named_system_admin(request),
        },
    )

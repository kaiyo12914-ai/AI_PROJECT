# webapps/doc/utils_login.py
from __future__ import annotations

import os

from django.http import HttpRequest
from webapps.common.login_utils import (
    get_login_user_idno,
    get_login_user_name,
    get_login_user_org,
)


def _env_bool(key: str, default: bool = False) -> bool:
    v = (os.getenv(key) or ("1" if default else "0")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def get_plant_arg(request: HttpRequest) -> str:
    """
    Read plant from request (GET, POST, or JSON body).
    """
    import json
    p = (request.GET.get("plant") or request.POST.get("plant") or "").strip()
    if not p:
        try:
            body = json.loads((request.body or b"").decode("utf-8") or "{}")
            p = (body.get("plant") or "").strip()
        except Exception:
            pass
    return p

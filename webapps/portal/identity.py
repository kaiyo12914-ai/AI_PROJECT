from __future__ import annotations

from typing import Any


def resolve_login_session_user_id(request: Any) -> str:
    """
    Resolve identity from middleware/session only.
    Priority:
    1) request.login_user
    2) request.session["login_user"]
    """
    login_user = str(getattr(request, "login_user", None) or "").strip()
    if login_user:
        return login_user

    session = getattr(request, "session", None)
    if session is not None:
        sess_login = str(session.get("login_user") or "").strip()
        if sess_login:
            return sess_login
    return ""


def resolve_effective_user_id(request: Any, user: Any = None) -> str:
    """
    Resolve effective user identity across middleware/session/auth layers.
    Priority:
    1) request.login_user
    2) request.session["login_user"]
    3) user.username (Django auth user)
    """
    login_user = resolve_login_session_user_id(request)
    if login_user:
        return login_user

    if user is None:
        user = getattr(request, "user", None)
    return str(getattr(user, "username", "") or "").strip()

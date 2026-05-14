# webapps/portal/decorators.py
from __future__ import annotations

import os
from functools import wraps
from typing import Callable, Iterable, Any, TypeVar, cast

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse, HttpRequest, HttpResponse

from webapps.portal.acl import can_access

T = TypeVar("T", bound=Callable[..., HttpResponse])


# ============================================================
# NO_PROXY helper
# ============================================================
def ensure_no_proxy(hosts: Iterable[str]) -> str:
    """
    把 hosts 合併進 NO_PROXY/no_proxy 環境變數（去重、保留原本項目）。
    """
    def _split_csv(s: str) -> list[str]:
        return [x.strip() for x in (s or "").split(",") if x.strip()]

    cur = _split_csv(os.getenv("NO_PROXY", "")) + _split_csv(os.getenv("no_proxy", ""))
    add = [h.strip() for h in hosts if (h or "").strip()]

    seen: set[str] = set()
    merged: list[str] = []
    for x in cur + add:
        if x not in seen:
            seen.add(x)
            merged.append(x)

    val = ",".join(merged)
    os.environ["NO_PROXY"] = val
    os.environ["no_proxy"] = val
    return val


# ============================================================
# ACL Decorator（依專案規範）
# - api=True 時：永遠回 JSON（不可回 HTML）
# - 未登入：401；無權限：403；ACL 錯誤：500
# - 兼容 fetch/Ajax：只要 Accept JSON / XRW / Content-Type JSON / /api/ 前綴，也視同 API 回 JSON
# ============================================================
def _wants_json(request: HttpRequest) -> bool:
    """
    判斷是否應回 JSON（符合規範：API/前端 fetch 不應收到 HTML）
    """
    accept = (request.headers.get("Accept") or "").lower()
    xrw = (request.headers.get("X-Requested-With") or "").lower()
    ctype = (request.headers.get("Content-Type") or "").lower()
    path = (request.path or "").lower()

    if "application/json" in accept:
        return True
    if "xmlhttprequest" in xrw:
        return True
    if "application/json" in ctype:
        return True
    if "/api/" in path:
        return True
    return False


def _json_acl_error(node: str) -> JsonResponse:
    return JsonResponse({"ok": False, "error": "ACL error", "node": node}, status=500)


def _json_denied(
    request: HttpRequest,
    node: str,
    *,
    status: int,
    reason: str,
) -> JsonResponse:
    """
    ✅ 規範：payload 要包含 debug 欄位（node / auth / username / login_user）
    這裡再補齊 path/method 方便前端與 log 對照。
    """
    user = getattr(request, "user", None)
    is_auth = bool(user and getattr(user, "is_authenticated", False))

    return JsonResponse(
        {
            "ok": False,
            "error": reason,                 # "Unauthorized" / "Forbidden"
            "node": node,
            "auth": is_auth,
            "is_authenticated": is_auth,      # 相容欄位
            "username": getattr(user, "username", None),
            "login_user": getattr(request, "login_user", None),
            "path": request.path,
            "method": request.method,
        },
        status=status,
    )


def _is_authenticated_user(user: Any) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


def _as_node_set(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        return {x.strip().lower() for x in raw.split(",") if x.strip()}
    if isinstance(raw, (list, tuple, set)):
        out: set[str] = set()
        for item in raw:
            s = str(item or "").strip().lower()
            if s:
                out.add(s)
        return out
    return set()


def _is_external_env() -> bool:
    env_name = str(
        getattr(settings, "ENV_NAME", "") or os.getenv("ENV", "")
    ).strip().upper()
    return env_name == "EXT"


def _is_internal_env() -> bool:
    env_name = str(
        getattr(settings, "ENV_NAME", "") or os.getenv("ENV", "")
    ).strip().upper()
    return env_name == "INT"


def _current_user_id(request: HttpRequest, user: Any) -> str:
    # Prefer login_user for intranet SSO/session identity.
    login_user = str(getattr(request, "login_user", None) or request.session.get("login_user") or "").strip()
    if login_user:
        return login_user
    return str(getattr(user, "username", "") or "").strip()


def _should_bypass_acl_group(node: str, user: Any, request: HttpRequest | None = None) -> bool:
    # In internal environment, allow ACL group bypass for selected users and nodes.
    # Default target: USER_ID=H121356578 on node=videolearning.
    if _is_internal_env() and request is not None:
        bypass_nodes_int = _as_node_set(getattr(settings, "PORTAL_ACL_BYPASS_NODES_INT", None))
        if not bypass_nodes_int:
            bypass_nodes_int = {"videolearning"}
        bypass_users_int = _as_node_set(getattr(settings, "PORTAL_ACL_BYPASS_USERS_INT", None))
        if not bypass_users_int:
            bypass_users_int = {"h121356578"}
        node_key = (node or "").strip().lower()
        user_id = _current_user_id(request, user).lower()
        has_identity = _is_authenticated_user(user) or bool(
            str(getattr(request, "login_user", None) or request.session.get("login_user") or "").strip()
        )
        if node_key in bypass_nodes_int and user_id in bypass_users_int and has_identity:
            return True

    # In external environment, skip ACL group check for selected nodes.
    if not _is_external_env():
        return False
    bypass_nodes = _as_node_set(getattr(settings, "PORTAL_ACL_BYPASS_NODES_EXT", None))
    if not bypass_nodes:
        bypass_nodes = {"doc"}
    if (node or "").strip().lower() not in bypass_nodes:
        return False
    # Bypass only the group check; keep authentication requirement.
    return _is_authenticated_user(user)


def require_node(node: str, api: bool = False) -> Callable[[T], T]:
    """
    ACL gate
    - node: ACL 節點名稱
    - api: True → 嚴格回 JSON（不可回 HTML）
    """
    def deco(view_func: T) -> T:
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            user = getattr(request, "user", None)
            wants_json = bool(api or _wants_json(request))
            is_auth = _is_authenticated_user(user)

            if _should_bypass_acl_group(node, user, request):
                return view_func(request, *args, **kwargs)

            # ✅ 關鍵：不要先擋未登入
            #   - ACL 關閉時 can_access() 會回 True（全部放行，含未登入）
            #   - PUBLIC 節點 can_access() 也會放行（含未登入）
            try:
                allowed = bool(can_access(user, node))
            except Exception:
                if wants_json:
                    return _json_acl_error(node)
                return HttpResponseForbidden("Forbidden")

            if allowed:
                return view_func(request, *args, **kwargs)

            # ✅ 拒絕：依登入狀態決定 401/403（API 必須 JSON）
            if wants_json:
                return _json_denied(
                    request,
                    node,
                    status=403 if is_auth else 401,
                    reason="Forbidden" if is_auth else "Unauthorized",
                )

            return HttpResponseForbidden("Forbidden")

        return cast(T, _wrapped)

    return deco

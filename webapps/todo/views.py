from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from webapps.portal.decorators import require_node

DEFAULT_TODO_SOURCE_URL = "https://www.mpc.mil.tw/notificationsingleton/WebService/Notification/GetPersonalToDo.ashx"


def _env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d).strip()


def _norm_base(path: str) -> str:
    s = (path or "").strip()
    if not s:
        return ""
    if not s.startswith("/"):
        s = "/" + s
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return "" if s == "/" else s


def _calc_app_base_url(request) -> str:
    script = _norm_base(getattr(request, "script_name", "") or request.META.get("SCRIPT_NAME", ""))
    return _norm_base((script + "/todo").replace("//", "/"))


def _coerce_bool(v: str | None, default: bool = True) -> bool:
    s = (v or "").strip().lower()
    if not s:
        return default
    return s in ("1", "true", "yes", "y", "on")


def _extract_todo_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []

    if isinstance(payload, list):
        out: list[dict[str, Any]] = []
        for i, row in enumerate(payload, start=1):
            if isinstance(row, dict):
                out.append(row)
            else:
                out.append({"task_name": str(row), "index": i})
        return out

    if isinstance(payload, dict):
        for key in ("todos", "items", "data", "results", "records", "result", "list", "rows"):
            v = payload.get(key)
            if isinstance(v, list):
                return _extract_todo_list(v)
            if isinstance(v, dict):
                for sub_key in ("todos", "items", "data", "results", "records", "result", "list", "rows"):
                    sub_v = v.get(sub_key)
                    if isinstance(sub_v, list):
                        return _extract_todo_list(sub_v)
        return [payload]

    if isinstance(payload, str):
        lines = [x.strip() for x in payload.splitlines() if x.strip()]
        return [{"task_name": x, "index": i + 1} for i, x in enumerate(lines)]

    return []


def _pick(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _task_name(item: dict[str, Any]) -> str:
    return _pick(item, "TaskName", "task_name", "name", "title", "subject", "todo", "task", default="未命名待辦")


def _notification_type_name(item: dict[str, Any]) -> str:
    return _pick(
        item,
        "NotifictionTypeName",  # upstream typo variant
        "NotificationTypeName",
        "notificationTypeName",
        "notification_type_name",
        default="",
    ).strip()


def _is_excluded_notification(item: dict[str, Any]) -> bool:
    return _notification_type_name(item) == "宣教宣導"


def _parse_deadline_datetime(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None

    m = re.search(r"/Date\((\d+)\)/", s)
    if m:
        try:
            ts_ms = int(m.group(1))
            return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.get_current_timezone())
        except Exception:
            return None

    normalized = s.replace("Z", "+00:00").replace("/", "-")
    for parser in (
        lambda x: datetime.fromisoformat(x),
        lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S"),
        lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M"),
        lambda x: datetime.strptime(x, "%Y-%m-%d"),
    ):
        try:
            dt = parser(normalized)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.get_current_timezone())
            return timezone.localtime(dt, timezone.get_current_timezone())
        except Exception:
            continue
    return None


def _find_deadline(item: dict[str, Any]) -> datetime | None:
    raw = _pick(
        item,
        "DeadlineDate",
        "deadlineDate",
        "deadline_date",
        "DueDate",
        "due_date",
        "EndDate",
        "end_date",
        default="",
    )
    return _parse_deadline_datetime(raw)


def _build_deadline_warnings(todos: list[dict[str, Any]]) -> list[str]:
    now = timezone.localtime()
    rows: list[tuple[datetime, str]] = []

    for i, item in enumerate(todos, start=1):
        deadline = _find_deadline(item)
        if deadline is None:
            continue

        delta_hours = (deadline - now).total_seconds() / 3600.0
        name = _task_name(item)
        notif_type = _notification_type_name(item) or "未分類"
        when_text = deadline.strftime("%Y-%m-%d %H:%M")

        if delta_hours < 0:
            msg = f"[逾期] #{i} {name}（類型:{notif_type}）期限:{when_text}，請立即處理並回報。"
        elif delta_hours <= 24:
            msg = f"[高] #{i} {name}（類型:{notif_type}）將於 24 小時內到期（{when_text}），建議優先完成。"
        elif delta_hours <= 72:
            msg = f"[中] #{i} {name}（類型:{notif_type}）將於 3 天內到期（{when_text}），請排入本日處理。"
        else:
            continue
        rows.append((deadline, msg))

    rows.sort(key=lambda x: x[0])
    return [msg for _, msg in rows]


@require_node("todo")
def todo_page(request):
    return render(
        request,
        "todo/index.html",
        {
            "app_base_url": _calc_app_base_url(request),
            "today": timezone.localdate().isoformat(),
        },
    )


@require_GET
@require_node("todo", api=True)
def api_fetch_todos(request):
    source_url = _env("TODO_SOURCE_URL", DEFAULT_TODO_SOURCE_URL)
    if not source_url:
        return JsonResponse({"ok": False, "error": "缺少待辦來源 URL"}, status=400)

    login_user = (getattr(request, "login_user", "") or "").strip()
    timeout_sec = int(_env("TODO_FETCH_TIMEOUT_SEC", "15") or 15)
    verify_ssl = _coerce_bool(_env("TODO_FETCH_VERIFY_SSL"), default=True)

    if "{login_user}" in source_url:
        source_url = source_url.replace("{login_user}", login_user)
    if "{user_id}" in source_url:
        source_url = source_url.replace("{user_id}", login_user)

    params: dict[str, str] = {}
    if ("{login_user}" not in source_url) and ("{user_id}" not in source_url):
        params["login_user"] = login_user
        params["user_id"] = login_user

    try:
        resp = requests.get(source_url, params=params, timeout=timeout_sec, verify=verify_ssl)
        resp.raise_for_status()
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"待辦資料讀取失敗: {e}"}, status=502)

    try:
        payload = resp.json()
    except Exception:
        payload = resp.text

    todos = _extract_todo_list(payload)
    filtered_todos = [x for x in todos if isinstance(x, dict) and not _is_excluded_notification(x)]
    warnings = _build_deadline_warnings(filtered_todos)

    return JsonResponse(
        {
            "ok": True,
            "count": len(filtered_todos),
            "todos_text": json.dumps(filtered_todos, ensure_ascii=False, indent=2),
            "todos_raw": filtered_todos,
            "warning_count": len(warnings),
            "warning_lines": warnings,
            "warning_text": "\n".join(warnings) if warnings else "目前無 3 天內到期或逾期事項。",
        },
        status=200,
    )


@csrf_exempt
@require_node("todo", api=True)
def api_plan_tasks(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    payload: dict[str, Any] = {}
    if request.content_type and "application/json" in request.content_type.lower():
        try:
            payload = json.loads((request.body or b"").decode("utf-8") or "{}")
        except Exception:
            payload = {}
    else:
        payload = request.POST.dict()

    todos_any: Any = payload.get("todos_json")
    if todos_any is None:
        todos_any = payload.get("todos")
    if todos_any is None or (isinstance(todos_any, str) and not todos_any.strip()):
        return JsonResponse({"ok": False, "error": "缺少待辦資料"}, status=400)

    if isinstance(todos_any, str):
        try:
            parsed = json.loads(todos_any)
        except Exception:
            return JsonResponse({"ok": False, "error": "todos_json 必須是合法 JSON"}, status=400)
    else:
        parsed = todos_any

    todos = _extract_todo_list(parsed)
    filtered_todos = [x for x in todos if isinstance(x, dict) and not _is_excluded_notification(x)]
    warnings = _build_deadline_warnings(filtered_todos)
    plan_text = "\n".join(warnings) if warnings else "目前無 3 天內到期或逾期事項。"

    return JsonResponse(
        {
            "ok": True,
            "plan_text": plan_text,
            "warning_count": len(warnings),
            "fallback": False,
        },
        status=200,
    )

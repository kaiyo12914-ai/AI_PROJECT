from __future__ import annotations

import json
import os
from typing import Any

import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from langchain_core.prompts import ChatPromptTemplate

from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node


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
        out = []
        for i, row in enumerate(payload, start=1):
            if isinstance(row, dict):
                out.append(row)
            else:
                out.append({"task_name": str(row), "index": i})
        return out

    if isinstance(payload, dict):
        for key in ("todos", "items", "data", "results", "records"):
            v = payload.get(key)
            if isinstance(v, list):
                return _extract_todo_list(v)
        return [payload]

    if isinstance(payload, str):
        lines = [x.strip() for x in payload.splitlines() if x.strip()]
        return [{"task_name": x, "index": i + 1} for i, x in enumerate(lines)]

    return []


def _task_name(item: dict[str, Any]) -> str:
    for key in ("task_name", "name", "title", "subject", "todo", "task"):
        v = item.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return "未命名任務"


def _pick(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _format_todos_for_prompt(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return "無"

    lines: list[str] = []
    for i, item in enumerate(todos, start=1):
        name = _task_name(item)
        due = _pick(item, "due_date", "deadline", "due", "end_date", default="未提供")
        priority = _pick(item, "priority", "importance", "level", default="未提供")
        status = _pick(item, "status", "progress", "state", default="未提供")
        est = _pick(item, "estimate_hours", "estimate", "duration", "work_hours", default="未提供")
        dep = _pick(item, "depends_on", "dependency", default="無")
        lines.append(
            f"{i}. 任務={name}｜截止={due}｜重要性={priority}｜狀態={status}｜預估工時={est}｜依賴={dep}"
        )
    return "\n".join(lines)


def _llm_to_text(resp: Any) -> str:
    if resp is None:
        return ""
    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                out.append(str(part.get("text") or part.get("content") or ""))
        return "".join(out).strip()
    return str(resp).strip()


def _build_schedule_prompt(
    todos: str,
    available_slots: str,
    user_preferences: str,
    current_date: str,
) -> str:
    return f"""你是一位「智慧排程與任務管理助手」，你的目標是協助使用者根據目前待辦事項、可用時間與工作習慣，自動安排工作順序，並提供提醒與調整建議。

請根據輸入資料進行分析，並只輸出與排程、提醒、優先順序相關的結果，不要輸出多餘說明。

【任務目標】
1. 判斷任務優先順序
2. 安排今日或未來幾日的執行時段
3. 避免時間衝突與過度排程
4. 提醒即將到期、延遲、高重要性任務
5. 提供清楚且可執行的調整建議

【優先判斷規則】
- 優先處理「即將到期且高重要性」任務
- 已逾期任務必須優先標記
- 重要但不緊急的任務，優先安排在高專注時段
- 若任務可拆分，請主動拆成較小步驟
- 若同時存在多個高優先任務，依下列順序排序：
  1. 截止日期較近
  2. 重要性較高
  3. 有依賴關係者優先
  4. 預估工時較長且接近截止者優先
- 若當日可用時間不足，請主動延後低優先任務，並說明原因

【排程規則】
- 任務不得安排在可用時段之外
- 任務總工時不得超過當日可用時間
- 高專注任務優先安排在使用者偏好的高效時段
- 每段任務之間預留 5 至 15 分鐘緩衝
- 相似任務可集中安排以降低切換成本
- 所有任務必須在截止日前安排完成
- 若任務工時過長，請拆成多段安排
- 若資料不足，請依現有資訊做最合理安排，不可虛構不存在的時間

【提醒規則】
請特別提醒以下任務：
1. 今日到期
2. 明日到期
3. 已逾期
4. 高重要性但尚未開始
5. 已安排但進度可能落後

【輸出要求】
- 回答必須簡潔、具體、可執行
- 不要重複輸入資料
- 不要輸出推理過程
- 若無資料，請明確寫「無」
- 若時間不足，請明確指出哪些任務無法安排完成

【輸出格式】
一、任務優先順序
- 任務名稱｜優先級｜原因

二、建議排程
- 日期：
  - 時段：任務名稱（預估工時）
  - 時段：任務名稱（預估工時）

三、提醒事項
- 提醒1
- 提醒2

四、調整建議
- 建議1
- 建議2

【輸入資料】
待辦事項：
{todos}

可用時間：
{available_slots}

使用者偏好：
{user_preferences}

目前日期：
{current_date}
""".strip()


def _fallback_plan_text() -> str:
    return (
        "一、任務優先順序\n"
        "- 無｜無｜目前無法取得可排序資料\n\n"
        "二、建議排程\n"
        "- 日期：\n"
        "  - 時段：無（無）\n\n"
        "三、提醒事項\n"
        "- 無\n\n"
        "四、調整建議\n"
        "- 請先確認待辦來源 URL 與資料格式。"
    )


@require_node("todo")
def todo_page(request):
    return render(
        request,
        "todo/index.html",
        {
            "app_base_url": _calc_app_base_url(request),
            "default_todo_source_url": (os.environ.get("TODO_SOURCE_URL") or "").strip(),
            "today": timezone.localdate().isoformat(),
        },
    )


@require_GET
@require_node("todo", api=True)
def api_fetch_todos(request):
    source_url = (request.GET.get("source_url") or os.environ.get("TODO_SOURCE_URL") or "").strip()
    if not source_url:
        return JsonResponse({"ok": False, "error": "請提供待辦來源 URL"}, status=400)

    login_user = (getattr(request, "login_user", "") or "").strip()
    timeout_sec = int(os.environ.get("TODO_FETCH_TIMEOUT_SEC", "15") or 15)
    verify_ssl = _coerce_bool(os.environ.get("TODO_FETCH_VERIFY_SSL"), default=True)

    # Optional placeholder replacement.
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
        return JsonResponse({"ok": False, "error": f"待辦取得失敗：{e}"}, status=502)

    try:
        payload = resp.json()
    except Exception:
        payload = resp.text

    todos = _extract_todo_list(payload)
    todos_text = _format_todos_for_prompt(todos)
    return JsonResponse(
        {
            "ok": True,
            "count": len(todos),
            "todos_text": todos_text,
            "todos_raw": todos,
            "source_url": source_url,
        },
        status=200,
    )


@csrf_exempt
@require_node("todo", api=True)
def api_plan_tasks(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    todos = ""
    available_slots = ""
    user_preferences = ""
    current_date = timezone.localdate().isoformat()

    if request.content_type and "application/json" in request.content_type.lower():
        try:
            body = json.loads((request.body or b"").decode("utf-8") or "{}")
        except Exception:
            body = {}
        todos = str(body.get("todos") or "").strip()
        available_slots = str(body.get("available_slots") or "").strip()
        user_preferences = str(body.get("user_preferences") or "").strip()
        current_date = str(body.get("current_date") or current_date).strip()
    else:
        todos = (request.POST.get("todos") or "").strip()
        available_slots = (request.POST.get("available_slots") or "").strip()
        user_preferences = (request.POST.get("user_preferences") or "").strip()
        current_date = (request.POST.get("current_date") or current_date).strip()

    if not todos:
        return JsonResponse({"ok": False, "error": "請先提供待辦事項"}, status=400)

    max_chars = int(os.environ.get("TODO_PROMPT_MAX_CHARS", "12000") or 12000)
    todos = todos[:max_chars]
    available_slots = (available_slots or "無")[:max_chars]
    user_preferences = (user_preferences or "無")[:max_chars]

    prompt = _build_schedule_prompt(
        todos=todos,
        available_slots=available_slots,
        user_preferences=user_preferences,
        current_date=current_date,
    )

    try:
        llm = get_chat_model(temperature=0.2, timeout=120)
        chat_prompt = ChatPromptTemplate.from_messages([("user", prompt)])
        plan_text = _llm_to_text(llm.invoke(chat_prompt.format_messages()))
        if not plan_text:
            plan_text = _fallback_plan_text()
        return JsonResponse({"ok": True, "plan_text": plan_text, "fallback": False}, status=200)
    except Exception:
        return JsonResponse({"ok": True, "plan_text": _fallback_plan_text(), "fallback": True}, status=200)


from __future__ import annotations

import json
import os
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from langchain_core.prompts import ChatPromptTemplate
from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node


ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_MB = 10


@require_node("graph")
def graph_page(request):
    return render(request, "graph2doc/index.html")


def _generate_ai_text(title: str, notes: str, has_image: bool) -> str:
    llm = get_chat_model(temperature=0.2, timeout=120)

    system = (
        "你是政府/製造業場域的文字整理助理。"
        "請用繁體中文。"
        "不要提到你是AI或模型。"
        "不要輸出章節標題或多餘說明，只輸出最後要給使用者貼上的文字內容。"
    )

    user = (
        "請把以下資訊整理成一段可直接貼上的「純文字」。\n"
        "限制：\n"
        "1) 不要寫章節（例如 一、二、三）\n"
        "2) 不要解釋你在做什麼\n"
        "3) 用條列或短句即可\n\n"
        f"- 標題：{title}\n"
        f"- 有無附圖：{'有' if has_image else '無'}\n"
        f"- 補充說明：{notes if notes else '（無）'}\n"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("user", user),
    ])

    resp = llm.invoke(prompt.format_messages())
    out = getattr(resp, "content", None) or str(resp)
    return (out or "").strip()


def _safe_filename(name: str) -> str:
    # 只留基本字元，避免路徑/控制字元
    name = os.path.basename(name or "upload")
    cleaned = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    return ("".join(cleaned) or "upload").strip()


@csrf_exempt
@require_node("graph", api=True)
def graph_build_text(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    title = (request.POST.get("title") or "圖表文字整理").strip()
    notes = (request.POST.get("notes") or "").strip()
    img = request.FILES.get("image")

    saved_img_path = None

    if img:
        if getattr(img, "size", 0) > MAX_IMAGE_MB * 1024 * 1024:
            return JsonResponse({"ok": False, "error": f"圖片過大（上限 {MAX_IMAGE_MB}MB）"}, status=400)

        orig = _safe_filename(getattr(img, "name", "image.png"))
        _, ext = os.path.splitext(orig.lower())
        if ext not in ALLOWED_IMAGE_EXTS:
            return JsonResponse(
                {"ok": False, "error": f"不支援的圖片格式（允許：{', '.join(sorted(ALLOWED_IMAGE_EXTS))}）"},
                status=400,
            )

        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        img_name = f"{uuid.uuid4().hex}_{orig}"
        saved_img_path = os.path.join(upload_dir, img_name)

        with open(saved_img_path, "wb") as f:
            for chunk in img.chunks():
                f.write(chunk)

    try:
        text = _generate_ai_text(title=title, notes=notes, has_image=bool(saved_img_path))
        return JsonResponse({"ok": True, "text": text}, status=200)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def _build_summary_prompt(doc_text: str) -> str:
    return f"""你是一位專業的文件分析與摘要專家，請根據以下文件內容，產出結構化重點摘要。

【任務要求】
1. 提取文件的核心主題與目的
2. 梳理關鍵重點（條列式）
3. 保留重要數據、結論與專有名詞
4. 避免冗長敘述，不要逐句改寫
5. 使用清晰、簡潔、專業的語言

【輸出格式】
請嚴格依照以下結構輸出：

一、文件主題：
（用一句話說明）

二、核心摘要：
（3～5句重點總結）

三、關鍵重點：
- 重點1
- 重點2
- 重點3
（視內容增加）

四、重要數據 / 結論：
- （列出關鍵數據或結論）

五、可行動建議（若適用）：
- （可執行的建議）

【文件內容】
{doc_text}
""".strip()


def _llm_to_text(resp) -> str:
    if resp is None:
        return ""

    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                out.append(str(part.get("text") or part.get("content") or ""))
        return "".join(out).strip()

    return str(resp).strip()


@csrf_exempt
@require_node("graph", api=True)
def graph_summary(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    text = ""
    if request.content_type and "application/json" in request.content_type.lower():
        try:
            body = json.loads((request.body or b"").decode("utf-8") or "{}")
            text = str(body.get("text") or "").strip()
        except Exception:
            text = ""
    else:
        text = (request.POST.get("text") or "").strip()

    if not text:
        return JsonResponse({"ok": False, "error": "請先提供文件內容"}, status=400)

    max_chars = int(os.environ.get("GRAPH_SUMMARY_MAX_CHARS", "12000") or 12000)
    if len(text) > max_chars:
        text = text[:max_chars]

    try:
        llm = get_chat_model(temperature=0.2, timeout=120)
        summary = _llm_to_text(llm.invoke(_build_summary_prompt(text)))
        if not summary:
            return JsonResponse({"ok": False, "error": "摘要回傳為空"}, status=502)
        return JsonResponse({"ok": True, "summary": summary}, status=200)
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"摘要失敗：{e}"}, status=500)

from __future__ import annotations

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

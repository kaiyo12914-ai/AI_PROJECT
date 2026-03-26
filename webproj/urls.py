# webproj/urls.py
from __future__ import annotations

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as static_serve
from django.views.generic import RedirectView

urlpatterns = [
    # ============================================================
    # ✅ Compatibility redirect (avoid legacy /portal/ 404)
    # - 專案規範：Portal 唯一入口是根目錄 "/"
    # - 仍可能有人用舊收藏 /portal/（或外部 /djangoai/portal/）
    # - 這裡統一導回 "/"，避免使用者以為系統壞掉
    # ============================================================
    path("portal/", RedirectView.as_view(url="/", permanent=False)),

    path("admin/", admin.site.urls),

    # ============================================================
    # Subsystems (NO proxy prefix here)
    # - 專案規範：Django URLconf 永遠不包含 /djangoai 或 /comment 這類反代前綴
    # ============================================================
    path("translator/", include("webapps.translator.urls")),
    path("comment/", include("webapps.comment.urls")),
    path("student/", include("webapps.student.urls")),
    path("meetingreply/", include("webapps.meetingreply.urls")),
    path("doc/", include("webapps.doc.urls")),
    path("graph/", include("webapps.graph2doc.urls")),
    path("text2pptx/", include("webapps.text2pptx.urls")),
    path("tts/", include("webapps.tts.urls")),
    path("api/", include("webapps.llm.urls")),
    path("pdf/", include("webapps.pdf.urls")),
    path("todo/", include("webapps.todo.urls")),
    path("rag/", include("webapps.rag_oracle.urls")),
    path("excelproc/", include("webapps.excelproc.urls")),

    # ============================================================
    # Portal (single canonical entry)
    # - 專案規範：避免雙入口造成路徑拼接/導覽混亂
    # ============================================================
    path("", include("webapps.portal.urls")),
]

# ============================================================
# DEBUG media
# - 反代環境：由反代負責把 /djangoai/media/ 對應到實體目錄
# - Django 內部：只提供 /media/（不要在這裡加 /djangoai）
# ============================================================
if settings.DEBUG:
    # 支援 DEBUG 模式下由 Django 服務靜態檔案 (即使是用 Waitress)
    # 注意：STATIC_URL 已經包含 PROXY_PREFIX (例如 /djangoai/static/)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_STATIC_WITH_DJANGO", False):
    # Django 6 在 DEBUG=False 時 static(...) 不會產生路由，這裡補顯式路由供內網直連測試。
    static_prefix = (settings.STATIC_URL or "/static/").strip("/")
    media_prefix = (settings.MEDIA_URL or "/media/").strip("/")
    urlpatterns += [
        re_path(rf"^{static_prefix}/(?P<path>.*)$", static_serve, {"document_root": settings.STATIC_ROOT}),
        re_path(rf"^{media_prefix}/(?P<path>.*)$", static_serve, {"document_root": settings.MEDIA_ROOT}),
    ]

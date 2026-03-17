# webapps/doc/urls.py
from __future__ import annotations

from django.urls import path

from webapps.doc.views_sybase_blob import (
    api_sybase_blob_download,
    api_sybase_blob_stash,
)
from . import views

# ============================================================
# 規範註解（Mandatory）
# 1) urls.py 路徑不得包含 proxy prefix（例如 /djangoai、/comment 等）
#    - 反向代理 prefix 一律由 IIS/Caddy + Django FORCE_SCRIPT_NAME / request.script_name 處理
# 2) page 與 api 必須分層：
#    - page：""（入口頁）
#    - api：一律放在 "api/..." 底下，避免與 page/舊路由互相干擾
# 3) URL name 必須唯一（同 app 內不可重複），且需與 template/JS 使用的 name 完全一致
# 4) 不保留 legacy alias（避免 reverse 指到錯的 endpoint 或 name 互撞）
# ============================================================

app_name = "doc"

urlpatterns = [
    # =========================================================
    # page
    # =========================================================
    # ✅ 入口頁（統一名稱：doc_page）
    path("", views.index, name="doc_page"),
    path("templates/", views.templates_manage, name="templates_manage"),
    path("sybase-query/", views.sybase_query_page, name="sybase_query_page"),

    # =========================================================
    # templates / generate（✅ 新式 API：避免與頁面/舊路由互相干擾）
    # =========================================================
    path("api/templates/", views.api_templates, name="api_templates"),
    path("api/templates/<int:tpl_id>/", views.api_template_item, name="api_template_item"),
    path("api/generate/", views.api_generate, name="api_generate"),
    path("api/draft_reply/", views.api_draft_reply, name="api_draft_reply"),

    # =========================================================
    # attachments（✅ 新式 API）
    # =========================================================
    path("api/parse/", views.api_parse_attachments, name="api_parse_attachments"),
    path("api/parse_focus/", views.api_parse_attachments_focus, name="api_parse_attachments_focus"),
    path("api/todo/lookup/", views.api_todo_lookup, name="api_todo_lookup"),

    # =========================================================
    # Sybase 來文（✅ 新式 API：路徑固定在 api/sybase/...）
    # ✅ name 採 template/JS 既用的 incoming_*，避免前後端 name 對不起來
    # =========================================================
    path("api/sybase/incoming/lookup/", views.incoming_lookup, name="incoming_lookup"),
    path("api/sybase/incoming/files/", views.incoming_files, name="incoming_files"),
    path("api/sybase/incoming/file/", views.incoming_file_query, name="incoming_file_query"),
    path("api/sybase/incoming/file/<str:attach_key>/", views.incoming_file, name="incoming_file"),
    path("api/sybase/query/search/", views.api_sybase_query_search, name="api_sybase_query_search"),
    path("api/sybase/query/file/", views.api_sybase_query_file, name="api_sybase_query_file"),
    path("api/sybase/query/preview/", views.api_sybase_query_preview, name="api_sybase_query_preview"),

    # =========================================================
    # Sybase 既有公文 -> 範例庫（轉入範例）
    # =========================================================
    path("api/sybase/template/import/", views.api_import_template_from_sybase, name="api_sybase_template_import"),
    # alias: import file download (DF/EF via attach_key)
    path("api/sybase/import/file/<str:attach_key>/", views.incoming_file, name="import_file"),

    # =========================================================
    # Sybase BLOB 收納/下載（供附件重點解析與使用者下載）
    # =========================================================
    path("api/sybase/blob/stash/", api_sybase_blob_stash, name="api_sybase_blob_stash"),
    path("api/sybase/blob/download/<str:token>/", api_sybase_blob_download, name="api_sybase_blob_download"),
]

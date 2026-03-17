# webapps/doc/views.py
from __future__ import annotations

# ============================================================
# 規範註解（Mandatory）
# 1) 本檔案僅作為「對外匯出（re-export）」彙整入口：
#    - urls.py 只 import webapps.doc.views，不跨模組亂抓，避免循環依賴與互相干擾
# 2) views.py 不寫業務邏輯、不在此建立 DB/LLM 連線；邏輯分散到 views_* 子模組
# 3) re-export 名稱需穩定且唯一，避免與其他 app/views 名稱衝突
# 4) Sybase incoming 使用固定介面（incoming_lookup/incoming_files/incoming_file）
# ============================================================

# ============================================================
# Page
# ============================================================
from webapps.doc.views_pages import index, templates_manage

# ============================================================
# APIs：templates / generate / parse
# ============================================================
from webapps.doc.views_templates import api_templates, api_template_item
from webapps.doc.views_generate import api_generate
from webapps.doc.views_parse import api_parse_attachments, api_parse_attachments_focus
from webapps.doc.views_draft_reply import api_draft_reply
from webapps.doc.views_todo import api_todo_lookup

# ============================================================
# Sybase incoming（for urls.py compatibility）
# ============================================================
from webapps.doc.sybase_incoming import incoming_lookup, incoming_files, incoming_file, incoming_file_query

# ============================================================
# Sybase -> Template import
# ============================================================
from webapps.doc.views_sybase_import import api_import_template_from_sybase
from webapps.doc.views_sybase_query import (
    sybase_query_page,
    api_sybase_query_search,
    api_sybase_query_file,
    api_sybase_query_preview,
)

# ============================================================
# Public exports（可選，但可讓 IDE/linters 更穩）
# ============================================================
__all__ = [
    # page
    "index",
    "templates_manage",
    # apis
    "api_templates",
    "api_template_item",
    "api_generate",
    "api_parse_attachments",
    "api_parse_attachments_focus",
    "api_draft_reply",
    "api_todo_lookup",
    # sybase incoming
    "incoming_lookup",
    "incoming_files",
    "incoming_file",
    "incoming_file_query",
    # sybase import
    "api_import_template_from_sybase",
    # sybase workstation query
    "sybase_query_page",
    "api_sybase_query_search",
    "api_sybase_query_file",
    "api_sybase_query_preview",
]

# AI_TOOLS Project Architecture and Functional Analysis

- Scope path: `h:\AI\AI_TOOLS`
- Generated at: 2026-03-19 11:21:15
- Purpose: project handoff document for Python + Django maintenance and onboarding.

## 1) Project Overview
- Framework: Django 6.0.
- Data: SQLite + Oracle/SQL Server/Sybase via DB Factory.
- LLM: OPENAI/GOOGLE/OLLAMA via llm_factory.
- Vector store: ChromaDB.
- Run: `python manage.py runserver 8000`.

## 2) Directory Tree
```text
AI_TOOLS/
?? manage.py
?? .env
?? webproj/
?? webapps/
?  ?? portal / doc / meetingreply / rag_oracle
?  ?? translator / comment / student
?  ?? tts / text2pptx / pdf / graph2doc / excelproc
?  ?? database
?? static / staticfiles
?? media
?? tools
```

## 3) App Functional Analysis
- __pycache__
- comment
- common
- database
- doc
- excelproc
- graph2doc
- llm
- meetingreply
- pdf
- piper
- portal
- rag_oracle
- repositories
- services
- student
- tests
- text2pptx
- translator
- tts

## 4) URL Routing and Major APIs
- `/` -> portal
- `/doc/` -> doc APIs (generate/parse/sybase)
- `/meetingreply/` -> todo/rag/reply
- `/rag/` -> health/ask
- `/api/` -> llm chat/translate

## 5) Core Models and Data Flow
- `PortalUsageLog` in `webapps/portal/models.py`.
- `DocumentTemplate` in `webapps/doc/models.py`.
- Data flow: request -> middleware -> app views -> db_factory/llm_factory -> response.

## 6) Background Jobs / Schedules
- `webapps/doc/management/commands/seed_doc_templates.py`
- `webapps/rag_oracle/management/commands/rag_sync.py`
- `webapps/rag_oracle/management/commands/sync_sqlserver_to_chroma.py`
- No Celery config detected; currently command/script driven.

## 7) External Dependencies
- DB drivers: `oracledb`, `pyodbc`.
- LLM providers: OpenAI, Google, Ollama.
- Vector DB: chromadb.
- Serving stack available: waitress/uvicorn.

## 8) Settings and Deployment Notes
- Main settings file: `webproj/settings.py`.
- Uses `.env` + optional `DB_FACTORY.MD` overrides.
- Proxy keys: `PROXY_PREFIX`, `FORCE_SCRIPT_NAME`, `TRUST_X_FORWARDED_PREFIX`.
- Static/media keys: `STATIC_ROOT`, `MEDIA_ROOT`.

## 9) Testing and Quality Status
- Multiple script-style tests exist (`test_*.py`, `webapps/tests/*`).
- No standardized pytest/mypy/ruff config found.
- Recommend CI baseline: pytest + lint + type checks.

## 10) Risks and Technical Debt
- High: `.env.example` missing.
- High: DEBUG flags enabled in `.env`.
- Medium: many external dependencies require robust health checks.
- Medium: test suite is not yet standardized.

## 11) Handoff Plan for Week 1
1. Create `.env.example` (no real secrets).
2. Run `python manage.py check` and `python manage.py migrate`.
3. Verify portal/doc/meetingreply/rag e2e flows.
4. Verify proxy and auth/ACL behavior.
5. Add CI and consolidate requirements.

## 12) .env Parameter Reference
- Runtime variables detected: 104
- Variables defined in `.env`: 39
- Runtime variables missing in `.env`: 69

| Name | Required | Default | Purpose | Impact Files | Sample | Risk |
|---|---|---|---|---|---|---|
| ALLOWED_HOSTS | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Medium |
| API_CONTEXT_PATH | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/rag_oracle/*; webapps/meetingreply/views.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| CHROMA_DIR | N | (not explicitly fixed in code; environment-dependent) | RAG/vector store configuration | webapps/rag_oracle/*; webapps/meetingreply/views.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| CHROMA_PERSIST_DIR | N | (not explicitly fixed in code; environment-dependent) | RAG/vector store configuration | webapps/rag_oracle/*; webapps/meetingreply/views.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| CSRF_COOKIE_PATH | N | (not explicitly fixed in code; environment-dependent) | Cookie/CSRF security settings | webproj/settings.py; webapps/portal/middleware*.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Medium |
| CSRF_COOKIE_SAMESITE | N | (not explicitly fixed in code; environment-dependent) | Cookie/CSRF security settings | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| CSRF_COOKIE_SECURE | N | (not explicitly fixed in code; environment-dependent) | Cookie/CSRF security settings | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| CSRF_TRUSTED_ORIGINS | N | (not explicitly fixed in code; environment-dependent) | Cookie/CSRF security settings | webproj/settings.py; webapps/portal/middleware*.py | 1 | Medium |
| DB_FACTORY_MD_PATH | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| DEBUG | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 1 | Medium |
| DEV_LOGIN_NAME | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | example_value | Medium |
| DEV_LOGIN_USER | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 1 | Medium |
| DJANGO_DEBUG | N | (not explicitly fixed in code; environment-dependent) | Application setting | webproj/settings.py; webapps/portal/middleware*.py | 1 | Medium |
| DJANGO_LOG_LEVEL | N | INFO | Application setting | webproj/settings.py; webapps/portal/middleware*.py | example_value | Low |
| DJANGO_SECRET_KEY | Y | (not explicitly fixed in code; environment-dependent) | Credential/secret | webproj/settings.py; webapps/portal/middleware*.py | ****** | High |
| DOC_API_DEBUG | N | (not explicitly fixed in code; environment-dependent) | Document module behavior | webapps/doc/views_*.py; webapps/doc/services/* | 1 | Medium |
| DOC_DEFAULT_PLANT | N | (not explicitly fixed in code; environment-dependent) | Document module behavior | webapps/doc/views_*.py; webapps/doc/services/* | example_value | Low |
| DOC_QUERY_ALLOWED_IPS | N | (not explicitly fixed in code; environment-dependent) | Document module behavior | webapps/doc/views_*.py; webapps/doc/services/* | example_value | Low |
| DOC_QUERY_TRUST_X_FORWARDED_FOR | N | (not explicitly fixed in code; environment-dependent) | Document module behavior | webapps/doc/views_*.py; webapps/doc/services/* | 1 | Low |
| DOC_TPL_SUFFIX_MAX_TRY | N | (not explicitly fixed in code; environment-dependent) | Document module behavior | webapps/doc/views_*.py; webapps/doc/services/* | 10 | Low |
| ENV | Y | EXT | Application setting | Cross-module usage | example_value | Low |
| ENV_PATH | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| FILE_CHARSET | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | example_value | Low |
| FORCE_SCRIPT_NAME | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | example_value | Low |
| GOOGLE_API_KEY | Y | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | ****** | High |
| GOOGLE_MODEL | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| LANGCHAIN_OLLAMA_MODEL | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| LANGCHAIN_TEMPERATURE | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | example_value | Low |
| MEDIA_ROOT | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | example_value | Low |
| MOCK_DB_JSON | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| MODEL_API_KEY | Y | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | ****** | High |
| MODEL_APR_KEY | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| MODEL_BASE_URL | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| MODEL_NAME | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| MODEL_PRIORITY | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| MODEL_TIMEOUT | N | 120 | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | 10 | Low |
| MODEL_TYPE | Y | OPENAI | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| NO_PROXY | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| NO_PROXY_EXTRA | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| OLLAMA_BASE_URL | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| OLLAMA_BASE_URL_EXTERNAL | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| OLLAMA_EMBED_MODEL | N | nomic-embed-text | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| OLLAMA_MODE | N | CHAT | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | example_value | Low |
| OLLAMA_MODEL | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| OPENAI_API_KEY | Y | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | ****** | High |
| OPENAI_BASE_URL | N | https://api.openai.com | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| OPENAI_MODEL | N | gpt-4o-mini | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | gpt-4o-mini / gemini-flash-latest / llama3.1:8b | Low |
| OPENAI_TIMEOUT | N | 60 | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | 10 | Low |
| ORACLE_EMP_DB_PROFILE | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Medium |
| ORACLE_EMP_ENABLED | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 1 | Medium |
| ORACLE_ENABLED | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 1 | Medium |
| ORA_ACL_GROUP_COL | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Medium |
| ORA_ACL_TABLE | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Medium |
| ORA_ACL_USER_COL | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 1 | Medium |
| ORA_HOST | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Medium |
| ORA_PASS | Y | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | ****** | High |
| ORA_PORT | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 10 | Low |
| ORA_SERVICE_NAME | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| ORA_USER | N | (not explicitly fixed in code; environment-dependent) | Oracle/ACL configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 1 | Low |
| PORTAL_ACL_BACKEND | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | example_value | Medium |
| PORTAL_ACL_ENABLED | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 1 | Medium |
| PROXY_PREFIX | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| PROXY_PREFIX_DEBUG_LOG | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | 1 | Medium |
| PROXY_PREFIX_WRITE_SCRIPT_NAME | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | 1 | Medium |
| RAG_CHROMA_COLLECTION | N | cm_qna | RAG/vector store configuration | webapps/rag_oracle/*; webapps/meetingreply/views.py | example_value | Low |
| RAG_CHROMA_DIR | N | (not explicitly fixed in code; environment-dependent) | RAG/vector store configuration | webapps/rag_oracle/*; webapps/meetingreply/views.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| RAG_TOP_K | N | 10 | RAG/vector store configuration | webapps/rag_oracle/*; webapps/meetingreply/views.py | 10 | Low |
| SECURE_PROXY_SSL_VALUE | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| SESSION_COOKIE_PATH | N | (not explicitly fixed in code; environment-dependent) | Cookie/CSRF security settings | webproj/settings.py; webapps/portal/middleware*.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Medium |
| SESSION_COOKIE_SAMESITE | N | (not explicitly fixed in code; environment-dependent) | Cookie/CSRF security settings | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| SESSION_COOKIE_SECURE | N | (not explicitly fixed in code; environment-dependent) | Cookie/CSRF security settings | webproj/settings.py; webapps/portal/middleware*.py | example_value | Medium |
| SQLDOC_JSON | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SQLDOC_JSON_PATH | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| SQLTEST_JSON | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SQLTEST_JSON_PATH | N | (not explicitly fixed in code; environment-dependent) | Application setting | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| SQL_SERVER_DB | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SQL_SERVER_DRIVER | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SQL_SERVER_FETCH_SIZE | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 10 | Low |
| SQL_SERVER_HOST | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Medium |
| SQL_SERVER_PASS | Y | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | ****** | High |
| SQL_SERVER_PORT | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 10 | Low |
| SQL_SERVER_RAG_VIEW | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SQL_SERVER_UPSERT_BATCH | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 10 | Low |
| SQL_SERVER_USER | N | (not explicitly fixed in code; environment-dependent) | SQL Server configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 1 | Low |
| STATIC_ROOT | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | example_value | Low |
| SYBASE_CHAR | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SYBASE_CHARSET | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SYBASE_DB | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SYBASE_DRIVER | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SYBASE_DSN | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | example_value | Low |
| SYBASE_HOST | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Medium |
| SYBASE_INI_PATH | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| SYBASE_PASS | Y | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | ****** | High |
| SYBASE_PORT | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 10 | Low |
| SYBASE_TIMEOUT_SEC | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 10 | Low |
| SYBASE_USER | N | (not explicitly fixed in code; environment-dependent) | Sybase configuration | webapps/database/db_factory.py; webapps/doc/services/doc_db_router.py | 1 | Low |
| TEXT2PPTX_MAX_CHARS | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 10 | Low |
| TRUST_X_FORWARDED_PREFIX | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 1 | Low |
| TTS_API_BASE_URL | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | http://127.0.0.1:8000 or H:/AI/AI_TOOLS/... | Low |
| TTS_API_TIMEOUT | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 10 | Low |
| TTS_FILE_MAX_MB | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 10 | Low |
| TTS_MAX_CHARS | N | (not explicitly fixed in code; environment-dependent) | Application setting | Cross-module usage | 10 | Low |
| USE_OLLAMA_FIRST | N | (not explicitly fixed in code; environment-dependent) | LLM model/provider configuration | webapps/llm/llm_factory.py; webapps/llm/services.py | 1 | Low |
| USE_X_FORWARDED_HOST | N | (not explicitly fixed in code; environment-dependent) | Reverse proxy/network routing | Cross-module usage | 1 | Medium |

## 13) Missing Parameter List
- .env.example not found; missing count=104
- ALLOWED_HOSTS
- API_CONTEXT_PATH
- CHROMA_DIR
- CHROMA_PERSIST_DIR
- CSRF_COOKIE_PATH
- CSRF_COOKIE_SAMESITE
- CSRF_COOKIE_SECURE
- CSRF_TRUSTED_ORIGINS
- DB_FACTORY_MD_PATH
- DEBUG
- DEV_LOGIN_NAME
- DEV_LOGIN_USER
- DJANGO_DEBUG
- DJANGO_LOG_LEVEL
- DJANGO_SECRET_KEY
- DOC_API_DEBUG
- DOC_DEFAULT_PLANT
- DOC_QUERY_ALLOWED_IPS
- DOC_QUERY_TRUST_X_FORWARDED_FOR
- DOC_TPL_SUFFIX_MAX_TRY
- ENV
- ENV_PATH
- FILE_CHARSET
- FORCE_SCRIPT_NAME
- GOOGLE_API_KEY
- GOOGLE_MODEL
- LANGCHAIN_OLLAMA_MODEL
- LANGCHAIN_TEMPERATURE
- MEDIA_ROOT
- MOCK_DB_JSON
- MODEL_API_KEY
- MODEL_APR_KEY
- MODEL_BASE_URL
- MODEL_NAME
- MODEL_PRIORITY
- MODEL_TIMEOUT
- MODEL_TYPE
- NO_PROXY
- NO_PROXY_EXTRA
- OLLAMA_BASE_URL
- OLLAMA_BASE_URL_EXTERNAL
- OLLAMA_EMBED_MODEL
- OLLAMA_MODE
- OLLAMA_MODEL
- OPENAI_API_KEY
- OPENAI_BASE_URL
- OPENAI_MODEL
- OPENAI_TIMEOUT
- ORACLE_EMP_DB_PROFILE
- ORACLE_EMP_ENABLED
- ORACLE_ENABLED
- ORA_ACL_GROUP_COL
- ORA_ACL_TABLE
- ORA_ACL_USER_COL
- ORA_HOST
- ORA_PASS
- ORA_PORT
- ORA_SERVICE_NAME
- ORA_USER
- PORTAL_ACL_BACKEND
- PORTAL_ACL_ENABLED
- PROXY_PREFIX
- PROXY_PREFIX_DEBUG_LOG
- PROXY_PREFIX_WRITE_SCRIPT_NAME
- RAG_CHROMA_COLLECTION
- RAG_CHROMA_DIR
- RAG_TOP_K
- SECURE_PROXY_SSL_VALUE
- SESSION_COOKIE_PATH
- SESSION_COOKIE_SAMESITE
- SESSION_COOKIE_SECURE
- SQLDOC_JSON
- SQLDOC_JSON_PATH
- SQLTEST_JSON
- SQLTEST_JSON_PATH
- SQL_SERVER_DB
- SQL_SERVER_DRIVER
- SQL_SERVER_FETCH_SIZE
- SQL_SERVER_HOST
- SQL_SERVER_PASS
- SQL_SERVER_PORT
- SQL_SERVER_RAG_VIEW
- SQL_SERVER_UPSERT_BATCH
- SQL_SERVER_USER
- STATIC_ROOT
- SYBASE_CHAR
- SYBASE_CHARSET
- SYBASE_DB
- SYBASE_DRIVER
- SYBASE_DSN
- SYBASE_HOST
- SYBASE_INI_PATH
- SYBASE_PASS
- SYBASE_PORT
- SYBASE_TIMEOUT_SEC
- SYBASE_USER
- TEXT2PPTX_MAX_CHARS
- TRUST_X_FORWARDED_PREFIX
- TTS_API_BASE_URL
- TTS_API_TIMEOUT
- TTS_FILE_MAX_MB
- TTS_MAX_CHARS
- USE_OLLAMA_FIRST
- USE_X_FORWARDED_HOST

## 14) Manual Verification Items
- Production must enforce DEBUG off.
- Confirm final `PROXY_PREFIX` + `FORCE_SCRIPT_NAME` combo.
- Validate DB driver/DSN/encoding on target servers.
- Confirm MODEL_PRIORITY policy for cost/SLA.
- Implement secrets governance (.env.example + secret store).

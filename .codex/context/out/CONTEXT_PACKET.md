# CONTEXT_PACKET

## Hard Rules (excerpt)
# 專案系統架構與開發規範（精簡強制版）

本文件為強制規範（Mandatory Rules）。
任何違反者，程式碼不得合併（MUST NOT MERGE）。

## 一、適用範圍
- Django 多節點系統（portal / doc / comment / meetingreply / …）
- 前端 JS / HTML Template / Static 資源
- IIS Reverse Proxy（含 proxy prefix）
- DB_FACTORY / LLM_FACTORY
- ACL / require_node / DEV Login

## 二、URL 與 Proxy 規範（核心鐵則）

### 鐵則 1：Django 永遠不寫 proxy prefix
- `urls.py` 不得包含 `/djangoai` 或任何 proxy 前綴

```python
# 正確
path("incoming_lookup/", ...)
# 錯誤
path("djangoai/incoming_lookup/", ...)
```

### 鐵則 2：前端不得硬寫任何 prefix / node
- 禁止 `/djangoai/...`
- 禁止 `/doc/...`
- 禁止自行拼接 base URL

### 鐵則 3：所有 API URL 只能經過 `apiurl()`
- HTML / JS / Template 唯一合法入口：`apiurl(path)`
- `apiurl()` 必須來自 `apiurl_factory`

## 三、apiurl_factory 規範（唯一真相）

### 強制規則
- JS 只能讀取 `document.body.dataset.baseUrl`
- 禁止存取：
  - `window.__FORCE_SCRIPT_NAME__`
  - `window.__PROXY_PREFIX__`

## Layered Memory Spec (excerpt)
# Layered Memory Spec

## Goal
Keep prompts short and stable while preserving critical project behavior.

## Layer 1: Rules (Most Stable)
- Source: `.codex/rules.md` and mandatory project policies.
- Content: hard constraints, architecture rules, forbidden patterns.
- Update frequency: low.

## Layer 2: State (Medium Volatility)
- Source: current branch/worktree + latest completion notes.
- Content: what changed, current blockers, validation status.
- Update frequency: every task slice.

## Layer 3: Task (High Volatility)
- Source: current user request.
- Content: one small objective, touched files, acceptance checks.
- Update frequency: per slice.

## Priority
1. Rules
2. Latest explicit user instruction
3. State
4. Generic defaults

## Compression Policy
- Never paste full files unless required.
- Use `path + function + 2~4 line summary`.
- Keep session brief <= 12 lines.
- Keep one task slice <= 1 verifiable objective.

## Rebuild Packet Structure
1. Hard Rules (3 bullets max)
2. Current State (3 bullets max)
3. Active Task (3 bullets max)
4. Validation Plan (2 bullets max)


## Latest Memory Files
- vibe_context_playbook_hAI_20260312_090239.md (2026-03-12T09:02:39)
- doc_system_principles_hAI_20260312_085920.md (2026-03-12T08:59:20)
- template_rules_hAI_20260312_085640.md (2026-03-12T08:56:40)
- workspace_hAI_20260312_085327.md (2026-03-12T08:53:27)

## Active Task
- 建立分層記憶 + 任務切片 + 可重建上下文

## Validation Plan
- Run minimal command-level validation.
- Write completion note after slice.
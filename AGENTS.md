# AGENTS.md

## Mandatory Startup Rule

- Every new session in this project must read `/.codex/rules.md` before any other task.
- Do not skip this step.

## Encoding Rule

- Project text/code files must use UTF-8 without BOM.
- Avoid `Set-Content -Encoding UTF8` on Windows PowerShell 5.1 (it writes BOM).
- Use no-BOM write pattern instead:

```powershell
[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
```

- On PowerShell 7, prefer `-Encoding utf8NoBOM`.
- In VS Code, keep file encoding as `UTF-8` (not `UTF-8 with BOM`).

## Technical History & Bug Prevention

### Official Document Subsystem
- **Perspective Logic**: Always use `_preprocess_incoming_text` to replace relative aliases ("Our Bureau", "This Plant") with concrete names before LLM processing. This breaks the LLM's perspective-copying habit.
- **Buffer Integrity**: Frontend hidden inputs (e.g., `sybAttachTokens`) must be cleared using both `.value = ""` and `.setAttribute("value", "")` to ensure FormData captures the clean state. Always trigger `resetFocusPick` on any case switch.
- **Backend Parse**: Keep `out_files` generation idempotent and unique in `views_parse.py` to prevent duplicate record counts.

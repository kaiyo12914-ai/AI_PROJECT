# Context Kit (Layered Memory + Task Slicing + Rebuild)  

This folder solves context-length pressure by enforcing a small, repeatable context packet.

## Files
- `LAYERED_MEMORY.md`: defines 3 memory layers and priority.
- `templates/SESSION_BRIEF.template.md`: 6-line session brief template.
- `templates/TASK_SLICE.template.md`: one-task-per-slice execution template.
- `scripts/rebuild_context.ps1`: rebuilds a compact context packet from rules + latest memories + current task.

## Operating Rules
1. Start every new session by reading `.codex/rules.md`.
2. Build one session brief from the template (max 12 lines).
3. Execute exactly one task slice at a time.
4. After each slice, append a completion note and update memory if rules changed.

## Quick Start
```powershell
powershell -ExecutionPolicy Bypass -File .codex\context\scripts\rebuild_context.ps1 -ProjectRoot . -Task "Describe current task"
```

The script outputs:
- `.codex/context/out/CONTEXT_PACKET.md`
- `.codex/context/out/SESSION_BRIEF.md`

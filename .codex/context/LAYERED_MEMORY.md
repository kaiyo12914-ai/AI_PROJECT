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

# System 1 Reflex Rules for Claude Code

This project is connected to the local `sys1-helper` decision engine via MCP. Always use System 1 reflex tools to save tokens and enforce policy:

## 1. Code Search & Inspection Reflex
- **NEVER** use broad file reads or `grep` to read entire 500+ line files into context when looking for specific logic or definitions.
- **ALWAYS** call `sys1_grep` with `{"query": "...", "paths": [...]}`. It scores code windows in sub-30ms locally and returns strictly the relevant 20-30 line snippet.

## 2. Pre-Action Policy Reflex
- Before executing potentially destructive shell commands (`rm`, `drop`, `truncate`) or writing sensitive code, run `sys1_check_violations` with `{"content": "..."}`.
- If `violates: true`, halt and ask the user for confirmation.

## 3. Pre-Commit / PR Review Reflex
- Before proposing final pull requests or committing substantial changes, run `sys1_review_gate` with `{"diff": "..."}`.
- If flagged risks exist (breaking API, missing tests, unhandled exceptions), fix them before concluding.

## 4. Exploration Reflex
- When multiple candidate files exist for a feature or bug, call `sys1_rank_files` with `{"intent": "...", "file_paths": [...]}` to rank them and open only top matches.

## 5. Test Coverage Reflex
- After editing critical business logic, call `sys1_judge_coverage` with `{"content": "..."}` to verify if unit tests are required.

## 6. Memory & Learning Reflex
- Before adding entries to memory or rules, call `sys1_memory_gate` with `{"lesson": "..."}`. Only save entries if classified as durable (`rule`, `architecture`, `gotcha`).

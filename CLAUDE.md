# AgentReflex Rules for Claude Code

This project is connected to the local `AgentReflex` decision engine via MCP. Always use System 1 reflex tools to save tokens and enforce policy:

## 1. Code Search & Inspection Reflex
- **NEVER** use broad file reads or `grep` to read entire 500+ line files into context when looking for specific logic or definitions.
- **ALWAYS** call `reflex_grep` with `{"query": "...", "paths": [...]}`. It scores code windows in sub-30ms locally and returns strictly the relevant 20-30 line snippet.

## 2. Pre-Action Policy Reflex
- Before executing potentially destructive shell commands (`rm`, `drop`, `truncate`) or writing sensitive code, run `reflex_check_violations` with `{"content": "..."}`.
- If `violates: true`, halt and ask the user for confirmation.

## 3. Pre-Commit / PR Review Reflex
- Before proposing final pull requests or committing substantial changes, run `reflex_review_gate` with `{"diff": "..."}`.
- If flagged risks exist (breaking API, missing tests, unhandled exceptions), fix them before concluding.

## 4. Exploration Reflex
- When multiple candidate files exist for a feature or bug, call `reflex_rank_files` with `{"intent": "...", "file_paths": [...]}` to rank them and open only top matches.

## 5. Test Coverage Reflex
- After editing critical business logic, call `reflex_judge_coverage` with `{"content": "..."}` to verify if unit tests are required.

## 6. Memory & Learning Reflex
- Before adding entries to memory or rules, call `reflex_memory_gate` with `{"lesson": "..."}`. Only save entries if classified as durable (`rule`, `architecture`, `gotcha`).

## 7. Trajectory Pruning Reflex (AgentDiet)
- When long multi-turn sessions accumulate resolved errors or large diagnostic listings, call `reflex_prune_trajectory` to strip obsolete noise from conversation state.

## 8. Trajectory & Tool Budget Governor Reflex (Warden Governor)
- When executing complex multi-step explorations, periodically verify velocity with `reflex_trajectory_governor` passing `{"task_goal": "...", "recent_actions": [...], "total_tool_calls": N}` to prevent runaway tool spirals or spinning wheels without progress.

# AgentReflex Rules for Claude Code

This project is connected to the local `AgentReflex` decision engine via MCP (`reflex_*` tools) and automatic `PreToolUse` safety hooks.

## 1. Targeted Code Retrieval
- When searching across large (300+ line) files for specific implementations or functions, prefer `reflex_grep` with `{"query": "...", "paths": [...]}` to extract strictly relevant 20-30 line snippets rather than dumping entire files into context.
- For small files or quick targeted inspections, standard file reads and grep are fine.

## 2. Pre-Commit & PR Risk Audit
- Before proposing final pull requests or committing substantial cross-module changes, run `reflex_review_gate` with `{"diff": "..."}` to catch breaking API changes, security issues, or unhandled errors early.

## 3. Candidate Path Exploration
- When multiple candidate files exist for a feature or bug, call `reflex_rank_files` with `{"intent": "...", "file_paths": [...]}` to pinpoint top matches before reading.

## 4. History Pruning & Trajectory Governance
- In long multi-turn sessions with large terminal outputs or resolved errors, use `reflex_prune_trajectory` to strip obsolete noise from conversation state.
- When executing complex multi-step explorations, use `reflex_trajectory_governor` if you suspect spinning wheels without forward progress.

## 5. Memory & Learnings
- Only promote durable guidelines (`rule`, `architecture`, `gotcha`) to permanent memory via `reflex_memory_gate`. Discard one-off task details.

## 6. Task Completion Validation (Stop / Done Reflex)
- Before concluding complex tasks or declaring victory, call `reflex_validate_done` with `{"task_goal": "...", "git_diff": "...", "test_output": "..."}` to verify all requirements are met and no broken tests or syntax errors remain.

## 7. Speculative Decision Fan-Out & Prompt Triage
- For complex ambiguous requests, call `reflex_triage_task` with `{"content": "..."}` to extract all tactical traits (migration, auth, breaking API, test needs, risk level) in a single pass before planning.

## 8. Hallucinated Tool Call & Parameter Validation Gate
- Before running complex shell commands or file operations with unfamiliar syntax or options, call `reflex_validate_tool_call` with `{"tool_name": "...", "args": {...}}` to catch hallucinated CLI flags and prevent broken turns.

## 9. Semantic Action Cache ("Learn to Skip")
- For recurring diagnostic checks (e.g., test suite runs, linter passes, schema inspections), call `reflex_action_cache` with `{"action": "lookup", "intent": "..."}` to retrieve verified tool sequences instantly with 0 LLM planning tokens.
- After completing routine diagnostic workflows successfully, save the sequence via `reflex_action_cache` with `{"action": "save", "intent": "...", "actions": [...]}`.



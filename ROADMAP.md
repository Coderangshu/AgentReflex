# AgentReflex: System 1 Decision Engine Roadmap

This roadmap tracks planned and partially implemented System 1 (sub-30ms local decision model) capabilities to optimize coding agent latency, context bloat, and LLM token costs.

---

## 1. Dynamic Model Tier Router `[NEW]`

- **Status**: Not Implemented
- **Target Module**: `lib/model_router.py`
- **What Problem It Solves**:
  Frontier reasoning models (`Claude 3.7 Sonnet`, `o3`, `GPT-5`) cost 15x–30x more and run 5x–10x slower than fast flash tiers (`Claude 3.5 Haiku`, `gemini-2.5-flash`). Most agent turns (formatting, minor bug fixes, docstrings, routine CRUD) do not need frontier reasoning.
- **System 1 Decision Logic**:
  - **Input**: User prompt, target file paths, recent diff.
  - **Decision (`choice`)**:
    - `flash`: Single-line fixes, docstrings, boilerplate, simple questions.
    - `standard`: Single-file component work, standard unit tests, endpoint logic.
    - `frontier`: Multi-file refactors, concurrency/race conditions, architectural changes.
  - **Action**: Routes the turn to the optimal model tier before execution.
- **Latency & Impact**:
  - ~30ms locally on MPS/GPU.
  - **60%–80% cost reduction** across multi-turn agent sessions.

---

## 2. Trajectory & History Pruner ("AgentDiet") `[IMPLEMENTED]`

- **Status**: Implemented & Verified
  - *Module*: `lib/trajectory_pruner.py`
  - *Hooks*: Integrated into `hooks/pre_invocation.py`
  - *MCP*: Exposed as `sys1_prune_trajectory` in `mcp/server.py`
- **Target Module**: `lib/trajectory_pruner.py`
- **What Problem It Solves**:
  Long agent sessions accumulate obsolete terminal traces. Passing 50,000+ tokens of stale history degrades reasoning and multiplies token bills on every subsequent turn.
- **System 1 Decision Logic**:
  - **Input**: Multi-step conversation history entries (tool calls, outputs, errors).
  - **Decision (`choice` per step)**:
    - `obsolete_error`: Error trace that has already been resolved by later code edits -> strip.
    - `transient_listing`: Full directory listing or file scan superseded by newer context -> strip.
    - `durable_state`: Active user requirements, architectural constraints, and open errors -> keep.
  - **Action**: Distills conversation history into lean active context.
- **Latency & Impact**:
  - Batched scan across history in sub-second time locally on MPS.
  - **35%–75% context token reduction** per turn; eliminates attention distraction.

---

## 3. Hallucinated Tool Call & Parameter Gate `[IMPLEMENTED]`

- **Status**: Implemented & Verified
  - *Module*: `lib/param_validator.py`
  - *Hooks*: Integrated into `hooks/pre_tool_enforcer.py` and `hooks/claude_code_hook.py`
  - *MCP*: Exposed as `reflex_validate_tool_call` in `mcp/server.py`
- **Target Module**: `lib/param_validator.py`
- **What Problem It Solves**:
  LLMs frequently hallucinate tool arguments (invalid CLI flags like `git checkout -b --remote-track`, wrong file extensions, missing required parameters). This causes failed tool executions and burns an extra LLM turn (~2–4s + 1,000 tokens) recovering from the mistake.
- **System 1 Decision Logic**:
  - **Input**: Proposed tool name and argument JSON in `PreToolUse`.
  - **Decision (`noul` + `choice`)**:
    - `is_valid_command`: Verifies command flags match known tool specs.
    - `is_plausible_target`: Verifies target paths and symbols exist in workspace.
  - **Action**: If invalid, denies tool call immediately with structured self-correction guidance before disk touch.
- **Latency & Impact**:
  - ~20ms locally.
  - **Saves 1 full recovery roundtrip** (~2–4s and 1,000+ tokens per hallucination).

---

## 4. Automated "Stop / Done" Validator `[IMPLEMENTED]`

- **Status**: Implemented & Verified
  - *Module*: `lib/done_validator.py`
  - *MCP*: Exposed as `reflex_validate_done` in `mcp/server.py`
- **Target Module**: `lib/done_validator.py`
- **What Problem It Solves**:
  Autonomous coding agents suffer from two failure modes:
  1. **Premature Victory**: Declaring a task complete while broken tests or missing requirements remain.
  2. **Over-Iteration**: Continuing to run speculative edits after the task is already solved.
- **System 1 Decision Logic**:
  - **Input**: Initial user goal, accumulated git diff, latest test/build output, and final summary.
  - **Decision (`choice` + `noul`)**:
    - `status`: Multi-choice classification (`task_complete`, `needs_more_work`, `unrelated_or_blocked`).
    - `has_failing_tests`: Detects unhandled exceptions or failing assertions (`noul`).
    - `satisfies_goal`: Evaluates goal fulfillment (`noul`).
  - **Action**: Validates completion before session stop, catching omissions or halting runaway over-iteration.
- **Latency & Impact**:
  - ~35ms locally on MPS/GPU.
  - Prevents runaway token burn and eliminates premature victory.

---

## 5. Speculative Decision Fan-Out `[IMPLEMENTED]`

- **Status**: Implemented & Verified
  - *Module*: `lib/speculative_triage.py`
  - *Hooks*: Integrated into `hooks/pre_invocation.py` (parallel prompt tagging)
  - *MCP*: Exposed as `reflex_triage_task` in `mcp/server.py`
- **Target Module**: `lib/speculative_triage.py`
- **What Problem It Solves**:
  Agents often need 5–8 tactical classifications answered before acting (e.g., "Is this a bug or feature?", "Does it need a migration?", "Does it touch auth?", "Is it a breaking change?"). Running separate LLM calls or complex prompts introduces multi-second delays.
- **System 1 Decision Logic**:
  - **Input**: User prompt or git diff hunk.
  - **Decision (Parallel Multi-Question Batch in 1 forward pass)**:
    - `task_type`: bug_fix / feature / refactor / exploration
    - `needs_migration`: Boolean
    - `needs_tests`: Boolean
    - `touches_auth`: Boolean
    - `is_breaking`: Boolean
    - `risk_level`: Low / Medium / High
  - **Action**: Evaluates all questions in a single GPU pass (<45ms) and injects typed tags into the prompt.
- **Latency & Impact**:
  - <45ms total on MPS/CUDA for simultaneous tactical questions.
  - Instant prompt enrichment with 0 remote LLM calls.

---

## 6. Semantic Project Preferences Linter `[NEW]`

- **Status**: Not Implemented
- **Target Module**: `lib/pref_linter.py`
- **What Problem It Solves**:
  Traditional linters (ESLint, flake8) check syntax and formatting, but miss team architectural conventions (e.g., "prefer functional composition over classes", "always return `Result<T, E>` instead of throwing", "use our internal `useQuery` wrapper").
- **System 1 Decision Logic**:
  - **Input**: Newly edited code patch and project rulebook.
  - **Decision (`noul` + `score`)**:
    - Evaluates code against team design conventions in `PostToolUse`.
  - **Action**: Emits a targeted warning to the agent immediately if it starts drifting from project conventions.
- **Latency & Impact**:
  - ~30ms locally.
  - Stops agents from writing 500 lines using the wrong design pattern.

---

## 7. Trajectory & Tool Budget Governor ("Warden Governor") `[IMPLEMENTED]`

- **Status**: Implemented & Verified
  - *Module*: `lib/warden_governor.py`
  - *Hooks*: Integrated into `hooks/pre_tool_enforcer.py`
  - *MCP*: Exposed as `reflex_trajectory_governor` in `mcp/server.py`
- **Target Module**: `lib/warden_governor.py`
- **What Problem It Solves**:
  Autonomous agents can get caught in unproductive exploration spirals, consuming dozens of tool calls without making tangible progress toward the user request.
- **System 1 Decision Logic**:
  - **Input**: User goal, recent action history, prospective tool call, and cumulative tool count / tokens.
  - **Decision (`choice` + `noul`)**:
    - `velocity`: Classifies trajectory as `advancing`, `spinning_wheels`, or `deviating`.
    - `budget_risk`: Enforces tool call limits (default 25) and token budgets.
  - **Action**: Intercepts actions in `PreToolUse` (`allow_tool: false`) when stalled or budget exhausted, forcing a clean checkpoint.
- **Latency & Impact**:
  - ~25ms per tool call on local MPS.
  - Eliminates runaway tool spirals and runaway API bills.

---

## 8. Semantic Action Cache ("Learn to Skip") `[IMPLEMENTED]`

- **Status**: Implemented & Verified
  - *Module*: `lib/action_cache.py`
  - *Hooks*: Integrated into `hooks/pre_invocation.py`
  - *MCP*: Exposed as `reflex_action_cache` in `mcp/server.py`
- **Target Module**: `lib/action_cache.py`
- **What Problem It Solves**:
  Agents frequently repeat identical diagnostic steps across sessions (e.g., inspecting git status, checking lint, fetching database schema, verifying environment variables).
- **System 1 Decision Logic**:
  - **Input**: Task intent and workspace state hash.
  - **Decision (`score`)**: Matches state against verified successful trajectories in local cache.
  - **Action**: If similarity > 0.95, directly executes the cached tool sequence without querying the remote LLM.
- **Latency & Impact**:
  - <10ms.
  - 100% token savings and sub-50ms instant execution for recurring workflows.

---

## Roadmap Status Summary

| Phase | Capability | Target Module | Status | Existing Foundation |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **Dynamic Model Tier Router** | `lib/model_router.py` | `[NEW]` | None (Greenfield) |
| **2** | **Trajectory & History Pruner** | `lib/trajectory_pruner.py` | `[DONE]` | Complete (`lib/trajectory_pruner.py`, hook, MCP) |
| **3** | **Hallucinated Tool Call Gate** | `lib/param_validator.py` | `[DONE]` | Complete (`lib/param_validator.py`, hooks, MCP) |
| **4** | **Automated Stop / Done Validator** | `lib/done_validator.py` | `[DONE]` | Complete (`lib/done_validator.py`, MCP) |
| **5** | **Speculative Decision Fan-Out** | `lib/speculative_triage.py` | `[DONE]` | Complete (`lib/speculative_triage.py`, hook, MCP) |
| **6** | **Semantic Project Preferences Linter** | `lib/pref_linter.py` | `[NEW]` | None (Greenfield) |
| **7** | **Trajectory & Tool Budget Governor** | `lib/warden_governor.py` | `[DONE]` | Complete (`lib/warden_governor.py`, hook, MCP) |
| **8** | **Semantic Action Cache** | `lib/action_cache.py` | `[DONE]` | Complete (`lib/action_cache.py`, hook, MCP) |

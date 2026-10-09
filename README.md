# AgentReflex

Local System 1 reflex decision engine for various coding agents powered by [Laya](https://github.com/NandhaKishorM/laya).

Provides sub-30ms offline policy enforcement, intent routing, test coverage judgment, and context compaction before running slow, expensive LLM calls.

---

## 1. Quickstart & Daemon Setup

### Step 1: Create Isolated Virtual Environment & Install
Create a dedicated virtual environment inside `agentreflex` to isolate dependencies:
```bash
cd agentreflex # or sys1-helper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Step 2: Start Daemon (Downloads Model on First Run)
Start the resident HTTP server. On the first launch, it will automatically download the Laya model weights (~300MB) directly to your local cache:
```bash
make start
# Or: ./scripts/start_daemon.sh
```

### Step 3: Verify Installation
```bash
# Check daemon health and device (MPS / CUDA / CPU)
make status
# Output: {"status":"ok","service":"agentreflex","device":"mps"} Daemon is running healthy.

# Run unit tests (including MCP server protocol tests)
make test

# Run end-to-end simulation self-check
make simulate
```

To stop the daemon when done:
```bash
make stop
```

---

## 2. Integration & Getting Started

Choose your coding agent below:

<details>
<summary><strong>Google Antigravity (agy-cli)</strong></summary>

<br>

### Project-Level Attach (Recommended)
Attach native hooks and skills to any project where you run `agy`:

```bash
cd /path/to/your-target-project
/path/to/AgentReflex/scripts/install_hooks.sh .
```

> **How it works under the hood**:
> `install_hooks.sh` automatically detects the `.venv/bin/python` interpreter inside `AgentReflex` and binds it explicitly inside `.agents/hooks.json`. This guarantees `agy-cli` runs the hooks in `AgentReflex`'s isolated environment without polluting or conflicting with your target project's Python version, Node runtime, or dependencies.

This creates `.agents/` inside the target directory:
- **`.agents/hooks.json`**: Configures `PreInvocation`, `PreToolUse`, and `PostToolUse` hooks pointing to `agentreflex/.venv/bin/python`.
- **`.agents/skills/`**: Symlinks all 4 skills (`reflex-fast-explore`, `reflex-review-gate`, `reflex-compact`, `reflex-grep`).

### Global Skills Attach (All Projects)
To make skills available everywhere across all `agy` sessions:

```bash
ln -sfn /path/to/agentreflex/skills/reflex-fast-explore ~/.gemini/config/skills/reflex-fast-explore
ln -sfn /path/to/agentreflex/skills/reflex-review-gate ~/.gemini/config/skills/reflex-review-gate
ln -sfn /path/to/agentreflex/skills/reflex-compact ~/.gemini/config/skills/reflex-compact
ln -sfn /path/to/agentreflex/skills/reflex-grep ~/.gemini/config/skills/reflex-grep
```

### Execution Flow in `agy`
Once attached, launch the agent normally inside your project:
```bash
agy
```
1. **Before Prompt Execution (`PreInvocation`)**: Routes user goals and injects recommended skill context (`/reflex-fast-explore`, `/reflex-review-gate`, `/reflex-grep`). Compresses active transcript if `>50KB` (pruning terminal downloads/progress bars by 80–90%).
2. **Before Tool Execution (`PreToolUse`)**: Intercepts edits and commands in ~36ms on GPU, blocking hardcoded secrets, raw SQL, and destructive commands (`allow_tool: false`). Detects and halts runaway agent loops.
3. **After Tool Execution (`PostToolUse`)**: Inspects written code and flags newly introduced logic lacking test coverage.

</details>

<details>
<summary><strong>Claude Code</strong></summary>

<br>

Claude Code uses AgentReflex in two ways: an MCP server (`mcp/server.py`) that exposes the `reflex_*` tools, and hooks (`hooks/claude_code_hook.py`) that run automatically on tool use. Both talk to the local daemon (`make start`).

### One-command install
```bash
# Every project (writes ~/.claude/settings.json, ~/.claude/CLAUDE.md, user-scope MCP)
/path/to/AgentReflex/scripts/install_claude_code.sh --user

# Or a single project (writes <project>/.claude/settings.json, <project>/CLAUDE.md, project-scope MCP)
/path/to/AgentReflex/scripts/install_claude_code.sh /path/to/your-target-project
```
The script is idempotent. It (1) registers the `agentreflex` MCP server, (2) merges the hooks into `settings.json` without touching your other settings, and (3) appends the reflex rules from `CLAUDE.md` once. Restart Claude Code afterwards and check `/mcp` and `/hooks`.

> **Note**: a plain `claude mcp add` (no `-s user`) registers the server for the current directory only, so other projects won't see it.

### Hooks (automatic)
| Event | Matcher | Behavior |
| :--- | :--- | :--- |
| `PreToolUse` | `Bash`, `Write`, `Edit`, `MultiEdit` | Checks commands and edits against the safety policy. On a violation it prompts you to confirm (`ask`) rather than hard-blocking. File edits get a deterministic secret-pattern check first. The model only judges edits of 200+ characters, because it over-scores short snippets. |
| `PostToolUse` | `Write`, `Edit`, `MultiEdit` | Tells Claude when newly written logic likely needs tests (`reflex_judge_coverage`). |
| `UserPromptSubmit` | all | Routes the prompt and tells Claude which `reflex_*` tool fits (explore / review / compact). |

The hooks fail open: if the daemon is down or errors, Claude proceeds normally. The loop and budget governor is not run as a hook, because normal Claude Code sessions routinely exceed its 25-call budget. Claude can call `reflex_trajectory_governor` itself.

### Manual MCP registration
```bash
claude mcp add -s user agentreflex -- /path/to/AgentReflex/.venv/bin/python /path/to/AgentReflex/mcp/server.py
```
The `CLAUDE.md` rules (what makes Claude call the tools proactively) are in this repo's `CLAUDE.md`. Append them to your project's or `~/.claude/CLAUDE.md`.


### Exposed MCP Tools (12 Core Modules)
Once registered, Claude Code has instant access to 12 System 1 tools:
- **`reflex_check_violations`**: Pre-action guardrail checking code edits and shell commands for secrets, destructive `rm -rf`, and database drops before running them.
- **`reflex_grep`**: Surgical context retrieval (`jevgrep`). Chunks target files into 20–30 line windows, scores them locally via Laya in ~30ms, and returns only strictly relevant snippets.
- **`reflex_review_gate`**: 7-point PR / diff risk audit across API breaks, injections, leaks, perf regressions, test gaps, unhandled errors, and contract violations.
- **`reflex_compact`**: Scores terminal output or conversation logs to distinguish disposable noise from retainable state.
- **`reflex_rank_files`**: Reranks candidate file paths by semantic relevance to a task intent.
- **`reflex_judge_coverage`**: Evaluates newly modified code to check if unit tests are required.
- **`reflex_memory_gate`**: Filters post-task lessons, ensuring only durable patterns (`rule`, `architecture`, `gotcha`) are stored in long-term memory.
- **`reflex_prune_trajectory`**: Multi-turn conversation history pruner (AgentDiet). Strips obsolete resolved errors and diagnostic noise while preserving active state.
- **`reflex_trajectory_governor`**: Trajectory velocity and tool budget governor (Warden Governor). Halts unproductive exploration spirals and enforces budget limits.
- **`reflex_validate_done`**: Automated Stop/Done completion validator. Verifies diffs and test suites satisfy user objectives before concluding.
- **`reflex_triage_task`**: Speculative multi-question triage fan-out. Classifies task type, risks, migration/auth requirements, and returns enriched execution plan tags.
- **`reflex_validate_tool_call`**: Hallucinated parameter and tool call gate. Validates command flags, tool arguments, and path plausibility before execution.

</details>

---

## 3. Standalone Skills CLI Usage

### Fast File Explorer (`reflex-fast-explore`)
Quickly rank candidate paths so the agent only reads top matches:

```bash
python skills/reflex-fast-explore/run.py "database migration files" $(find . -name "*.py")
# Or pipe:
find . -name "*.py" | python skills/reflex-fast-explore/run.py "auth controllers"
```

### 7-Point PR / Diff Risk Gate (`reflex-review-gate`)
Evaluate diff against 7 risk vectors (breaking API, security injection, secret leak, perf regression, missing tests, unhandled exceptions, schema breaking):

```bash
# Evaluate current working changes:
git diff | python skills/reflex-review-gate/run.py

# Evaluate specific commit:
git diff HEAD~1 | python skills/reflex-review-gate/run.py
```
Exit code `0` on APPROVE, exit code `1` on REJECT / CHANGES REQUIRED.

### Context Compactor (`reflex-compact`)
Prune disposable noise and terminal vomit from session context:

```bash
# Compact conversation transcript:
python skills/reflex-compact/run.py --transcript /path/to/transcript.jsonl

# Compact raw command output or logs:
cat build.log | python skills/reflex-compact/run.py
```

### Surgical Context Retrieval (`reflex-grep` / jevgrep)
Extract strictly relevant 20-30 line snippets instead of loading full files into LLM context:

```bash
python skills/reflex-grep/run.py "detect infinite loop" lib/
```

---

## 4. Core System 1 Decision Tools & Token Savings

Each tool offloads specialized binary (`true`/`false`) or discrete classification decisions from expensive frontier LLMs to the local Laya engine (<50ms on GPU). The exact criteria, question modes, and decision thresholds are detailed below:

| Tool / Decision Engine | Classification Basis & Decision Threshold (`true` / `false`) | Output Type | Time & Token Savings |
| :--- | :--- | :--- | :--- |
| **`reflex_check_violations`**<br>([`lib/rule_enforcer.py`](file:///Users/angshuman/git/AgentReflex/lib/rule_enforcer.py)) | **Boolean (`noul` >= 0.80)**: Evaluates code edit/command against safety rules (plaintext secrets, credentials, `rm -rf`, DROP DB). **`violates = true`** if certainty >= 80%. | Boolean flag + score | **~50ms locally vs ~1,600ms LLM roundtrip**. Saves **~750 tokens per tool call**; prevents catastrophic leaks. |
| **`reflex_grep`**<br>([`lib/surgical_retrieval.py`](file:///Users/angshuman/git/AgentReflex/lib/surgical_retrieval.py)) | **Boolean (`noul` >= 0.70)**: Evaluates 20–30 line sliding windows against target query (*"Does this snippet directly answer, define, or implement logic for '{query}'?"*). Matches scored above threshold are kept. | Ranked snippet list | **Cuts context by 70–90%**. Injects ~200 tokens of relevant lines instead of 2,000+ token full file dumps. |
| **`reflex_compact`**<br>([`lib/compaction.py`](file:///Users/angshuman/git/AgentReflex/lib/compaction.py)) | **Boolean (`should_prune = true`)**: Triggers if regex matches progress bars/downloads OR neural scores meet: `(noise_score > 0.65 and keep_score < 0.35) or noise_score >= 0.80`. | Boolean flag + noise/keep scores | **Prunes 80–90% of terminal noise** locally. Prevents multi-thousand-token log dumps from bloating context. |
| **`reflex_prune_trajectory`**<br>([`lib/trajectory_pruner.py`](file:///Users/angshuman/git/AgentReflex/lib/trajectory_pruner.py)) | **Multi-class choice + threshold**: Compares past steps against future steps to classify category:<br>• `obsolete_error`: choice `resolved_past_error` with conf >= 0.65 (`should_prune = true`)<br>• `transient_listing`: `is_transient_search` noul >= 0.70 or progress regex (`should_prune = true`)<br>• `durable_state`: default (`should_prune = false`). | Step category + boolean prune flag | **Cuts multi-turn context by 35%–75%**, eliminating stale error distraction across multi-turn agent sessions. |
| **`reflex_rank_files`**<br>([`lib/file_ranker.py`](file:///Users/angshuman/git/AgentReflex/lib/file_ranker.py)) | **Continuous score (`noul`)**: Evaluates candidate file path against intent (*"Is candidate file highly relevant to '{intent}'?"*). Sorted descending, top-K paths returned. | Ranked `(file, score)` pairs | Ensures agent opens only top 1–2 target files, **saving up to 80% speculative file-reading tokens**. |
| **`reflex_review_gate`**<br>([`lib/review_gate.py`](file:///Users/angshuman/git/AgentReflex/lib/review_gate.py)) | **Boolean 7-point audit (`passed = true/false`)**: Tests 7 dimensions with `noul` (API break, security injection, secrets leak, perf regression, test gap, unhandled exception, contract violation). **`passed = false`** if *any* dimension >= 0.70 risk threshold. | Boolean pass/fail + flagged risks | Instant risk audits in **sub-second time**, replacing slow and repetitive full-diff reviews by frontier models. |
| **`reflex_judge_coverage`**<br>([`lib/judge.py`](file:///Users/angshuman/git/AgentReflex/lib/judge.py)) | **Boolean (`requires_verification = true`)**: Calculates `uncovered_risk = max(0.0, needs_tests - (is_test_file * 0.8))`. Flags **`true`** if `uncovered_risk >= 0.70`. | Boolean flag + risk score | Flags test gaps in **~40ms**, catching omissions early before expensive downstream test and fix cycles. |
| **`reflex_memory_gate`**<br>([`lib/memory_gate.py`](file:///Users/angshuman/git/AgentReflex/lib/memory_gate.py)) | **Composite boolean (`should_promote = true`)**: Requires `should_promote` noul >= 0.70 **AND** category choice != `ephemeral` (must be `rule`, `architecture`, or `gotcha`). | Boolean promotion + category | Prevents permanent memory from accumulating noise; keeps long-term retrieval lean and high-signal. |
| **Skill & Intent Router**<br>([`lib/skill_picker.py`](file:///Users/angshuman/git/AgentReflex/lib/skill_picker.py)) | **Multi-class choice + confidence**: Selects target skill (`fast_explore`, `review_gate`, `compact`, `none`). **`is_recommended = true`** if choice != `none` and `confidence > 0.65`. | Skill choice + recommendation flag | **Routes in ~50–130ms with 0 tokens**. Bypasses expensive multi-turn frontier LLM planning (~1,400ms / ~500 tokens). |
| **Agent Loop Detector**<br>([`lib/loop_detector.py`](file:///Users/angshuman/git/AgentReflex/lib/loop_detector.py)) | **Deterministic + neural (`is_looping = true`)**: Flags **`true`** immediately if >= 3 identical consecutive actions; or if error present and neural `is_stuck` noul >= 0.99. | Boolean loop flag + reason | **Instantly halts runaway loops**, saving tens of thousands of wasted tokens and stuck retry cycles. |
| **Trajectory & Tool Budget Governor**<br>([`lib/warden_governor.py`](file:///Users/angshuman/git/AgentReflex/lib/warden_governor.py)) | **Multi-factor threshold (`allow_action = false`)**: Intercepts if tool calls >= 25, tokens >= 120,000, identical action loops >= 3, or neural velocity choice `spinning_wheels`/`deviating` (conf >= 0.65) while budget > 60%. | Boolean allow/deny + budget metrics | **Eliminates runaway exploration spirals**, saving tens of thousands of wasted tokens and runaway LLM billing. |
| **Task Completion Validator**<br>([`lib/done_validator.py`](file:///Users/angshuman/git/AgentReflex/lib/done_validator.py)) | **Composite threshold (`is_complete = true`)**: Verifies code diff and test output fulfill user goal. Flags **`false`** if failing tests score >= 0.60, satisfaction < 0.40, or choice `needs_more_work`. | Boolean complete + missing gaps | **Prevents premature victory** and eliminates speculative over-iteration after tasks are finished. |
| **Speculative Decision Fan-Out**<br>([`lib/speculative_triage.py`](file:///Users/angshuman/git/AgentReflex/lib/speculative_triage.py)) | **Parallel multi-question triage**: Classifies 6 dimensions simultaneously in 1 forward pass (task type, db migration, test needs, auth sensitivity, breaking change, risk level). Injects typed tags into prompt context. | Typed tags + dimension scores | **Enriches prompts in <45ms**, bypassing multiple sequential remote LLM roundtrips and planning turns. |
| **Hallucinated Param Gate**<br>([`lib/param_validator.py`](file:///Users/angshuman/git/AgentReflex/lib/param_validator.py)) | **Deterministic + neural validation**: Catches hallucinated CLI flags (`git`, `npm`, `pip`, `pytest`), missing required schema parameters, and nonexistent disk paths before execution. | Validation boolean + suggestions | **Saves 1 full recovery roundtrip** (~2–4s + 1,000+ tokens) per hallucinated tool invocation. |
| **DOM Element Selector**<br>([`lib/browser_nav.py`](file:///Users/angshuman/git/AgentReflex/lib/browser_nav.py)) | **Multi-candidate choice**: Scores all candidate interactive DOM elements against navigation goal. Returns candidate with highest confidence; returns `None` if `none` wins. | Selected DOM node + confidence | Eliminates sending massive 10,000+ token raw HTML dumps to LLM; picks targets locally in ~40ms. |

---

## 5. Benchmarks & Performance Benefits

Benchmarked directly against an active full-stack codebase (`Native-App` - React Native / Expo / Drizzle):

| Metric | Without Laya (Frontier LLM Roundtrip) | With Laya (MPS GPU System 1 Engine) | Real-World Impact |
| :--- | :--- | :--- | :--- |
| **Intent & Skill Routing** | ~1,400 ms \| 500 tokens | **133 ms** \| **0 tokens** | **10.5x faster**, 100% token savings |
| **Pre-Tool-Use Guardrail** | ~1,600 ms \| 750 tokens | **~50 ms** \| **0 tokens** | **~25x faster**, blocks before disk touch |
| **Code Retrieval (`db/`)** | 794 tokens (full file dump) | **600 tokens** (surgical snippets) | **24.4% context token reduction** |
| **Context Compaction** | 100% build logs retained | **80–90%** terminal noise pruned | Keeps LLM prompt lean |

---

## 6. Overcoming the Small Context Size Bottleneck

The base Laya model (`ModernBERT-large`) is designed for sub-50ms System 1 classification with a single-window context budget of 512 tokens (~1,200 characters).

For large inputs (such as multi-KB files, full git diffs, or entire module changes), a naive truncation to 1,200 characters would introduce blind spots (e.g., missing a leaked secret at line 100 of a 4KB file).

### The Solution: Dynamic Sliding-Window Aggregation (`predict_long`)
To eliminate this bottleneck without sacrificing speed:
1. **Dynamic Routing in Daemon**: In [daemon/server.py](daemon/server.py), states under 1,200 characters execute via single-pass `predict()` in **~36 ms**.
2. **Overlapping Window Scanning**: When a payload exceeds 1,200 characters, the daemon automatically activates `router.predict_long()`.
3. **Smart Aggregation**:
   - Long files and multi-hunk diffs are chunked into overlapping sliding windows (50% stride).
   - Scored in batches on GPU.
   - For risk guardrails (`noul`), the decision aggregates to the **maximum risk score** across all windows.
4. **Verified Accuracy**:
   - In a 4,386-character file with a secret placed at character 4,000, single-window truncation scored `0.2476` (missed leak).
   - `predict_long` scanned 6 overlapping windows and caught the leak with score `1.0000` (100% certainty, pinpointed in window #5).

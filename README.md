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


### Exposed MCP Tools (14 Core Modules)
Once registered, Claude Code has instant access to 14 System 1 tools:
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
- **`reflex_action_cache`**: Semantic action cache ("Learn to Skip"). Stores and retrieves verified successful idempotent diagnostic action sequences.
- **`reflex_route_model`**: Dynamic Model Tier & Effort Router. Classifies task across 8 categories and outputs model tier, reasoning effort, and thinking token limits.

</details>

---

## 3. System 1 Decision & Safety Tools

See the complete [Tool Reference](docs/tools.md) for full parameter schemas, input/output structures, and decision thresholds.

1. **Check Violation**: Intercepts shell commands and file edits before execution, blocking security risks, credentials/secrets, and destructive commands (`rm -rf`, database drops).
2. **Surgical Retrieval (jevgrep)**: Scans target files in 20–30 line sliding windows and scores them against user intent, returning strictly relevant snippets instead of full multi-KB files.
3. **Context Compactor**: Strips ephemeral terminal noise, progress bars, download spinners, and repetitive logs from command outputs or transcripts.
4. **Trajectory Pruner**: Compacts multi-turn conversation transcripts, pruning resolved error loops and transient search noise while keeping active state intact.
5. **File Ranker**: Scores candidate file paths against task intent to prioritize the top 1–2 files for the agent to inspect.
6. **Review Gate (7-Point Risk Audit)**: Audits git diffs across 7 dimensions (breaking changes, injections, secret leaks, perf regressions, test gaps, unhandled errors, contract violations).
7. **Coverage Judge**: Evaluates newly written or edited logic to determine if accompanying unit tests are needed.
8. **Memory Gate**: Filters post-task lessons, saving only durable architectural rules and gotchas to long-term memory while discarding ephemeral session noise.
9. **Intent & Skill Router**: Classifies prompts into 8 categories and routes directly to the optimal skill with zero added latency.
10. **Loop Detector**: Halts runaway agent loops when identical actions or stuck error cycles repeat.
11. **Trajectory Budget Governor**: Enforces turn tool budgets and intercepts unproductive exploration spirals.
12. **Task Completion Validator**: Verifies that modified code diffs and test results actually fulfill the user's prompt before the agent concludes.
13. **Speculative Task Triage**: Simultaneously classifies 6 task dimensions (task type, db migration, test needs, auth sensitivity, breaking change, risk level) in one forward pass.
14. **Parameter Gate**: Validates CLI flags, schema arguments, and path existence before execution to prevent hallucinated commands.
15. **Semantic Action Cache**: Caches verified idempotent diagnostic sequences bound to git commit state for instant replay.
16. **Dynamic Model Router**: Dynamically selects model tier (`flash`, `standard`, `frontier`), reasoning effort, and thinking budget based on prompt complexity.
17. **DOM Element Selector**: Evaluates candidate interactive browser DOM elements against user navigation goals, choosing the single optimal element locally in ~40ms and avoiding massive raw HTML token dumps to LLMs.

---

## 4. Benchmarks & Performance Benefits

Benchmarked directly against an active full-stack codebase (`Native-App` - React Native / Expo / Drizzle):

| Metric | Without Laya (Frontier LLM Roundtrip) | With Laya (MPS GPU System 1 Engine) | Real-World Impact |
| :--- | :--- | :--- | :--- |
| **Intent & Skill Routing** | ~1,400 ms \| 500 tokens | **133 ms** \| **0 tokens** | **10.5x faster**, 100% token savings |
| **Pre-Tool-Use Guardrail** | ~1,600 ms \| 750 tokens | **~50 ms** \| **0 tokens** | **~25x faster**, blocks before disk touch |
| **Code Retrieval (`db/`)** | 794 tokens (full file dump) | **600 tokens** (surgical snippets) | **24.4% context token reduction** |
| **Context Compaction** | 100% build logs retained | **80–90%** terminal noise pruned | Keeps LLM prompt lean |

---

## 5. Overcoming the Small Context Size Bottleneck

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

---

## 6. Latency & Time-To-First-Token (TTFT) Optimizations

To ensure zero perceived lag on user turns—especially for rapid, interactive tasks—the client-daemon architecture incorporates three major latency optimizations:

### 1. Unix Domain Socket (UDS) with Transparent TCP Fallback
- **Zero TCP Handshake Overhead**: On macOS and Linux, the client communicates with the resident daemon via `/tmp/agentreflex.sock` using pure OS kernel buffer copies, completely bypassing TCP loopback networking, 3-way handshakes, and `TIME_WAIT` connection teardowns.
- **~4x Faster Raw Socket IO**: Drops raw IPC transfer latency from ~1.76ms to ~0.44ms per request.
- **Dual-Mode Resident Daemon**: The daemon binds both UDS and `127.0.0.1:8765` concurrently in the same asyncio event loop. If UDS is unavailable (e.g. on Windows), client requests fall back to TCP transparently without configuration changes.

### 2. Single-Pass Unified Skill & Model Derivation
- **Eliminated Duplicate Inference**: Previous implementations ran a separate `pick_skill` classifier before `route_model`.
- **0ms Skill Derivation**: Specialized agent skills are now derived directly from `route_model`'s 8-class taxonomy:
  - `review_audit` -> `reflex-review-gate`
  - `simple_inspect` -> `reflex-fast-explore` / `reflex-grep`
  - Explicit compaction requests -> `reflex-compact`
- Eliminates 60ms of duplicate neural model latency per prompt turn.

### 3. Neural-Gated Triage Bypass
- **Smart Conditional Execution**: The heavy multi-dimension speculative prompt triage (`triage_task` checking database migrations, breaking contracts, and security vectors) is automatically bypassed for read-only and trivial tasks (`doc_typo`, `ops_script`, `simple_inspect`).
- Deep triage runs exclusively when code-modifying intents (`routine_crud`, `complex_refactor`, `hard_debug`, `arch_design`) are detected.

### Real-World TTFT Benchmark Results

| Prompt Type | Unoptimized Hook | Optimized Hook (UDS + Unified Router) | Latency Reduction |
|---|---|---|---|
| **Basic Typo** (`fix typo in README`) | **372 ms** | **158 ms** | **~2.35x faster (57% drop)** 🚀 |
| **Simple Inspect** (`explain auth middleware`) | **~450 ms** | **159 ms** | **~2.8x faster (65% drop)** 🚀 |
| **Inspect File** (`read config & inspect db`) | **~450 ms** | **162 ms** | **~2.8x faster (64% drop)** 🚀 |
| **Standard Feature** (`add route for login`) | **447 ms** | **381 ms** | **~15% faster** |
| **Complex Debug** (`deadlock in worker pool`) | **479 ms** | **393 ms** | **~18% faster** |
| **Complex Review** (`review git diff for bugs`) | **~480 ms** | **389 ms** | **~19% faster** |

---

## 7. Real-World Project Activity Logging

AgentReflex can record an audit trail of agent interactions across your active coding projects:
- **User Prompts**: Every incoming prompt (`[TOOL: USER_PROMPT]`)
- **Tool Invocations**: Every tool proposed (`run_command`, `replace_file_content`, `view_file`, etc.)
- **Guardrail Interceptions**: Blocked actions (`BLOCKED: <reason>`)
- **Tool Outputs & Responses**: Truncated execution results, exit codes, and errors

### Log Storage & Isolated Layout
Logs are saved inside the `AgentReflex` repository in [`logs/`](logs/):
- **Human-Readable Text**: `logs/<project_name>.log` (single line per event, optimized for `tail -f`)
- **Structured JSON Lines**: `logs/<project_name>.jsonl` (for programmatic queries or metrics)
- **Daemon Lifecycle Logs**: `logs/server.log` (daemon startup, health, and server events)

Each project writes to its own isolated file (`logs/doomsday.log`, `logs/laya.log`, `logs/AgentReflex.log`), completely eliminating concurrent file write lock contention. Redundant project tags are omitted from line contents since the filename already identifies the project.

### How to Enable Logging (OFF by Default)
Logging is **disabled by default** (0 disk overhead). Choose your preferred opt-in method below:

<details>
<summary><strong>Method 1: Flag File (Fastest)</strong></summary>

<br>

Touch `.reflex-log` in the root of your target project:
```bash
touch /path/to/your-project/.reflex-log
```

</details>

<details>
<summary><strong>Method 2: Project Config (.agentreflex.json)</strong></summary>

<br>

Create or edit `.agentreflex.json` or `.agents/config.json` in your project root:
```json
{
  "logging": true
}
```

</details>

<details>
<summary><strong>Method 3: Hooks Configuration (.agents/hooks.json)</strong></summary>

<br>

Add `"logging": true` under `"reflex-guardrails"` in `.agents/hooks.json`:
```json
{
  "reflex-guardrails": {
    "logging": true,
    "PreInvocation": [...],
    ...
  }
}
```

</details>

<details>
<summary><strong>Method 4: Environment Variable</strong></summary>

<br>

Enable globally for a terminal session:
```bash
export AGENTREFLEX_LOGGING=1
```

</details>

### Live Log Streaming
Watch agent activity in real-time while working:
```bash
tail -f logs/<project_name>.log
```
Example output:
```text
[TOOL: run_command] cmd='git status' -> response=CALL_ALLOWED [AGENT: gemini-3.8-flash (test-doo)] [STATUS: allowed] [2026-10-11 17:34:39]
[TOOL: run_command] cmd='git status' -> response=On branch main, up to date [AGENT: gemini-3.8-flash (test-doo)] [STATUS: success] [2026-10-11 17:34:39]
[TOOL: USER_PROMPT] {"prompt": "run tests"} -> response=(turn started) [AGENT: gemini-3.8-flash (test-doo)] [STATUS: prompt] [2026-10-11 17:41:03]
```

---

## 8. Roadmap & In-Progress Features

See the dedicated [Roadmap](docs/ROADMAP.md) for active optimizations in progress and planned capabilities:

- **Cross-Turn Intent Drift Alarm**: Proactive course-correction when multi-turn execution wanders off-topic.
- **Speculate-and-Verify Tool Prefetching**: Predicts and runs read-only diagnostic actions in the background.
- **Ephemeral Scratchpad Auto-Janitor**: Cleans disposable scratch files and temp scripts after turn completion.
- **AST-Aware Chunking for Surgical Retrieval**: Function- and class-level syntax boundary chunking for `jevgrep`.




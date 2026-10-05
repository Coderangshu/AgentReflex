# sys1-helper

Local System 1 decision engine for `agy-cli` agents powered by [Laya](https://github.com/convaiinnovations/laya).

Provides sub-30ms offline policy enforcement, intent routing, test coverage judgment, and context compaction before running slow, expensive LLM calls.

---

## 1. Quickstart & Daemon Setup

### Step 1: Create Isolated Virtual Environment & Install
Create a dedicated virtual environment inside `sys1-helper` to isolate dependencies:
```bash
cd sys1-helper
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
# Output: {"status":"ok","service":"sys1-helper","device":"mps"} Daemon is running healthy.

# Run unit tests
make test

# Run end-to-end simulation self-check
make simulate
```

To stop the daemon when done:
```bash
make stop
```

---

## 2. Attaching to `agy-cli`

### Option A: Project-Level Attach (Recommended)
Attach hooks and skills to any codebase where you use `agy`:

```bash
cd /path/to/your-target-project
/path/to/sys1-helper/scripts/install_hooks.sh .
```

> **How it works under the hood**:
> `install_hooks.sh` automatically detects the `.venv/bin/python` interpreter inside `sys1-helper` and binds it explicitly inside `.agents/hooks.json`. This guarantees `agy-cli` runs the hooks in `sys1-helper`'s isolated environment without polluting or conflicting with your target project's Python version, Node runtime, or dependencies.

This creates `.agents/` inside the target directory:
- **`.agents/hooks.json`**: Configures `PreInvocation`, `PreToolUse`, and `PostToolUse` hooks pointing to `sys1-helper/.venv/bin/python`.
- **`.agents/skills/`**: Symlinks all 4 skills (`laya-fast-explore`, `laya-review-gate`, `laya-compact`, `laya-grep`).

### Option B: Global Skills Attach (All Projects)
To make skills available everywhere across all `agy` sessions:

```bash
ln -sfn /path/to/sys1-helper/skills/laya-fast-explore ~/.gemini/config/skills/laya-fast-explore
ln -sfn /path/to/sys1-helper/skills/laya-review-gate ~/.gemini/config/skills/laya-review-gate
ln -sfn /path/to/sys1-helper/skills/laya-compact ~/.gemini/config/skills/laya-compact
ln -sfn /path/to/sys1-helper/skills/laya-grep ~/.gemini/config/skills/laya-grep
```

---

## 3. How It Works During `agy` Execution

Once attached, launch the agent normally inside your project:

```bash
agy
```

`agy-cli` automatically hooks into `sys1-helper`:

1. **Before Prompt Execution (`PreInvocation`)**:
   - [hooks/pre_invocation.py](hooks/pre_invocation.py) routes user intent and injects recommended skill context (`/fast_explore` or `/review_gate`).
2. **Before Tool Execution (`PreToolUse`)**:
   - [hooks/pre_tool_enforcer.py](hooks/pre_tool_enforcer.py) intercepts proposed code edits and shell commands.
   - Evaluates risk in ~30ms. If dangerous queries, hardcoded secrets, or policy violations exceed `>= 80%` certainty, execution blocks immediately (`allow_tool: false`).
3. **After Tool Execution (`PostToolUse`)**:
   - [hooks/post_tool_judge.py](hooks/post_tool_judge.py) inspects newly written code and flags logic lacking test coverage.

---

## 4. Standalone Skills CLI Usage

### Fast File Explorer (`laya-fast-explore`)
Quickly rank candidate paths so the agent only reads top matches:

```bash
python skills/laya-fast-explore/run.py "database migration files" $(find . -name "*.py")
# Or pipe:
find . -name "*.py" | python skills/laya-fast-explore/run.py "auth controllers"
```

### 7-Point PR / Diff Risk Gate (`laya-review-gate`)
Evaluate diff against 7 risk vectors (breaking API, security injection, secret leak, perf regression, missing tests, unhandled exceptions, schema breaking):

```bash
# Evaluate current working changes:
git diff | python skills/laya-review-gate/run.py

# Evaluate specific commit:
git diff HEAD~1 | python skills/laya-review-gate/run.py
```
Exit code `0` on APPROVE, exit code `1` on REJECT / CHANGES REQUIRED.

### Context Compactor (`laya-compact`)
Prune disposable noise and terminal vomit from session context:

```bash
# Compact conversation transcript:
python skills/laya-compact/run.py --transcript /path/to/transcript.jsonl

# Compact raw command output or logs:
cat build.log | python skills/laya-compact/run.py
```

### Surgical Context Retrieval (`laya-grep` / jevgrep)
Extract strictly relevant 20-30 line snippets instead of loading full files into LLM context:

```bash
python skills/laya-grep/run.py "detect infinite loop" lib/
```

---

## 5. Core Engine Modules (`lib/`)

- **`lib/client.py`**: Lightweight HTTP client querying the local daemon.
- **`lib/compaction.py`**: Pruning engine distinguishing noise/logs from critical state.
- **`lib/judge.py`**: Test coverage requirement evaluator.
- **`lib/memory_gate.py`**: Gate judging durable lessons vs task-specific noise for long-term memory.
- **`lib/loop_detector.py`**: Step history repetition/thrashing judge & task output rubric evaluator.
- **`lib/surgical_retrieval.py`**: Sliding window code snippet chunker & semantic ranker (`jevgrep`).
- **`lib/skill_picker.py`**: User intent to skill classifier.
- **`lib/file_ranker.py`**: Intent-based candidate path ranker.
- **`lib/review_gate.py`**: 7-point risk gate evaluator.
- **`lib/browser_nav.py`**: Goal-based interactive DOM element selector.
- **`lib/rule_enforcer.py`**: Hard security and safety guardrail.

---

## 6. Benchmarks & Performance Benefits

Benchmarked directly against an active full-stack codebase (`Native-App` - React Native / Expo / Drizzle):

| Metric | Without Laya (Frontier LLM Roundtrip) | With Laya (MPS GPU System 1 Engine) | Real-World Impact |
| :--- | :--- | :--- | :--- |
| **Intent & Skill Routing** | ~1,400 ms \| 500 tokens | **133 ms** \| **0 tokens** | **10.5x faster**, 100% token savings |
| **Pre-Tool-Use Guardrail** | ~1,600 ms \| 750 tokens | **~50 ms** \| **0 tokens** | **~25x faster**, blocks before disk touch |
| **Code Retrieval (`db/`)** | 794 tokens (full file dump) | **600 tokens** (surgical snippets) | **24.4% context token reduction** |
| **Context Compaction** | 100% build logs retained | **80–90%** terminal noise pruned | Keeps LLM prompt lean |

---

## 7. Overcoming the Small Context Size Bottleneck

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

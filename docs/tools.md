# AgentReflex Tool Reference

Comprehensive reference for all System 1 decision and safety tools provided by AgentReflex.

Each tool runs locally against the resident Laya daemon in sub-50ms on GPU (MPS/CUDA), eliminating expensive frontier model roundtrips for discrete binary and ranking decisions.

---

1. Check Violations
   - **What it does**: Inspects proposed shell commands or file edits before execution, catching security risks, hardcoded credentials/secrets, and destructive commands (`rm -rf`, raw database drops).
   - **Input**:
     - `action_type`: `"command"` or `"file_edit"`.
     - `target`: Command line string or file path.
     - `content`: Command arguments or code diff/content to be written.
   - **Output**:
     - `violates`: Boolean (`true` if risk certainty >= 0.80).
     - `reason`: Explanation of the violation (e.g. credential leak, destructive shell pattern).
     - `score`: Confidence score (`0.0` to `1.0`).

2. Surgical Code Retrieval (jevgrep)
   - **What it does**: Performs semantic code retrieval across target files. Automatically detects file language (Rust, Python, TypeScript, Go, C/C++, Java) and extracts complete syntactic blocks (functions, classes, impl blocks) via tree-sitter AST, falling back to sliding windows for plain text or markup. Scores snippets locally via Laya in ~30ms, returning strictly relevant code.
   - **User Skill Access**: Usable via skill **`/reflex-grep`** (or `skills/reflex-grep/run.py`).
   - **Input**:
     - `query`: Search intent or target logic description.
     - `paths`: List of files or directories to search.
   - **Output**:
     - `snippets`: Ranked list of matches containing file path, line numbers (`start_line` to `end_line`), snippet text, chunk type (`ast_function_item`, `ast_class_definition`, etc.), and relevance score.

3. Context Compactor
   - **What it does**: Prunes disposable terminal noise, progress bars, package download spinners, and repetitive logs from command outputs or conversation transcript steps.
   - **User Skill Access**: Usable via skill **`/reflex-compact`** (or `skills/reflex-compact/run.py`).
   - **Input**:
     - `text`: Raw command output string, or transcript step content.
   - **Output**:
     - `should_prune`: Boolean indicating whether content is disposable noise.
     - `cleaned_text`: Stripped high-signal content with noise removed.
     - `noise_score`: Neural noise confidence score.

4. Trajectory Pruner
   - **What it does**: Analyzes multi-turn agent conversation history to identify and remove obsolete resolved errors and transient diagnostic listings while preserving durable final state and user goals.
   - **Input**:
     - `transcript_path`: Path to JSONL transcript file, or list of trajectory step objects.
   - **Output**:
     - `pruned_steps`: Count of removed steps.
     - `preserved_steps`: Count of retained high-signal steps.
     - `summary`: Compacted trajectory summary preserving active system state.

5. Fast File Ranker
   - **What it does**: Reranks candidate file paths against task intent using continuous neural scoring, ensuring the agent opens only the top 1–2 target files instead of speculatively reading whole directory trees.
   - **User Skill Access**: Usable via skill **`/reflex-fast-explore`** (or `skills/reflex-fast-explore/run.py`).
   - **Input**:
     - `intent`: Task goal or description.
     - `candidate_paths`: List of candidate file paths.
   - **Output**:
     - `ranked_files`: Sorted list of `(file_path, score)` pairs from highest to lowest relevance.

6. Review Gate (7-Point Audit)
   - **What it does**: Evaluates git diffs or pull requests across 7 risk dimensions: breaking API changes, security injections, secrets leaks, performance regressions, test gaps, unhandled exceptions, and contract violations.
   - **User Skill Access**: Usable via skill **`/reflex-review-gate`** (or `skills/reflex-review-gate/run.py`).
   - **Input**:
     - `diff`: Git patch or diff string.
   - **Output**:
     - `passed`: Boolean (`false` if any dimension risk >= 0.70).
     - `flagged_risks`: List of triggered risk categories with individual scores and line references.

7. Test Coverage Judge
   - **What it does**: Evaluates newly modified or created code to determine whether corresponding unit tests or verification steps are required before completing the turn.
   - **Input**:
     - `code_diff`: Modified code diff or newly written functions.
     - `file_path`: Path of the modified file.
   - **Output**:
     - `requires_verification`: Boolean (`true` if uncovered risk >= 0.70).
     - `risk_score`: Uncovered logic risk score.

8. Memory Gate
   - **What it does**: Evaluates post-task lessons and insights, ensuring only durable patterns (`rule`, `architecture`, `gotcha`) are stored in long-term memory while rejecting ephemeral session-specific noise.
   - **Input**:
     - `lesson_text`: Proposed memory insight or takeaway.
     - `context`: Summary of the task just executed.
   - **Output**:
     - `should_promote`: Boolean (`true` if pattern is permanently valuable).
     - `category`: `"rule"`, `"architecture"`, `"gotcha"`, or `"ephemeral"`.

9. Intent & Skill Router
   - **What it does**: Classifies user prompts into 8 task categories and directly maps them to the optimal skill (`reflex-fast-explore`, `/reflex-review-gate`, `/reflex-compact`, `/reflex-grep`) with 0ms overhead on top of model routing.
   - **Input**:
     - `prompt`: User prompt text.
   - **Output**:
     - `task_class`: Classified task category.
     - `recommended_skill`: Target skill name or `None`.
     - `summary_tag`: Injected context router tag.

10. Loop Detector
    - **What it does**: Monitors sequential agent actions and detects repetitive loops (e.g. repeated identical tool calls or stuck error recovery cycles) in real time.
    - **Input**:
      - `recent_actions`: List of last 3–6 tool invocations, arguments, and responses.
    - **Output**:
      - `is_looping`: Boolean (`true` if runaway loop detected).
      - `reason`: Description of repeated tool patterns or stuck state.

11. Trajectory Budget Governor
    - **What it does**: Monitors turn tool call counts, token consumption, and exploration velocity. Intercepts runaway agent exploration spirals before budget limits are exceeded.
    - **Input**:
      - `total_tool_calls`: Tool calls made in current turn.
      - `recent_actions`: Recent action history.
      - `task_goal`: Original user objective.
    - **Output**:
      - `allow_action`: Boolean (`false` if budget exceeded or exploration stalled).
      - `reason`: Explanation if denied.
      - `metrics`: Current tool count and budget percentages.

12. Task Completion Validator
    - **What it does**: Verifies whether modified code diffs and test results actually satisfy the user's prompt objectives, preventing premature victory declarations or unnecessary follow-up loops.
    - **Input**:
      - `user_goal`: User's original request.
      - `git_diff`: Resulting code changes.
      - `test_output`: Output from test suite execution.
    - **Output**:
      - `is_complete`: Boolean (`true` if requirements satisfied and verified).
      - `missing_gaps`: List of missing requirements or failing edge cases.

13. Speculative Task Triage
    - **What it does**: Performs parallel multi-question triage in a single forward pass, classifying task type, database migration needs, test requirements, auth sensitivity, and breaking risk level.
    - **Input**:
      - `user_prompt`: Incoming user prompt text.
    - **Output**:
      - `tags`: Dictionary of classification dimensions.
      - `summary_tag`: Typed bracket tag injected into prompt context.

14. Hallucinated Parameter Gate
    - **What it does**: Validates CLI flags (`git`, `npm`, `pytest`, `cargo`), tool arguments, and target disk paths before execution to intercept hallucinated options before running.
    - **Input**:
      - `tool_name`: Name of tool to execute.
      - `tool_args`: Argument dictionary.
    - **Output**:
      - `is_valid`: Boolean.
      - `suggestion`: Corrected command syntax or valid argument suggestion.

15. Semantic Action Cache ("Learn to Skip")
    - **What it does**: Caches successful idempotent diagnostic sequences bound to repository git state. Replays verified read-only diagnostic sequences instantly in <10ms with 100% token savings.
    - **Input**:
      - `intent`: User prompt or diagnostic goal.
      - `git_head`: Current git commit hash.
    - **Output**:
      - `cache_hit`: Boolean.
      - `actions`: List of pre-verified tool calls to replay.
      - `confidence`: Semantic match confidence score.

16. Dynamic Model Router
    - **What it does**: Classifies prompt complexity across 8 task categories and dynamically maps it to the optimal model tier (`flash`, `standard`, `frontier`), reasoning effort, and thinking token budget.
    - **Input**:
      - `prompt`: User prompt text.
      - `harness`: Runtime agent harness (e.g. `"agy"`, `"claude"`, `"generic"`).
    - **Output**:
      - `tier`: Recommended model tier (`flash`, `standard`, `frontier`).
      - `effort`: Reasoning effort level (`low`, `medium`, `high`).
      - `thinking_budget`: Recommended token budget.
      - `summary_tag`: Injected context tag.

17. DOM Element Selector
    - **What it does**: Evaluates candidate interactive browser DOM elements against user navigation goals, choosing the single optimal element locally in ~40ms and avoiding massive raw HTML token dumps to LLMs.
    - **Input**:
      - `goal`: Web browsing navigation goal or click intent.
      - `candidates`: List of interactive candidate DOM element dictionaries (`tag`, `text`, `role`, `selector`, `id`).
    - **Output**:
      - `winner`: Winning candidate element dictionary (or `None`).
      - `choice_key`: Selected candidate identifier.
      - `confidence`: Confidence score.


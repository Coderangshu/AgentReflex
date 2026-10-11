import json
import os
import shutil
import time
from pathlib import Path

# Paths
TARGET_DIR = Path("/Users/angshuman/git/doomsday/projects/notemaking")
SCRATCH_DIR = TARGET_DIR / "api" / "_benchmark_tmp"
RESULTS_FILE = Path("/Users/angshuman/git/AgentReflex/benchmark_crud_results.json")

# Ensure clean scratch dir
if SCRATCH_DIR.exists():
    shutil.rmtree(SCRATCH_DIR)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

test_file = SCRATCH_DIR / "sample_note.py"

# Benchmark 1: CRUD Operations (Create, Read, Update, Delete)
results = {
    "crud_ops": {},
    "search_ops": {},
    "speculative_prefetch": {},
}

print("Running CRUD operations benchmark...")

# 1. CREATE
t0 = time.perf_counter()
initial_code = '''"""Sample Note Service Module."""

def create_note(title: str, content: str, user_id: int) -> dict:
    return {"title": title, "content": content, "user_id": user_id, "status": "draft"}

def get_note_by_id(note_id: int) -> dict:
    return {"id": note_id, "title": "Existing Note"}
'''
test_file.write_text(initial_code, encoding="utf-8")
t_create = (time.perf_counter() - t0) * 1000
results["crud_ops"]["CREATE_file"] = {"time_ms": round(t_create, 3), "bytes": len(initial_code)}

# 2. READ (Sequential file read)
t0 = time.perf_counter()
content_read = test_file.read_text(encoding="utf-8")
t_read = (time.perf_counter() - t0) * 1000
results["crud_ops"]["READ_file"] = {"time_ms": round(t_read, 3), "lines": len(content_read.splitlines())}

# 3. UPDATE (Modify function)
t0 = time.perf_counter()
updated_code = content_read.replace('"status": "draft"', '"status": "published", "updated_at": 1729000000')
test_file.write_text(updated_code, encoding="utf-8")
t_update = (time.perf_counter() - t0) * 1000
results["crud_ops"]["UPDATE_file"] = {"time_ms": round(t_update, 3), "bytes": len(updated_code)}

# 4. DELETE
t0 = time.perf_counter()
test_file.unlink()
t_delete = (time.perf_counter() - t0) * 1000
results["crud_ops"]["DELETE_file"] = {"time_ms": round(t_delete, 3)}

# Clean up benchmark scratch
shutil.rmtree(SCRATCH_DIR, ignore_errors=True)

print("Running Search Operations (Standard Full-File Grep vs AST Surgical Jevgrep)...")

# Target real files in notemaking
views_py = TARGET_DIR / "api" / "views.py"
models_py = TARGET_DIR / "api" / "models.py"

query = "NoteViewSet"

# A. Standard naive grep/file load (Without AgentReflex AST jevgrep)
t0 = time.perf_counter()
full_views = views_py.read_text(encoding="utf-8")
naive_matches = [line for line in full_views.splitlines() if query in line]
t_naive = (time.perf_counter() - t0) * 1000
naive_tokens_est = len(full_views) // 4  # Standard LLM context tokens dumped

# B. With AgentReflex surgical_search (AST Chunking + Laya Scoring)
from lib.surgical_retrieval import surgical_search

t0 = time.perf_counter()
ast_res = surgical_search(query, [str(views_py), str(models_py)], max_snippets=2)
t_ast = (time.perf_counter() - t0) * 1000

ast_snippets = ast_res if isinstance(ast_res, list) else ast_res.get("snippets", [])
ast_tokens_est = sum(len(s.get("snippet", "")) for s in ast_snippets) // 4

results["search_ops"] = {
    "query": query,
    "without_agentreflex": {
        "strategy": "Full file read / raw dump",
        "time_ms": round(t_naive, 3),
        "context_tokens_dumped": naive_tokens_est,
        "matches_found": len(naive_matches),
    },
    "with_agentreflex": {
        "strategy": "Tree-sitter AST syntax boundary + Laya scoring",
        "time_ms": round(t_ast, 3),
        "context_tokens_dumped": ast_tokens_est,
        "snippets_returned": len(ast_snippets),
        "token_reduction_pct": round((1 - ast_tokens_est / max(naive_tokens_est, 1)) * 100, 1),
    },
}

print("Running Speculate-and-Verify Tool Prefetch Benchmark...")

from lib.tool_prefetch import predict_speculative_action, execute_speculative_action
from daemon.server import prefetch_trigger, prefetch_claim, prefetch_invalidate, PrefetchTriggerPayload, PrefetchClaimPayload

# Prompt referencing views.py
prompt = f"Check the NoteViewSet permissions in {views_py}"

# 1. Without prefetch: Frontier LLM wait + sequential tool execution
# Measure pure tool execution time
t0 = time.perf_counter()
seq_res = execute_speculative_action("view_file", {"AbsolutePath": str(views_py)})
t_seq = (time.perf_counter() - t0) * 1000

# 2. With prefetch:
# T0: Hook predicts and triggers prefetch in background
t0 = time.perf_counter()
pred = predict_speculative_action(prompt, cwd=str(TARGET_DIR))
t_predict = (time.perf_counter() - t0) * 1000

# Trigger background execution
prefetch_trigger(PrefetchTriggerPayload(tool=pred["tool"], args=pred["args"], cwd=str(TARGET_DIR)))

# Simulate LLM thinking delay (500ms)
time.sleep(0.5)

# T1: When tool call arrives, claim prefetch from RAM
t0 = time.perf_counter()
claim_res = prefetch_claim(PrefetchClaimPayload(tool=pred["tool"], args=pred["args"]))
t_claim = (time.perf_counter() - t0) * 1000

results["speculative_prefetch"] = {
    "target_tool": pred["tool"] if pred else "unknown",
    "target_args": pred["args"] if pred else {},
    "prediction_time_ms": round(t_predict, 3),
    "without_prefetch_tool_exec_ms": round(t_seq, 3),
    "with_prefetch_claim_time_ms": round(t_claim, 3),
    "latency_speedup_x": round(t_seq / max(t_claim, 0.001), 1),
    "cache_hit": claim_res.get("hit", False),
}

# Write results
RESULTS_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
print("\n=== BENCHMARK COMPLETED ===")
print(json.dumps(results, indent=2))

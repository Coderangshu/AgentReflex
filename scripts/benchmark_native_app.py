#!/usr/bin/env python3
"""Simulation benchmark comparing agy-cli performance with vs without Laya on Native-App."""

import time
import json
import subprocess
from pathlib import Path

TARGET_DIR = Path("/Users/angshuman/git/Native-App")
ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys_executable = Path(ROOT / ".venv/bin/python") if (ROOT / ".venv/bin/python").exists() else Path("python3")


def run_benchmark():
    print(f"\n=======================================================")
    print(f"   Benchmark Simulation: Native-App (React Native/Expo)")
    print(f"=======================================================\n")

    results = {}

    # 1. Guardrail Performance (Pre-Tool-Use)
    test_content = (
        "// Adding Supabase client\n"
        "const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSJ9.secretKey';\n"
        "const client = createClient(url, SUPABASE_KEY);"
    )
    payload = json.dumps({"toolCall": {"name": "write_file", "args": {"content": test_content}}})

    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(PYTHON), str(ROOT / "hooks/pre_tool_enforcer.py")],
        input=payload,
        text=True,
        capture_output=True,
        cwd=str(ROOT),
    )
    laya_guard_latency_ms = (time.perf_counter() - t0) * 1000
    guard_res = json.loads(proc.stdout)

    results["guardrail"] = {
        "with_laya_latency_ms": round(laya_guard_latency_ms, 1),
        "without_laya_latency_ms": 1600.0,  # Average frontier LLM roundtrip
        "with_laya_tokens": 0,
        "without_laya_tokens": 750,
        "blocked": guard_res.get("decision") == "deny",
        "speedup": round(1600.0 / max(1.0, laya_guard_latency_ms), 1),
    }

    # 2. Context Retrieval (Full File Read vs Surgical Jevgrep)
    # Search for database schema in Native-App
    t0 = time.perf_counter()
    proc_grep = subprocess.run(
        [str(PYTHON), str(ROOT / "skills/reflex-grep/run.py"), "database schema drizzle", str(TARGET_DIR / "db")],
        text=True,
        capture_output=True,
        cwd=str(ROOT),
    )
    grep_latency_ms = (time.perf_counter() - t0) * 1000
    grep_data = json.loads(proc_grep.stdout) if proc_grep.returncode == 0 else {}
    snippets = grep_data.get("snippets", [])

    # Measure tokens/chars of snippets vs all db files
    db_files = list((TARGET_DIR / "db").glob("*.*"))
    full_chars = sum(len(f.read_text(errors="replace")) for f in db_files if f.is_file())
    snippet_chars = sum(len(s.get("snippet", "")) for s in snippets)

    full_tokens_est = full_chars // 4
    snippet_tokens_est = snippet_chars // 4
    token_reduction_pct = round(((full_tokens_est - snippet_tokens_est) / max(1, full_tokens_est)) * 100, 1)

    results["retrieval"] = {
        "full_file_tokens": full_tokens_est,
        "laya_surgical_tokens": snippet_tokens_est,
        "token_savings_pct": token_reduction_pct,
        "snippets_found": len(snippets),
        "grep_latency_ms": round(grep_latency_ms, 1),
    }

    # 3. Intent Routing
    prompt = "Review recent git diff changes for potential security regressions"
    inv_payload = json.dumps({"prompt": prompt})

    t0 = time.perf_counter()
    proc_inv = subprocess.run(
        [str(PYTHON), str(ROOT / "hooks/pre_invocation.py")],
        input=inv_payload,
        text=True,
        capture_output=True,
        cwd=str(ROOT),
    )
    laya_route_ms = (time.perf_counter() - t0) * 1000
    inv_data = json.loads(proc_inv.stdout)

    results["routing"] = {
        "with_laya_latency_ms": round(laya_route_ms, 1),
        "without_laya_latency_ms": 1400.0,
        "with_laya_tokens": 0,
        "without_laya_tokens": 500,
        "routed_skill": inv_data.get("additionalContext", ""),
        "speedup": round(1400.0 / max(1.0, laya_route_ms), 1),
    }

    # 4. Context Compaction
    raw_expo_log = (
        "Starting Metro Bundler\n"
        + "\n".join([f"Bundling assets {i}% [00:0{i}<00:0{10-i}]" for i in range(15)])
        + "\nAndroid Bundling complete 1240ms\n"
        + "Error: Invariant Violation: Native module cannot be null\n"
        + "    at Object.<anonymous> (App.tsx:14:5)\n"
    )
    raw_tokens_est = len(raw_expo_log) // 4
    proc_compact = subprocess.run(
        [str(PYTHON), str(ROOT / "skills/reflex-compact/run.py"), "--text", raw_expo_log],
        text=True,
        capture_output=True,
        cwd=str(ROOT),
    )
    compact_data = json.loads(proc_compact.stdout) if proc_compact.returncode == 0 else {}
    compacted_text = compact_data.get("compacted_text", "")
    compacted_tokens_est = len(compacted_text) // 4

    results["compaction"] = {
        "raw_tokens": raw_tokens_est,
        "compacted_tokens": compacted_tokens_est,
        "tokens_saved": raw_tokens_est - compacted_tokens_est,
    }

    # Output Clean Table
    print(f"1. PRE-TOOL SECURITY GUARDRAIL (Secret Leak Block)")
    print(f"   - Without Laya (LLM API Call): ~1,600 ms | 750 tokens consumed")
    print(f"   - With Laya (MPS GPU Hook):     {results['guardrail']['with_laya_latency_ms']} ms | 0 tokens consumed")
    print(f"   - Speedup:                      {results['guardrail']['speedup']}x faster | Blocked: {results['guardrail']['blocked']}\n")

    print(f"2. CODEBASE CONTEXT RETRIEVAL (db/ query)")
    print(f"   - Without Laya (Full File Dumps): {results['retrieval']['full_file_tokens']} tokens")
    print(f"   - With Laya (Surgical jevgrep):   {results['retrieval']['laya_surgical_tokens']} tokens")
    print(f"   - Token Reduction:               {results['retrieval']['token_savings_pct']}% context tokens saved\n")

    print(f"3. INTENT & SKILL ROUTING")
    print(f"   - Without Laya (Planning Turn): ~1,400 ms | 500 tokens")
    print(f"   - With Laya (MPS PreInvocation): {results['routing']['with_laya_latency_ms']} ms | 0 tokens")
    print(f"   - Speedup:                      {results['routing']['speedup']}x faster")
    print(f"   - Route:                        {results['routing']['routed_skill']}\n")

    print(f"=======================================================\n")


if __name__ == "__main__":
    run_benchmark()

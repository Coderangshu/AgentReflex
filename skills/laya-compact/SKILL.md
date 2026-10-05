---
name: laya-compact
description: Compacts conversation transcript and working memory using Laya System 1 decision engine, pruning disposable terminal outputs and noise while preserving critical state.
---

# Laya Context Compaction Instructions

Use this skill when the user asks to compact, prune, summarize, or compress memory/context:
1. Run the local compaction tool:
   `python <path-to-sys1-helper>/skills/laya-compact/run.py --transcript <transcript_file>`
   Or pipe arbitrary text/logs via stdin:
   `cat <log_file> | python <path-to-sys1-helper>/skills/laya-compact/run.py`
2. The tool scores every block using Laya's local router (<30ms) and filters out verbose progress logs, keeping only critical commands, code, errors, and requirements.
3. Review the distilled summary and proceed with a clean context.

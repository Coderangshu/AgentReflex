---
name: laya-grep
description: Performs surgical code retrieval (jevgrep) using local Laya scoring. Returns only the strictly relevant 15-30 lines of code instead of loading full files into context.
---

# Surgical Retrieval Instructions (jevgrep)

When searching for specific functions, implementations, or definitions:
1. Instead of reading entire files with `view_file` (which consumes hundreds of tokens), run surgical search:
   `python <path-to-sys1-helper>/skills/laya-grep/run.py "<query>" <files_or_directories...>`
2. Inspect only the returned snippets with exact line ranges.
3. This conserves 80-90% of working memory context tokens.

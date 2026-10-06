---
name: reflex-fast-explore
description: Rapidly scores and ranks candidate file paths locally so you only open the top matches.
---

# Fast Explore Instructions

When searching for code files:
1. Gather candidate paths using `find` or `rg --files`.
2. Run the local scoring script:
   `python <path-to-agentreflex>/skills/reflex-fast-explore/run.py "<search_intent>" <file_paths...>`
3. Only inspect the top 1 or 2 files returned.

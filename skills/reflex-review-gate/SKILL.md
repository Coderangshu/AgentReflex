---
name: reflex-review-gate
description: Evaluates git diffs and pull requests against a 7-point risk gate before merging or committing.
---

# Review Gate Instructions

When reviewing code, pull requests, or git diffs:
1. Generate the git diff using `git diff HEAD~1` or `git diff --cached`.
2. Run the review gate script:
   `python <path-to-agentreflex>/skills/reflex-review-gate/run.py [diff_file_or_patch]`
   Or pipe git diff via stdin:
   `git diff | python <path-to-agentreflex>/skills/reflex-review-gate/run.py`
3. Inspect the 7-dimension risk scores and only proceed if the gate returns APPROVE.

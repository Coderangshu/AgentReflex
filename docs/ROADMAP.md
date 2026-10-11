# Roadmap

This roadmap tracks partially implemented and planned System 1 optimizations for upcoming AgentReflex releases.

For the comprehensive reference of all implemented tools and parameters, see [Tool Reference](tools.md).

---

## Planned & Partially Implemented Optimizations

- [ ] **Cross-Turn Intent Drift Alarm**: Neural embedding similarity check comparing current execution trajectory steps against original user goal (`step_N` vs `prompt`). Triggers proactive soft course-correction injection when semantic distance indicates the agent is wandering off-topic during long multi-turn sessions.
- [ ] **Speculate-and-Verify Tool Prefetching**: Predict likely read-only diagnostic tool actions (`view_file`, `git status`, test suite checks) and run them speculatively in the background while frontier LLMs generate responses, cutting time-to-action by 40–60%.
- [ ] **Ephemeral Scratchpad Auto-Janitor**: Post-invocation hook that tracks and cleans disposable scratch files, test dumps, and temporary scripts created during agent execution to maintain repository hygiene.

# Roadmap

This roadmap tracks partially implemented and planned System 1 optimizations for upcoming AgentReflex releases.

For the comprehensive reference of all implemented tools and parameters, see [Tool Reference](tools.md).

---

## Implemented Optimizations

- [x] **Cross-Turn Intent Drift Alarm**: Compares ongoing multi-turn action trajectories against the user's primary goal using resident Laya neural scoring, firing an alarm and halting off-topic tangents before resource waste occurs.

## Planned & Partially Implemented Optimizations

- [ ] **Speculate-and-Verify Tool Prefetching**: Predict likely read-only diagnostic tool actions (`view_file`, `git status`, test suite checks) and run them speculatively in the background while frontier LLMs generate responses, cutting time-to-action by 40–60%.
- [ ] **Ephemeral Scratchpad Auto-Janitor**: Post-invocation hook that tracks and cleans disposable scratch files, test dumps, and temporary scripts created during agent execution to maintain repository hygiene.

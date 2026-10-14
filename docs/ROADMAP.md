# Roadmap

This roadmap tracks partially implemented and planned System 1 optimizations for upcoming AgentReflex releases.

For the comprehensive reference of all implemented tools and parameters, see [Tool Reference](tools.md).

---

## Planned Optimizations

- [ ] **Ephemeral Scratchpad Auto-Janitor**: Post-invocation hook that tracks and cleans disposable scratch files, test dumps, and temporary scripts created during agent execution to maintain repository hygiene.
- [ ] **Traceback Frame Regex Extractor for Speculative Prefetch**: Parse stack frames (`File "...", line N`) from failed command outputs to speculate-fetch culprit source files with 100% precision before the LLM requests them.
- [ ] **ONNX Runtime & INT8 Quantization for CPU-Only Environments**: Export ModernBERT to an INT8 ONNX graph with AVX-512/VNNI acceleration via `CPUExecutionProvider` in `daemon/server.py`. Automatically activates on systems lacking Apple Silicon (MPS) or NVIDIA/AMD GPUs (CUDA/ROCm), reducing CPU inference latency from ~280ms to ~35–50ms.
- [ ] **tree-sitter-language-pack Integration**: Upgrade from `tree_sitter_languages` to `tree_sitter_language_pack` in `lib/surgical_retrieval.py` with unified `CHUNK_NODE_TYPES` for Ruby, PHP, Swift, and Kotlin AST boundary extraction.


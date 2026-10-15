# llama.cpp CPU deployment smoke (secondary)

Not part of the SLM-02 scientific gate.

## Procedure

1. Export / convert `Qwen/Qwen3-1.7B` to GGUF (e.g. `Q4_K_M`).
2. Serve with `llama-server` (CPU).
3. Apply JSON-schema constrained generation using a **projection** of WELL-IR schema if native conversion rejects constructs.
4. Run 10–20 representative gold utterances.
5. Record: load OK, constrained parse OK, tok/s, wall latency, RAM.

## Explicit non-comparisons

Do not treat GGUF scores as interchangeable with the HF BF16/FP scientific baseline.

# SLM-02 QLoRA scaffold (not executed in SLM-01)

This directory proves an SLM-02 handoff is possible. It does **not** authorize training.

## Handoff inputs (from SLM-01 PASS)

- Frozen WELL-IR schema hash (`benchmark/evidence/slm01_provenance.json`)
- Gold corpus + sealed splits
- `export_training_data.py` output JSONL (development split only)
- `config.example.yaml`

## Explicitly not required for SLM-01 closeout

- training run
- adapter artifact
- SLM-02 execution

## Suggested hardware (when authorized)

- NVIDIA 6–8 GB (QLoRA 4-bit) for Qwen3-1.7B
- Keep sequence length short (256–1024)

## Artifact policy

Never commit `adapter_model.*`, `.safetensors`, or `.gguf`. Record only:

- base model id + revision
- training config hash
- dataset semantic id/hash
- adapter digest (external storage)
- evaluation result digest

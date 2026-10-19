# Amendment R1 — Encoder Bake-Off (record)

**Date:** 2026-10-15  
**Authority context:** Post–MB-00 plan amendment (docs only; no training)

## Change

MB-03 becomes a three-arm bake-off:

| Arm | Checkpoint family |
|---|---|
| A | `RoBERTa-base` |
| B | `ModernBERT-base` |
| C | `UltraBERT-150M` (`dmis-lab/UltraBERT-150M`) |

## Constraints retained / added

- MB-03 **BLOCKED** until MB-01 **and** MB-02 accepted.
- Same corpus / splits / labels / fact projector / metrics / seeds / tuning budget.
- MB-04 sealed three-arm eval + lexicographic winner policy (false-OK first).
- MB-05 integrates **selected** encoder with unchanged SLM-03.
- UltraBERT: pin revision; review custom load code; no unpinned `trust_remote_code`.
- Do not dump full documents into UltraBERT for 32K capacity alone.

## Source of generic benchmarks (not WellPlot evidence)

Author table (UltraBERT HF / arXiv `2610.15028`): UltraBERT-150M GLUE 89.5 / RewardBench 73.0 vs ModernBERT 88.4 / 68.0 vs RoBERTa 86.4 / 63.2 under same per-task grid.

## Status

Docs updated. **No MB-01/MB-03 implementation in this amendment.**  
Await MB-00 acceptance, then MB-01 authority.

"""Experiment filesystem roots."""

from __future__ import annotations

from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = EXPERIMENT_ROOT / "evidence"
ARTIFACTS_DIR = EXPERIMENT_ROOT / "artifacts"

# Frozen SLM-03 / corpus live under the sibling SLM experiment (read-only references).
REPO_ROOT = EXPERIMENT_ROOT.parents[1]
SLM01_ROOT = REPO_ROOT / "experiments" / "nlp_slm_01"
SLM03_ADAPTER = SLM01_ROOT / "artifacts" / "adapters" / "slm03_qwenv17_qlora"
SLM03_EVIDENCE = SLM01_ROOT / "benchmark" / "evidence"

"""Failure taxonomy helpers and learnability statistics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from benchmark.taxonomy import IR_BLOCKERS, LEARNABLE


def summarize_taxonomy(labels: list[str]) -> dict[str, Any]:
    counts = Counter(labels)
    model_semantic = [lab for lab in labels if lab in LEARNABLE or lab in {
        "alias_resolution",
        "composition",
        "relation",
        "units",
        "deictic",
        "ordering",
        "envelope_misuse",
    }]
    # confirmed model-semantic failures = LEARNABLE ∪ envelope etc already in LEARNABLE
    confirmed = [lab for lab in labels if lab in LEARNABLE]
    learnable_share = (
        sum(1 for lab in confirmed if lab in LEARNABLE) / len(confirmed) if confirmed else None
    )
    ir_share = (
        sum(1 for lab in labels if lab in IR_BLOCKERS) / len(labels) if labels else None
    )
    return {
        "counts": dict(counts),
        "confirmed_model_semantic_n": len(confirmed),
        "learnable_share_of_confirmed": learnable_share,
        "ir_limitation_share_of_all_failures": ir_share,
        "model_semantic_labels_seen": sorted(set(model_semantic)),
    }

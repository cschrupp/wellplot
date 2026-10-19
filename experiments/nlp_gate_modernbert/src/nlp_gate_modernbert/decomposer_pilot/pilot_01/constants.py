"""Frozen DECOMPOSER-PILOT-01 pins."""

from __future__ import annotations

AUTH = "WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-01-AUTH-001"
SLICE = "DECOMPOSER-PILOT-01"
STARTING_TIP = "bad4ad33f1dd6f0c6976e8213012f66e16f19ea9"
AUTHORITY_REMOTE_HEAD = "9fbfb74cac97773519171a6b30fa6865e6201b8e"

INVOCATION_ORDER = (
    "D5GAP-0085",
    "D5GAP-0089",
    "D5GAP-0117",
    "D5GAP-0096",
    "D5GAP-0101",
    "SEED-cm-9643c020e2e02463",
)

EXPECTED_INFERENCE_CONFIG_SHA256 = (
    "6daab17278547241563d1bc6bec92fcdd882ed48c8de3e18db81e737c732b54b"
)
HIGH_LEVEL_CALLS_AUTHORIZED = 6

# Layer-2 critical mechanism attribution (frozen design Q5).
MECHANISM_ATTRIBUTION = {
    "composition": {
        "labels": frozenset(
            {
                "MISSING_TASK",
                "WRONG_OPERATION",
                "SEMANTIC_UNDERSPECIFICATION",
                "SEMANTIC_OVERREACH",
            }
        ),
        "only_on_cases": frozenset({"D5GAP-0096", "D5GAP-0101"}),
    },
    "local_binding": {
        "labels": frozenset({"WRONG_BINDING", "WRONG_DEPENDENCY"}),
        "only_on_cases": frozenset({"D5GAP-0096", "D5GAP-0101"}),
    },
    "required_ordering": {
        "labels": frozenset({"WRONG_ORDER"}),
        "only_on_cases": frozenset(
            {"D5GAP-0085", "D5GAP-0089", "SEED-cm-9643c020e2e02463"}
        ),
    },
    "independent_order_handling": {
        "labels": frozenset({"WRONG_DEPENDENCY", "WRONG_ORDER"}),
        "only_on_cases": frozenset({"D5GAP-0096", "D5GAP-0117"}),
    },
    "reference_resolution": {
        "labels": frozenset({"WRONG_OPERAND", "WRONG_BINDING", "MISSING_TASK"}),
        "only_on_cases": frozenset({"D5GAP-0085", "D5GAP-0089"}),
    },
}

PROBE_CASES = {
    "composition": frozenset({"D5GAP-0096", "D5GAP-0101"}),
    "local_binding": frozenset({"D5GAP-0096", "D5GAP-0101"}),
    "required_ordering": frozenset(
        {"D5GAP-0085", "D5GAP-0089", "SEED-cm-9643c020e2e02463"}
    ),
    "independent_order_handling": frozenset({"D5GAP-0096", "D5GAP-0117"}),
    "reference_resolution": frozenset({"D5GAP-0085", "D5GAP-0089"}),
}

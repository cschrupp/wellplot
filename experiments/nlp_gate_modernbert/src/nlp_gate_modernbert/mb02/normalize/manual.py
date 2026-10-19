"""Explicit MANUAL_NORMALIZATION residuals (source-reviewed; no gold fields).

Populated only when family builders cannot safely extract allowlisted structure
from the kept utterance alone. Values are request structure only.
"""

from __future__ import annotations

from typing import Any

# case_id → NormalizedRequest dict (allowlisted fields only)
MANUAL_BY_CASE: dict[str, dict[str, Any]] = {
    # Seed / complex unsupported — request kind from utterance content
    "SEED-cm-843982294d26902b": {
        "requested_operation": "CREATE_TRACK",
        "query": {"kind": "curve", "text": "CBL"},
    },
    "SEED-cm-5f1b23161fc35b70": {
        "requested_operation": "CREATE_TRACK",
        "query": {"kind": "curve", "text": "TENS"},
    },
    # Source-file-bound curves absent from catalog (utterance cites missing_*.las)
    "SEED-d4-a56636363f8f3535": {
        "requested_operation": "PLACE_CURVE",
        "query": {"kind": "curve", "text": "missing_neutron"},
    },
    "SEED-d4-9a19bd0b9e3522da": {
        "requested_operation": "PLACE_CURVE",
        "query": {"kind": "curve", "text": "missing_resistivity"},
    },
    "D5GAP-0125": {
        "requested_operation": "PLACE_CURVE",
        "query": {"kind": "curve", "text": "neutron"},
        "target": {"kind": "curve", "text": "density"},
    },
    # Track title "QC" is multi-match; PEF is not in fixture catalog — request still
    # targets the QC track title from the utterance.
    "D5GAP-0123": {
        "requested_operation": "PLACE_CURVE",
        "query": {"kind": "curve", "text": "PEF"},
        "target": {"kind": "track", "text": "QC"},
    },
    "D5GAP-0081": {
        "requested_operation": "DEFINE_FILL",
        "fill": {
            "mode": "BETWEEN",
            "primary_query": "wide CBL",
            "predicate": {"kind": "BETWEEN_CURVES", "secondary_query": "narrow CBL"},
            "asserts_scale_mismatch": True,
        },
    },
}

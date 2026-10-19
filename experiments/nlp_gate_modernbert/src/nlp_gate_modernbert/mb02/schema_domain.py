"""Schema/domain checks — reuse production ScaleSpec where possible."""

from __future__ import annotations

import sys
from pathlib import Path

from nlp_gate_modernbert.mb02.contracts import NormalizedRequest
from nlp_gate_modernbert.paths import REPO_ROOT

_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from wellplot.model.document import ScaleKind, ScaleSpec  # noqa: E402


def assess_schema_domain(req: NormalizedRequest) -> tuple[bool, str | None]:
    """Return (invalid, reason_code). reason codes are existing WELL-IR families."""
    # Contradictory direction claims
    dirs = list(req.scale_direction_claims or [])
    if "increasing" in dirs and "decreasing" in dirs:
        return True, "contradictory_scale_direction"

    # Contradictory exclusive targets
    if len(set(req.target_claims or [])) >= 2:
        return True, "contradictory_target"

    sb = req.scale_bounds
    if sb is not None and sb.minimum is not None and sb.maximum is not None:
        kind = ScaleKind.LOG if sb.kind == "log" else ScaleKind.LINEAR
        try:
            ScaleSpec(kind=kind, minimum=float(sb.minimum), maximum=float(sb.maximum))
        except ValueError as exc:
            msg = str(exc).lower()
            if "positive" in msg or "log" in msg:
                return True, "invalid_log_scale_bounds"
            return True, "invalid_scale_bounds"

    ib = req.interval_bounds
    if ib is not None and ib.top is not None and ib.base is not None:
        if float(ib.top) == float(ib.base):
            return True, "invalid_interval_zero_span"
        if float(ib.top) > float(ib.base):
            return True, "invalid_interval_order"

    if req.alpha is not None:
        if not (0.0 <= float(req.alpha) <= 1.0):
            # Prefer existing gold reason families
            if req.fill is not None:
                return True, "invalid_fill_alpha"
            return True, "invalid_alpha"

    if req.line_width is not None:
        if float(req.line_width) <= 0:
            return True, "invalid_line_width"

    if req.requested_unit is not None:
        unit = req.requested_unit.lower()
        if unit not in {"m", "ft", "cm", "mm", "in"}:
            return True, "unsupported_unit"

    return False, None

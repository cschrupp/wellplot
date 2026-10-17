from __future__ import annotations

import pytest
from pydantic import ValidationError

from well_ir.canonicalize import assert_ok_refs_resolved, parse_well_ir
from well_ir.selectors import ResolvedRef


def test_parse_ok_place_curve() -> None:
    result = parse_well_ir(
        {
            "status": "ok",
            "well_ir_version": "1.0",
            "ops": [
                {
                    "op": "place_curve",
                    "curve": {"kind": "curve", "ref": "RHOB"},
                    "target": {
                        "mode": "relative",
                        "relation": "with",
                        "reference": {"kind": "curve", "ref": "NPHI"},
                    },
                }
            ],
        }
    )
    assert result.status == "ok"
    assert_ok_refs_resolved(result)


def test_resolved_ref_requires_exactly_one_binding() -> None:
    with pytest.raises(ValidationError):
        ResolvedRef(kind="curve", ref="RHOB", local_ref="$x")


def test_ambiguous_envelope() -> None:
    result = parse_well_ir(
        {
            "status": "ambiguous",
            "well_ir_version": "1.0",
            "ambiguities": [{"field": "curve", "candidates": ["RHOB", "RHOZ"], "query": "density"}],
        }
    )
    assert result.status == "ambiguous"

"""Static WELL-IR 1.2-candidate capability registry (experiment-side inventory)."""

from __future__ import annotations

from nlp_gate_modernbert.mb02.contracts import NormalizedRequest

# Operations representable as WELL-IR ops in the frozen 1.2-candidate surface.
_SUPPORTED_OPS = {
    "PLACE_CURVE",
    "MOVE_CURVE",
    "REMOVE_CURVE",
    "CONFIGURE_CURVE_DISPLAY",
    "SET_INTERVAL",
    "CREATE_TRACK",
    "DEFINE_FILL",
    "REMOVE_FILL",
}

# Request kinds outside WELL-IR → operation_not_supported (+ detail)
_UNSUPPORTED_OPS: dict[str, tuple[str, str]] = {
    "RENAME_REPORT": ("operation_not_supported", "report_authoring_outside_well_ir_v1"),
    "SET_PAGE_ORIENTATION": ("operation_not_supported", "page_authoring_outside_well_ir_v1"),
    "ADD_ANNOTATION": ("operation_not_supported", "annotations_outside_well_ir_v1"),
    "INSTANTIATE_TEMPLATE": ("operation_not_supported", "template_instantiation_outside_well_ir_v1"),
    "SELECT_SOURCE": ("operation_not_supported", "source_selection_outside_well_ir_v1"),
    "COMPARE_WELLS": ("operation_not_supported", "multi_well_outside_well_ir_v1"),
    "MULTI_SECTION_LAYOUT": ("operation_not_supported", "cbl_vdl_or_multi_section_construct"),
    "RASTER_WAVEFORM": ("operation_not_supported", "raster_waveform_outside_well_ir_v1"),
    "SECTION_TARGETED_SCALE": ("operation_not_supported", "section_targeting_outside_well_ir_v1"),
}


def assess_capability(req: NormalizedRequest) -> tuple[bool, str | None, str | None]:
    """Return (supported, reason, detail). Reuses frozen WELL-IR reason families only."""
    op = req.requested_operation
    if op in _UNSUPPORTED_OPS:
        reason, detail = _UNSUPPORTED_OPS[op]
        return False, reason, detail
    if op == "UNKNOWN":
        return False, "operation_not_supported", "unknown_request_kind"
    if op not in _SUPPORTED_OPS:
        return False, "operation_not_supported", f"operation_outside_well_ir:{op}"

    # DEFINE_FILL with conditional threshold is unsupported
    if op == "DEFINE_FILL" and req.fill and req.fill.mode == "CONDITIONAL":
        pred = req.fill.predicate
        if pred and pred.kind in {"ABOVE_THRESHOLD", "BELOW_THRESHOLD"}:
            return (
                False,
                "operation_not_supported",
                "conditional_threshold_fill_outside_well_ir_v1",
            )

    # Source / section qualifiers on otherwise supported ops
    if req.source_qualifier:
        return False, "operation_not_supported", "source_selection_outside_well_ir_v1"
    if req.section_qualifier and op == "CONFIGURE_CURVE_DISPLAY":
        return False, "operation_not_supported", "section_targeting_outside_well_ir_v1"

    return True, None, None

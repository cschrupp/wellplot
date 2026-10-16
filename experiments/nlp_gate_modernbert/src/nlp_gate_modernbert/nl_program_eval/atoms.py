"""Declarative REQUIRED_REPRESENTABLE atom checkers (case_id, atom_id) → bool.

Checkers inspect candidate semantic facts only. They do not reconstruct oracle programs.
"""

from __future__ import annotations

from typing import Any, Callable

from nlp_gate_modernbert.mb02.resolve import match_curves
from nlp_gate_modernbert.scope_runtime.contracts import ProgramExecutionResult, ScopeNormalizedProgram

AtomChecker = Callable[[ScopeNormalizedProgram, ProgramExecutionResult], bool]

CheckerKey = tuple[str, str]


def _tasks(program: ScopeNormalizedProgram) -> list:
    return list(program.tasks)


def _reqs(program: ScopeNormalizedProgram):
    return [t.request for t in program.tasks]


def _has_configure_scale(
    program: ScopeNormalizedProgram,
    *,
    query_substr: str | None = None,
    query_exact: str | None = None,
    minimum: float,
    maximum: float,
    kind: str | None = None,
    reverse: bool | None = None,
) -> bool:
    for req in _reqs(program):
        if req.requested_operation != "CONFIGURE_CURVE_DISPLAY":
            continue
        if req.scale_bounds is None:
            continue
        sb = req.scale_bounds
        if sb.minimum != minimum or sb.maximum != maximum:
            continue
        if kind is not None and sb.kind != kind:
            continue
        qtext = (req.query.text or "") if req.query else ""
        if query_exact is not None and qtext != query_exact:
            continue
        if query_substr is not None and query_substr.lower() not in qtext.lower():
            continue
        if reverse is True:
            if "decreasing" not in (req.scale_direction_claims or []):
                continue
        if reverse is False and "decreasing" in (req.scale_direction_claims or []):
            continue
        return True
    return False


def _has_fill_between(program: ScopeNormalizedProgram) -> bool:
    for req in _reqs(program):
        if req.requested_operation != "DEFINE_FILL":
            continue
        fill = req.fill
        if fill is None:
            continue
        if fill.mode in {"BETWEEN_INSTANCES", "BETWEEN"}:
            return True
        if fill.predicate and fill.predicate.kind == "BETWEEN_CURVES":
            return True
    return False


def _has_create_track(
    program: ScopeNormalizedProgram,
    *,
    title: str | None = None,
    width_mm: float | None = None,
) -> bool:
    for req in _reqs(program):
        if req.requested_operation != "CREATE_TRACK":
            continue
        if title is not None and req.track_title != title:
            continue
        if width_mm is not None and req.track_width_mm != width_mm:
            continue
        return True
    return False


def _curve_entity_ids(ws_summary: dict, query: str) -> list[str]:
    # Reconstruct minimal resolution via channel/id in summary is insufficient for aliases;
    # checkers that need alias resolution use program text + runtime adjudicated query.
    return []


def _place_on_bound_track(
    program: ScopeNormalizedProgram,
    *,
    curve_texts: set[str],
) -> bool:
    """PLACE_CURVE whose query text is in curve_texts and target is a local_ref bind."""
    producers = set()
    for t in program.tasks:
        producers.update(t.produces_binds.keys())
    for t in program.tasks:
        req = t.request
        if req.requested_operation != "PLACE_CURVE":
            continue
        q = (req.query.text or "").strip() if req.query else ""
        if q not in curve_texts:
            # also accept case-insensitive / known aliases checked elsewhere
            if q.lower() not in {c.lower() for c in curve_texts}:
                continue
        tgt = req.target
        if tgt is None or not tgt.local_ref:
            continue
        if tgt.local_ref in producers:
            return True
    return False


def _place_curve_texts(program: ScopeNormalizedProgram) -> list[str]:
    out = []
    for req in _reqs(program):
        if req.requested_operation == "PLACE_CURVE" and req.query and req.query.text:
            out.append(req.query.text.strip())
    return out


def _configure_after_create_indices(program: ScopeNormalizedProgram) -> list[int]:
    return [
        i
        for i, t in enumerate(program.tasks)
        if t.request.requested_operation == "CONFIGURE_CURVE_DISPLAY"
    ]


def _task_index_by_op(program: ScopeNormalizedProgram, op: str) -> list[int]:
    return [i for i, t in enumerate(program.tasks) if t.request.requested_operation == op]


def _scale_task_indices(program: ScopeNormalizedProgram) -> list[int]:
    return _task_index_by_op(program, "CONFIGURE_CURVE_DISPLAY")


def _fill_task_indices(program: ScopeNormalizedProgram) -> list[int]:
    return _task_index_by_op(program, "DEFINE_FILL")


def _ordering_scale_before_fill(program: ScopeNormalizedProgram) -> bool:
    scales = _scale_task_indices(program)
    fills = _fill_task_indices(program)
    if not scales or not fills:
        return False
    return max(scales) < min(fills) or (
        # also accept dependency: every fill has a scale ancestor
        all(
            any(_ancestry(program, program.tasks[fi].task_id, program.tasks[si].task_id) for si in scales)
            or fi > max(scales)
            for fi in fills
        )
        and min(fills) > min(scales)
    )


def _ancestry(program: ScopeNormalizedProgram, task_id: str, ancestor_id: str) -> bool:
    by_id = {t.task_id: t for t in program.tasks}
    seen: set[str] = set()
    stack = list(by_id[task_id].depends_on)
    while stack:
        cur = stack.pop()
        if cur == ancestor_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(by_id[cur].depends_on)
    return False


def _gr_before_rt(program: ScopeNormalizedProgram) -> bool:
    gr_i = None
    rt_i = None
    for i, t in enumerate(program.tasks):
        req = t.request
        if req.requested_operation != "PLACE_CURVE" or not req.query or not req.query.text:
            continue
        text = req.query.text.strip().lower()
        if text in {"gr", "gamma", "gamma ray"} and gr_i is None:
            gr_i = i
        if text in {"rt", "resistivity", "res"} and rt_i is None:
            rt_i = i
    if gr_i is None or rt_i is None:
        return False
    return gr_i < rt_i


def _has_split_fill(program: ScopeNormalizedProgram, baseline: float) -> bool:
    for req in _reqs(program):
        if req.requested_operation != "DEFINE_FILL":
            continue
        fill = req.fill
        if fill is None:
            continue
        if fill.mode == "BASELINE_SPLIT" and fill.baseline_value == baseline:
            return True
        if fill.predicate and fill.predicate.kind == "BASELINE_SPLIT" and fill.predicate.value == baseline:
            return True
    return False


def _cali_texts() -> set[str]:
    return {"CALI", "cali", "caliper", "cal"}


def _gr_texts() -> set[str]:
    return {"GR", "gr", "gamma", "gamma ray"}


def _rt_texts() -> set[str]:
    return {"RT", "rt", "resistivity", "res"}


def _rhob_texts() -> set[str]:
    return {"RHOB", "rhob", "density", "bulk density"}


def _place_matches(program: ScopeNormalizedProgram, texts: set[str]) -> bool:
    lowered = {t.lower() for t in texts}
    for q in _place_curve_texts(program):
        if q.lower() in lowered:
            return True
    return False


# --- per-case checkers ---


def _0085_both_cbl(program: ScopeNormalizedProgram, _trace: ProgramExecutionResult) -> bool:
    wide = _has_configure_scale(program, query_substr="wide", minimum=0.0, maximum=100.0)
    narrow = _has_configure_scale(program, query_substr="narrow", minimum=0.0, maximum=100.0)
    # also accept ordinal first/second CBL configures covering both instances
    first = _has_configure_scale(program, query_substr="first", minimum=0.0, maximum=100.0)
    second = _has_configure_scale(program, query_substr="second", minimum=0.0, maximum=100.0)
    return (wide and narrow) or (first and second)


def _0085_scale_before_fill(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _ordering_scale_before_fill(program) and _has_fill_between(program)


def _0085_fill(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_fill_between(program)


def _0089_narrow(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_configure_scale(program, query_substr="narrow", minimum=0.0, maximum=100.0)


def _0089_order(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _ordering_scale_before_fill(program)


def _0089_fill(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_fill_between(program)


def _0117_range(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return any(
        _has_configure_scale(program, query_exact=q, minimum=1.95, maximum=2.95)
        for q in _rhob_texts()
    ) or _has_configure_scale(program, query_substr="rhob", minimum=1.95, maximum=2.95)


def _0117_rev(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    for req in _reqs(program):
        if req.requested_operation != "CONFIGURE_CURVE_DISPLAY":
            continue
        q = (req.query.text or "").lower() if req.query else ""
        if q not in {x.lower() for x in _rhob_texts()}:
            continue
        if "decreasing" in (req.scale_direction_claims or []):
            return True
    return False


def _0117_fill(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_split_fill(program, 2.45)


def _0117_baseline(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_split_fill(program, 2.45)


def _0096_new_track(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_create_track(program)


def _0096_title(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_create_track(program, title="Petrophysics")


def _0096_gr_place(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _place_on_bound_track(program, curve_texts=_gr_texts()) or _place_matches(program, _gr_texts())


def _0096_gr_range(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return any(
        _has_configure_scale(program, query_exact=q, minimum=0.0, maximum=150.0)
        for q in _gr_texts()
    )


def _0096_rt_place(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _place_on_bound_track(program, curve_texts=_rt_texts()) or _place_matches(program, _rt_texts())


def _0096_rt_log(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return any(
        _has_configure_scale(program, query_exact=q, minimum=0.2, maximum=2000.0, kind="log")
        for q in _rt_texts()
    )


def _0101_new(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_create_track(program)


def _0101_title(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_create_track(program, title="Caliper QC")


def _0101_width(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_create_track(program, width_mm=24.0)


def _0101_cali_place(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _place_on_bound_track(program, curve_texts=_cali_texts()) or _place_matches(
        program, _cali_texts()
    )


def _0101_cali_range(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return any(
        _has_configure_scale(program, query_exact=q, minimum=6.0, maximum=12.0)
        for q in _cali_texts()
    )


def _seed_new(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_create_track(program)


def _seed_normal(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    # Canonical default kind — no extra operand required
    return _has_create_track(program)


def _seed_title(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _has_create_track(program, title="Petrophysics")


def _seed_gr_place(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _place_matches(program, _gr_texts())


def _seed_gr_range(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return any(
        _has_configure_scale(program, query_exact=q, minimum=-10.0, maximum=140.0, kind="linear")
        for q in _gr_texts()
    )


def _seed_rt_place(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _place_matches(program, _rt_texts())


def _seed_rt_log(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return any(
        _has_configure_scale(program, query_exact=q, minimum=0.1, maximum=10000.0, kind="log")
        for q in _rt_texts()
    )


def _seed_order(program: ScopeNormalizedProgram, _t: ProgramExecutionResult) -> bool:
    return _gr_before_rt(program)


ATOM_CHECKERS: dict[CheckerKey, AtomChecker] = {
    ("D5GAP-0085", "BOTH_CBL_SCALE_0_100"): _0085_both_cbl,
    ("D5GAP-0085", "SCALE_BEFORE_FILL"): _0085_scale_before_fill,
    ("D5GAP-0085", "FILL_BETWEEN_CBL"): _0085_fill,
    ("D5GAP-0089", "NARROW_CBL_SCALE_0_100"): _0089_narrow,
    ("D5GAP-0089", "SCALE_BEFORE_FILL"): _0089_order,
    ("D5GAP-0089", "FILL_BETWEEN_CBL_INSTANCES"): _0089_fill,
    ("D5GAP-0117", "RHOB_RANGE_1_95_2_95"): _0117_range,
    ("D5GAP-0117", "RHOB_REVERSED"): _0117_rev,
    ("D5GAP-0117", "RHOB_SPLIT_FILL"): _0117_fill,
    ("D5GAP-0117", "SPLIT_BASELINE_2_45"): _0117_baseline,
    ("D5GAP-0096", "NEW_TRACK"): _0096_new_track,
    ("D5GAP-0096", "TRACK_TITLE_PETROPHYSICS"): _0096_title,
    ("D5GAP-0096", "GR_ON_NEW_TRACK"): _0096_gr_place,
    ("D5GAP-0096", "GR_RANGE_0_150"): _0096_gr_range,
    ("D5GAP-0096", "RT_ON_NEW_TRACK"): _0096_rt_place,
    ("D5GAP-0096", "RT_LOG_0_2_2000"): _0096_rt_log,
    ("D5GAP-0101", "NEW_TRACK"): _0101_new,
    ("D5GAP-0101", "TRACK_TITLE_CALIPER_QC"): _0101_title,
    ("D5GAP-0101", "TRACK_WIDTH_24_MM"): _0101_width,
    ("D5GAP-0101", "CALI_ON_NEW_TRACK"): _0101_cali_place,
    ("D5GAP-0101", "CALI_RANGE_6_12"): _0101_cali_range,
    ("SEED-cm-9643c020e2e02463", "NEW_TRACK"): _seed_new,
    ("SEED-cm-9643c020e2e02463", "TRACK_NORMAL_DEFAULT"): _seed_normal,
    ("SEED-cm-9643c020e2e02463", "TRACK_TITLE_PETROPHYSICS"): _seed_title,
    ("SEED-cm-9643c020e2e02463", "GR_ON_NEW_TRACK"): _seed_gr_place,
    ("SEED-cm-9643c020e2e02463", "GR_LINEAR_M10_140"): _seed_gr_range,
    ("SEED-cm-9643c020e2e02463", "RT_ON_NEW_TRACK"): _seed_rt_place,
    ("SEED-cm-9643c020e2e02463", "RT_LOG_0_1_10000"): _seed_rt_log,
    ("SEED-cm-9643c020e2e02463", "GR_BEFORE_RT"): _seed_order,
}


def evaluate_coverage(
    case_id: str,
    required_atom_ids: tuple[str, ...],
    program: ScopeNormalizedProgram,
    trace: ProgramExecutionResult,
) -> tuple[dict[str, bool], list[str]]:
    """Return (atom_id→covered, missing_atom_ids). Fail closed on unknown checker."""
    results: dict[str, bool] = {}
    missing: list[str] = []
    for atom_id in required_atom_ids:
        key = (case_id, atom_id)
        checker = ATOM_CHECKERS.get(key)
        if checker is None:
            raise RuntimeError(f"COMPARATOR_SCOPE_UNSUPPORTED:missing_atom_checker:{key}")
        ok = bool(checker(program, trace))
        results[atom_id] = ok
        if not ok:
            missing.append(atom_id)
    return results, missing

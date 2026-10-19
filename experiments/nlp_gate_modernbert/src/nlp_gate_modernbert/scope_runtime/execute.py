"""Fail-fast NormalizedProgram execution over unchanged MB-02R adjudicate()."""

from __future__ import annotations

from typing import Any

from nlp_gate_modernbert.mb02.adjudicate import adjudicate
from nlp_gate_modernbert.mb02.contracts import NormalizedRequest, ProjectedWorkspace, SemanticQuery
from nlp_gate_modernbert.scope_runtime.contracts import (
    LocalBindingTable,
    ProgramExecutionResult,
    ScopeNormalizedProgram,
    ScopeNormalizedRequest,
    ScopeNormalizedTask,
    ScopeSemanticQuery,
    TaskTraceRecord,
)
from nlp_gate_modernbert.scope_runtime.effects import (
    apply_effect,
    publish_binds_after_create_track,
    workspace_summary,
)


def _task_index(program: ScopeNormalizedProgram) -> dict[str, int]:
    return {t.task_id: i for i, t in enumerate(program.tasks)}


def validate_program_structure(
    program: ScopeNormalizedProgram,
) -> tuple[bool, str | None]:
    """Program-level schema/domain checks before any task runs."""
    ids = [t.task_id for t in program.tasks]
    if len(ids) != len(set(ids)):
        return False, "duplicate_task_id"
    index = _task_index(program)

    # Producers of each bind
    producers: dict[str, str] = {}
    for t in program.tasks:
        for bind_name in t.produces_binds:
            if bind_name in producers:
                return False, "duplicate_bind_producer"
            producers[bind_name] = t.task_id

    for i, t in enumerate(program.tasks):
        # depends_on must be earlier in array order (linear)
        for dep in t.depends_on:
            if dep not in index:
                return False, "unknown_dependency"
            if index[dep] >= i:
                return False, "depends_on_order_contradiction"
        # linear chain: if depends_on present, only prior tasks; non-linear fan-in out of scope
        if len(t.depends_on) > 1:
            return False, "non_linear_dependency_out_of_scope"

        for q in (t.request.query, t.request.secondary_query, t.request.target):
            if q is None:
                continue
            has_text = q.text is not None and str(q.text).strip() != ""
            has_ref = q.local_ref is not None and str(q.local_ref).strip() != ""
            if has_text and has_ref:
                return False, "local_ref_and_text_both_set"
            if has_ref:
                ref = str(q.local_ref).strip()
                if ref not in producers:
                    return False, "local_bind_has_no_producer"
                prod_id = producers[ref]
                if index[prod_id] >= i:
                    return False, "producer_after_consumer"
                # must depend on producer (directly or via chain of depends_on)
                if not _depends_on_ancestry(program, t.task_id, prod_id):
                    return False, "missing_dependency_on_bind_producer"

        # Q1A: track_title/width only meaningful on CREATE_TRACK (warn as schema if used elsewhere)
        if t.request.requested_operation != "CREATE_TRACK":
            if t.request.track_title is not None or t.request.track_width_mm is not None:
                return False, "create_track_operands_on_non_create_track"

    return True, None


def _depends_on_ancestry(
    program: ScopeNormalizedProgram, task_id: str, ancestor_id: str
) -> bool:
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


def _resolve_query(
    q: ScopeSemanticQuery | None,
    bindings: LocalBindingTable,
    ws: ProjectedWorkspace,
) -> tuple[SemanticQuery | None, str | None, int | None, str | None]:
    """Return (mb02_query, source_local_ref, resolved_ref, mb02_text_for_track)."""
    if q is None:
        return None, None, None, None
    if q.local_ref:
        ref_name = str(q.local_ref).strip()
        projected = bindings.get(ref_name)
        if projected is None:
            # Should have been caught by structural validation; treat as schema if reached
            raise ValueError("unresolved_local_ref_at_adapter")
        # Must exist in current workspace
        if not any(t.ref == projected for t in ws.tracks):
            raise ValueError("resolved_bind_not_in_workspace")
        text = f"track {projected}"
        return (
            SemanticQuery(kind=q.kind, text=text),
            ref_name,
            projected,
            text,
        )
    # Q4 XOR already enforced on ScopeSemanticQuery: text path has non-empty text
    return SemanticQuery(kind=q.kind, text=q.text), None, None, None


def to_mb02_request(
    req: ScopeNormalizedRequest,
    bindings: LocalBindingTable,
    ws: ProjectedWorkspace,
) -> tuple[NormalizedRequest, str | None, int | None, str | None]:
    """Build MB-02R adjudication view: no local_ref, no Q1A track fields."""
    source_local_ref = None
    resolved_ref = None
    mb02_query = None

    mq, slr, rr, mt = _resolve_query(req.query, bindings, ws)
    if slr:
        source_local_ref, resolved_ref, mb02_query = slr, rr, mt
    msq, slr2, rr2, mt2 = _resolve_query(req.secondary_query, bindings, ws)
    if slr2:
        source_local_ref, resolved_ref, mb02_query = slr2, rr2, mt2
    mtgt, slr3, rr3, mt3 = _resolve_query(req.target, bindings, ws)
    if slr3:
        source_local_ref, resolved_ref, mb02_query = slr3, rr3, mt3

    mb02 = NormalizedRequest(
        requested_operation=req.requested_operation,
        query=mq,
        secondary_query=msq,
        target=mtgt,
        deictic_reference=req.deictic_reference,
        scale_direction_claims=list(req.scale_direction_claims),
        target_claims=list(req.target_claims),
        scale_bounds=req.scale_bounds,
        interval_bounds=req.interval_bounds,
        alpha=req.alpha,
        line_width=req.line_width,
        requested_unit=req.requested_unit,
        fill=req.fill,
        source_qualifier=req.source_qualifier,
        section_qualifier=req.section_qualifier,
        report_title=req.report_title,
    )
    return mb02, source_local_ref, resolved_ref, mb02_query


def execute_program(
    program: ScopeNormalizedProgram,
    initial_ws: ProjectedWorkspace,
    *,
    case_id: str | None = None,
) -> ProgramExecutionResult:
    ok, reason = validate_program_structure(program)
    if not ok:
        return ProgramExecutionResult(
            case_id=case_id,
            structural_valid=False,
            structural_reason=reason,
            task_trace=[],
            program_terminal={
                "status": "invalid",
                "reason": reason,
                "authority": "DETERMINISTIC_SCHEMA_DOMAIN",
            },
            gold_used_as_runtime_decision_input=False,
            frontier_calls=0,
        )

    bindings = LocalBindingTable()
    ws = initial_ws.model_copy(deep=True)
    trace: list[TaskTraceRecord] = []
    effects_only_post_ok = True
    adapters_from_table = True

    for task in program.tasks:
        before = workspace_summary(ws)
        try:
            mb02_req, src_ref, resolved, mb02_q = to_mb02_request(
                task.request, bindings, ws
            )
        except ValueError as exc:
            return ProgramExecutionResult(
                case_id=case_id,
                structural_valid=False,
                structural_reason=str(exc),
                task_trace=trace,
                program_terminal={
                    "status": "invalid",
                    "reason": str(exc),
                    "authority": "DETERMINISTIC_SCHEMA_DOMAIN",
                },
                gold_used_as_runtime_decision_input=False,
                frontier_calls=0,
                all_task_effects_post_ok_only=effects_only_post_ok,
                all_local_ref_adapters_resolved_from_binding_table=adapters_from_table,
            )

        if src_ref is not None and resolved is None:
            adapters_from_table = False

        decision = adjudicate(mb02_req, ws)
        env = decision.public_envelope.model_dump()

        if decision.authority != "OK":
            # Fail-fast: no effect, no binds, later tasks not run
            trace.append(
                TaskTraceRecord(
                    task_id=task.task_id,
                    workspace_before=before,
                    scope_request=task.request.model_dump(),
                    source_local_ref=src_ref,
                    resolved_projected_ref=resolved,
                    mb02_adjudication_query=mb02_q,
                    mb02_authority=decision.authority,
                    public_envelope=env,
                    effect_applied=None,
                    binds_produced={},
                    workspace_after=before,  # unchanged
                    adjudicated=True,
                )
            )
            return ProgramExecutionResult(
                case_id=case_id,
                structural_valid=True,
                structural_reason=None,
                task_trace=trace,
                program_terminal={
                    "status": env.get("status"),
                    "reason": env.get("reason"),
                    "detail": env.get("detail"),
                    "authority": decision.authority,
                    "subtype": decision.subtype,
                    "failed_task_id": task.task_id,
                },
                gold_used_as_runtime_decision_input=False,
                frontier_calls=0,
                all_task_effects_post_ok_only=effects_only_post_ok,
                all_local_ref_adapters_resolved_from_binding_table=adapters_from_table,
            )

        # OK → apply effect then publish binds for CREATE_TRACK producers
        new_ws, _, effect_label = apply_effect(
            task.request, ws, bindings, resolved_track_ref=resolved
        )
        binds_produced: dict[str, int] = {}
        if task.request.requested_operation == "CREATE_TRACK" and task.produces_binds:
            # projected ref is the new last track
            new_ref = max(t.ref for t in new_ws.tracks)
            binds_produced = publish_binds_after_create_track(
                dict(task.produces_binds), new_ref, bindings
            )
            effect_label = f"{effect_label}; binds={binds_produced}"

        ws = new_ws
        after = workspace_summary(ws)
        trace.append(
            TaskTraceRecord(
                task_id=task.task_id,
                workspace_before=before,
                scope_request=task.request.model_dump(),
                source_local_ref=src_ref,
                resolved_projected_ref=resolved,
                mb02_adjudication_query=mb02_q,
                mb02_authority="OK",
                public_envelope=env,
                effect_applied=effect_label,
                binds_produced=binds_produced,
                workspace_after=after,
                adjudicated=True,
            )
        )

    return ProgramExecutionResult(
        case_id=case_id,
        structural_valid=True,
        structural_reason=None,
        task_trace=trace,
        program_terminal={"status": "ok", "reason": None, "authority": "OK"},
        gold_used_as_runtime_decision_input=False,
        frontier_calls=0,
        all_task_effects_post_ok_only=effects_only_post_ok,
        all_local_ref_adapters_resolved_from_binding_table=adapters_from_table,
    )


def parse_program_from_witness(normalized_program: dict[str, Any]) -> ScopeNormalizedProgram:
    """Instantiate program from design witness; strip non-contract keys on tasks."""
    tasks = []
    for raw in normalized_program.get("tasks") or []:
        tasks.append(
            ScopeNormalizedTask(
                task_id=raw["task_id"],
                depends_on=list(raw.get("depends_on") or []),
                produces_binds=dict(raw.get("produces_binds") or {}),
                request=ScopeNormalizedRequest.model_validate(raw["request"]),
            )
        )
    return ScopeNormalizedProgram(
        version=normalized_program.get("version"),
        tasks=tasks,
    )

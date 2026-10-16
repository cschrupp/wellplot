"""Q3 semantic equivalence for the frozen six-case surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nlp_gate_modernbert.mb02.contracts import ProjectedWorkspace
from nlp_gate_modernbert.mb02.resolve import match_curves, match_tracks
from nlp_gate_modernbert.nl_program_eval.atoms import evaluate_coverage
from nlp_gate_modernbert.nl_program_eval.cases import CaseRecord
from nlp_gate_modernbert.nl_program_eval.freeze import FrozenCandidate, require_frozen
from nlp_gate_modernbert.scope_runtime.contracts import (
    ProgramExecutionResult,
    ScopeNormalizedProgram,
    ScopeNormalizedTask,
)
from nlp_gate_modernbert.scope_runtime.execute import execute_program


FAILURE_LABELS = (
    "MISSING_TASK",
    "EXTRA_UNSUPPORTED_TASK",
    "WRONG_OPERATION",
    "WRONG_OPERAND",
    "WRONG_ORDER",
    "WRONG_DEPENDENCY",
    "WRONG_BINDING",
    "SEMANTIC_OVERREACH",
    "SEMANTIC_UNDERSPECIFICATION",
    "RUNTIME_TERMINAL_MISMATCH",
    "COMPARATOR_SCOPE_UNSUPPORTED",
)


@dataclass
class CompareResult:
    semantically_equivalent: bool
    failure_labels: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    coverage: dict[str, bool] = field(default_factory=dict)
    observed_out_of_scope: list[str] = field(default_factory=list)
    alignment: list[dict[str, Any]] = field(default_factory=list)
    benign_redundant_task_ids: list[str] = field(default_factory=list)
    candidate_terminal: dict[str, Any] = field(default_factory=dict)
    oracle_terminal: dict[str, Any] = field(default_factory=dict)


def _terminal_ok(term: dict[str, Any]) -> bool:
    return term.get("authority") == "OK" and term.get("status") == "ok"


def _terminals_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a.get("authority") == b.get("authority")
        and a.get("status") == b.get("status")
        and (a.get("reason") or None) == (b.get("reason") or None)
    )


def _resolve_text_entity(ws: ProjectedWorkspace, kind: str | None, text: str | None) -> str | None:
    if not text:
        return None
    if kind == "track":
        m = match_tracks(ws, text)
        if m.candidate_count == 1:
            return f"track:{m.candidate_ids[0]}"
        return f"track_ambig:{text}:{m.candidate_count}"
    # curve / fill / deictic → curve matcher for six-case surface
    m = match_curves(ws, text)
    if m.candidate_count == 1:
        return f"curve:{m.candidate_ids[0]}"
    return f"curve_ambig:{text}:{m.candidate_count}"


def _scalar_fingerprint(req) -> tuple:
    sb = req.scale_bounds
    fill = req.fill
    return (
        req.requested_operation,
        sb.kind if sb else None,
        sb.minimum if sb else None,
        sb.maximum if sb else None,
        tuple(req.scale_direction_claims or []),
        req.track_title,
        req.track_width_mm,
        req.report_title,
        fill.mode if fill else None,
        fill.baseline_value if fill else None,
        fill.primary_query if fill else None,
        (fill.predicate.kind if fill and fill.predicate else None),
        (fill.predicate.value if fill and fill.predicate else None),
        (fill.predicate.secondary_query if fill and fill.predicate else None),
    )


def _task_semantic_key(
    task: ScopeNormalizedTask,
    ws_before: ProjectedWorkspace | None,
    bind_role: dict[str, str],
) -> tuple:
    """Alignment key: op + resolved entities + scalars + bind roles (α-safe)."""
    req = task.request
    ents: list[str] = []
    for q, role in (
        (req.query, "query"),
        (req.secondary_query, "secondary"),
        (req.target, "target"),
    ):
        if q is None:
            continue
        if q.local_ref:
            ents.append(f"{role}:bind:{bind_role.get(q.local_ref, q.local_ref)}")
        elif q.text and ws_before is not None:
            ents.append(f"{role}:{_resolve_text_entity(ws_before, q.kind, q.text)}")
        elif q.text:
            ents.append(f"{role}:text:{q.text.strip().lower()}")
    produced = tuple(sorted(bind_role.get(b, b) for b in task.produces_binds))
    return (_scalar_fingerprint(req), tuple(ents), produced)


def _ws_from_summary(summary: dict[str, Any], template: ProjectedWorkspace) -> ProjectedWorkspace:
    """Rebuild a ProjectedWorkspace snapshot from execution summary for resolution."""
    from nlp_gate_modernbert.mb02.contracts import CurveFact, FillFact, TrackFact

    tracks = [
        TrackFact(ref=t["ref"], id=t.get("id") or f"t{t['ref']}", title=t.get("title"), curves=[])
        for t in summary.get("tracks") or []
    ]
    curves = []
    # Prefer live template curves updated with summary facts for alias resolution
    by_id = {(c.handle or c.id): c for c in template.curves}
    for c in summary.get("curves") or []:
        cid = c["id"]
        base = by_id.get(cid)
        if base is not None:
            curves.append(
                base.model_copy(
                    update={
                        "track_ref": c.get("track_ref"),
                        "scale_kind": c.get("scale_kind"),
                        "scale_min": c.get("scale_min"),
                        "scale_max": c.get("scale_max"),
                        "scale_reverse": c.get("scale_reverse"),
                    }
                )
            )
        else:
            curves.append(
                CurveFact(
                    id=cid,
                    channel=c.get("channel"),
                    handle=cid,
                    track_ref=c.get("track_ref"),
                    scale_kind=c.get("scale_kind"),
                    scale_min=c.get("scale_min"),
                    scale_max=c.get("scale_max"),
                    scale_reverse=c.get("scale_reverse"),
                    aliases=[],
                )
            )
    # Keep unplaced catalog curves from template for alias resolution
    present = {c.handle or c.id for c in curves} | {c.channel for c in curves if c.channel}
    for c in template.curves:
        key = c.handle or c.id
        if key not in present and (c.channel not in present if c.channel else True):
            curves.append(c)
    fills = [
        FillFact(ref=str(f["ref"]), curve=f.get("curve"), mode=f.get("mode"))
        for f in summary.get("fills") or []
    ]
    return template.model_copy(update={"tracks": tracks, "curves": curves, "fills": fills})


def _bind_role_map(program: ScopeNormalizedProgram) -> dict[str, str]:
    """Map local bind name → stable role by producer task index order."""
    roles: dict[str, str] = {}
    n = 0
    for t in program.tasks:
        for b, kind in t.produces_binds.items():
            roles[b] = f"{kind}#{n}"
            n += 1
    return roles


def _pre_task_workspaces(
    result: ProgramExecutionResult,
    initial: ProjectedWorkspace,
) -> list[ProjectedWorkspace]:
    out: list[ProjectedWorkspace] = []
    for i, rec in enumerate(result.task_trace):
        if i == 0:
            out.append(initial)
        else:
            prev = result.task_trace[i - 1]
            out.append(_ws_from_summary(prev["workspace_after"] if isinstance(prev, dict) else prev.workspace_after, initial))
    return out


def _trace_rec(rec) -> dict[str, Any]:
    return rec if isinstance(rec, dict) else rec.model_dump()


def _effect_already_true(task: ScopeNormalizedTask, ws: ProjectedWorkspace) -> bool:
    """Predicate: semantic effect already holds on pre-task workspace."""
    req = task.request
    op = req.requested_operation
    if op == "CONFIGURE_CURVE_DISPLAY" and req.query and req.query.text and req.scale_bounds:
        m = match_curves(ws, req.query.text)
        if m.candidate_count != 1:
            return False
        cid = m.candidate_ids[0]
        for c in ws.curves:
            if (c.handle or c.id) == cid or c.id == cid:
                sb = req.scale_bounds
                if c.scale_min == sb.minimum and c.scale_max == sb.maximum:
                    if sb.kind is None or c.scale_kind == sb.kind or (
                        sb.kind == "linear" and c.scale_kind in (None, "linear")
                    ):
                        want_rev = "decreasing" in (req.scale_direction_claims or [])
                        have_rev = c.scale_reverse is True
                        if want_rev != have_rev and want_rev:
                            return False
                        if not want_rev and have_rev:
                            return False
                        return True
        return False
    if op == "DEFINE_FILL":
        return False
    if op == "CREATE_TRACK":
        return False
    if op == "PLACE_CURVE":
        # Placing onto a newly bound track is never "already true"
        if req.target and req.target.local_ref:
            return False
        if not req.query or not req.query.text:
            return False
        m = match_curves(ws, req.query.text)
        if m.candidate_count != 1:
            return False
        cid = m.candidate_ids[0]
        target_ref = None
        if req.target and req.target.text:
            tm = match_tracks(ws, req.target.text)
            if tm.candidate_count == 1:
                target_ref = int(tm.candidate_ids[0])
        for c in ws.curves:
            if (c.handle or c.id) == cid or c.id == cid:
                if target_ref is None:
                    return False
                return c.track_ref == target_ref
        return False
    return False


def _program_without_task(program: ScopeNormalizedProgram, task_id: str) -> ScopeNormalizedProgram:
    tasks = []
    for t in program.tasks:
        if t.task_id == task_id:
            continue
        deps = [d for d in t.depends_on if d != task_id]
        tasks.append(
            ScopeNormalizedTask(
                task_id=t.task_id,
                request=t.request,
                depends_on=deps,
                produces_binds=dict(t.produces_binds),
            )
        )
    return ScopeNormalizedProgram(version=program.version, tasks=tasks)


def _introduces_new_utterance_semantics(
    case: CaseRecord,
    task: ScopeNormalizedTask,
    program: ScopeNormalizedProgram,
    initial: ProjectedWorkspace,
) -> bool:
    """If removing this task would drop a required atom, it is not benign."""
    reduced = _program_without_task(program, task.task_id)
    reduced_result = execute_program(reduced, initial.model_copy(deep=True), case_id=case.case_id)
    _, missing = evaluate_coverage(case.case_id, case.required_atom_ids, reduced, reduced_result)
    return len(missing) > 0


def _find_benign_redundant(
    case: CaseRecord,
    program: ScopeNormalizedProgram,
    result: ProgramExecutionResult,
    initial: ProjectedWorkspace,
) -> list[str]:
    """Apply frozen six-predicate BENIGN_REDUNDANT_TASK test."""
    if not _terminal_ok(result.program_terminal):
        return []
    pre_ws = _pre_task_workspaces(result, initial)
    benign: list[str] = []
    for i, task in enumerate(program.tasks):
        # individually supported: appeared in OK trace
        if i >= len(result.task_trace):
            continue
        rec = _trace_rec(result.task_trace[i])
        if rec.get("mb02_authority") != "OK":
            continue
        ws = pre_ws[i] if i < len(pre_ws) else initial
        # Harness requires a proven duplicate or already-true effect at this point;
        # the duplicate clause is mandatory so required first occurrences are not dropped.
        if not _duplicate_of_earlier_identical(program, i):
            continue
        if not _effect_already_true(task, ws) and not _duplicate_of_earlier_identical(program, i):
            continue
        if task.produces_binds:
            continue  # must not create/remove/change needed bind
        if _introduces_new_utterance_semantics(case, task, program, initial):
            continue
        reduced = _program_without_task(program, task.task_id)
        reduced_result = execute_program(reduced, initial.model_copy(deep=True), case_id=case.case_id)
        if not _terminal_ok(reduced_result.program_terminal):
            continue
        # After duplicate apply, effect is already true because earlier twin applied it
        if not _effect_already_true(task, ws) and i > 0:
            # still OK for pure duplicates: earlier twin made it true
            pass
        benign.append(task.task_id)
    return benign


def _duplicate_of_earlier_identical(program: ScopeNormalizedProgram, index: int) -> bool:
    cur = program.tasks[index]
    cur_fp = _scalar_fingerprint(cur.request)
    cur_q = None
    if cur.request.query:
        cur_q = cur.request.query.text or cur.request.query.local_ref
    for j in range(index):
        prev = program.tasks[j]
        if _scalar_fingerprint(prev.request) != cur_fp:
            continue
        pq = None
        if prev.request.query:
            pq = prev.request.query.text or prev.request.query.local_ref
        if pq == cur_q and cur.request.requested_operation == prev.request.requested_operation:
            return True
    return False


def _oracle_dep_constraints(oracle: ScopeNormalizedProgram) -> set[tuple[int, int]]:
    """Pairs (earlier_idx, later_idx) required by oracle depends_on edges."""
    index = {t.task_id: i for i, t in enumerate(oracle.tasks)}
    out: set[tuple[int, int]] = set()
    for i, t in enumerate(oracle.tasks):
        for d in t.depends_on:
            if d in index:
                out.add((index[d], i))
    return out


def _classify_mismatch(ct, ot, cand_roles, ora_roles, cws, ows) -> str:
    if ct.request.requested_operation != ot.request.requested_operation:
        return "WRONG_OPERATION"
    if _binding_mismatch(ct, ot, cand_roles, ora_roles):
        return "WRONG_BINDING"
    if _scalar_fingerprint(ct.request) != _scalar_fingerprint(ot.request):
        return "WRONG_OPERAND"
    ck = _task_semantic_key(ct, cws, cand_roles)
    ok = _task_semantic_key(ot, ows, ora_roles)
    if ck != ok:
        return "WRONG_OPERAND"
    return "WRONG_OPERAND"


def _align_spines(
    cand: ScopeNormalizedProgram,
    oracle: ScopeNormalizedProgram,
    cand_result: ProgramExecutionResult,
    oracle_result: ProgramExecutionResult,
    initial: ProjectedWorkspace,
    skip_cand_ids: set[str],
) -> tuple[list[tuple[int, int]], list[str], list[str], list[str]]:
    """Align non-benign candidate tasks to oracle tasks by semantic key.

    Preserves oracle dependency partial order and candidate array causality, but does
    NOT treat independent oracle serialization order as user-required order.
    """
    cand_roles = _bind_role_map(cand)
    ora_roles = _bind_role_map(oracle)
    cand_pre = _pre_task_workspaces(cand_result, initial)
    ora_pre = _pre_task_workspaces(oracle_result, initial)

    cand_idxs = [i for i, t in enumerate(cand.tasks) if t.task_id not in skip_cand_ids]
    ora_idxs = list(range(len(oracle.tasks)))

    def key_at(cidx: int, oidx: int) -> tuple:
        ct = cand.tasks[cidx]
        ot = oracle.tasks[oidx]
        cws = cand_pre[cidx] if cidx < len(cand_pre) else initial
        ows = ora_pre[oidx] if oidx < len(ora_pre) else initial
        return (
            _task_semantic_key(ct, cws, cand_roles),
            _task_semantic_key(ot, ows, ora_roles),
            ct,
            ot,
            cws,
            ows,
        )

    pairs: list[tuple[int, int]] = []
    used_cand: set[int] = set()
    failures: list[str] = []
    near_miss_labels: list[str] = []

    for oi in ora_idxs:
        ot = oracle.tasks[oi]
        matches: list[int] = []
        for cidx in cand_idxs:
            if cidx in used_cand:
                continue
            ck, ok, ct, _, cws, ows = key_at(cidx, oi)
            if ck == ok:
                matches.append(cidx)
        if matches:
            chosen = min(matches)
            used_cand.add(chosen)
            pairs.append((chosen, oi))
            continue
        # No exact match — record best mismatch label from unused candidates with same op
        same_op = [
            cidx
            for cidx in cand_idxs
            if cidx not in used_cand
            and cand.tasks[cidx].request.requested_operation == ot.request.requested_operation
        ]
        if same_op:
            cidx = same_op[0]
            _, _, ct, _, cws, ows = key_at(cidx, oi)
            near_miss_labels.append(
                _classify_mismatch(ct, ot, cand_roles, ora_roles, cws, ows)
            )
        else:
            unused = [cidx for cidx in cand_idxs if cidx not in used_cand]
            if unused:
                cidx = unused[0]
                _, _, ct, _, cws, ows = key_at(cidx, oi)
                near_miss_labels.append(
                    _classify_mismatch(ct, ot, cand_roles, ora_roles, cws, ows)
                )

    matched_ora = {p[1] for p in pairs}
    matched_cand = {p[0] for p in pairs}
    unmatched_ora = [oracle.tasks[i].task_id for i in ora_idxs if i not in matched_ora]
    unmatched_cand = [cand.tasks[i].task_id for i in cand_idxs if i not in matched_cand]

    if unmatched_ora:
        if near_miss_labels:
            failures.extend(near_miss_labels)
        else:
            failures.append("MISSING_TASK")
    if unmatched_cand and not unmatched_ora:
        failures.append("SEMANTIC_OVERREACH")
    elif unmatched_cand and unmatched_ora and not failures:
        failures.append("MISSING_TASK")

    return pairs, failures, unmatched_ora, unmatched_cand


def _binding_mismatch(ct, ot, cand_roles, ora_roles) -> bool:
    c_refs = []
    o_refs = []
    for req, bag in ((ct.request, c_refs), (ot.request, o_refs)):
        for q in (req.query, req.secondary_query, req.target):
            if q and q.local_ref:
                bag.append(q.local_ref)
    # produced binds
    if bool(ct.produces_binds) != bool(ot.produces_binds):
        return True
    # consumer uses text track vs bind
    ct_uses_bind = any(
        q and q.local_ref for q in (ct.request.query, ct.request.secondary_query, ct.request.target)
    )
    ot_uses_bind = any(
        q and q.local_ref for q in (ot.request.query, ot.request.secondary_query, ot.request.target)
    )
    if ct_uses_bind != ot_uses_bind:
        return True
    return False


def _bind_producers(program: ScopeNormalizedProgram) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in program.tasks:
        for b in t.produces_binds:
            out[b] = t.task_id
    return out


def _ancestry_ids(program: ScopeNormalizedProgram, task_id: str) -> set[str]:
    by_id = {t.task_id: t for t in program.tasks}
    seen: set[str] = set()
    stack = list(by_id[task_id].depends_on)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(by_id[cur].depends_on)
    return seen


def _component_id(task: ScopeNormalizedTask) -> str:
    req = task.request
    op = req.requested_operation
    if op == "CREATE_TRACK":
        return "create"
    q = (req.query.text or "").strip().lower() if req.query and req.query.text else ""
    if op == "PLACE_CURVE":
        return f"place:{q}"
    if op == "CONFIGURE_CURVE_DISPLAY":
        return f"cfg:{q}"
    if op == "DEFINE_FILL":
        return "fill"
    return f"op:{op}"


# Directed forbidden depends_on edges (consumer_component, dependency_component).
# Omitting oracle linearization is fine; adding reverse/independent edges is not.
_FORBIDDEN_DEPENDENCY_EDGES: dict[str, frozenset[tuple[str, str]]] = {
    # 0096: GR/RT fork may be serialized either way; no directed edge is forbidden beyond bind ancestry.
    "D5GAP-0096": frozenset(),
    "D5GAP-0101": frozenset(
        {
            # place must not depend on configure (configure may depend on place)
            ("place:cali", "cfg:cali"),
            ("place:caliper", "cfg:cali"),
            ("place:cali", "cfg:caliper"),
            ("place:caliper", "cfg:caliper"),
        }
    ),
    "SEED-cm-9643c020e2e02463": frozenset(),
}


def _check_bind_dependencies(
    case: CaseRecord,
    cand: ScopeNormalizedProgram,
    oracle: ScopeNormalizedProgram,
    pairs: list[tuple[int, int]],
) -> bool:
    """Bind ancestry must reach producer; candidate must not order case-independent components."""
    cand_prod = _bind_producers(cand)
    for cidx, _oidx in pairs:
        ct = cand.tasks[cidx]
        for q in (ct.request.query, ct.request.secondary_query, ct.request.target):
            if q is None or not q.local_ref:
                continue
            prod_id = cand_prod.get(q.local_ref)
            if prod_id is None:
                return False
            if prod_id != ct.task_id and prod_id not in _ancestry_ids(cand, ct.task_id):
                return False

    forbidden = _FORBIDDEN_DEPENDENCY_EDGES.get(case.case_id, frozenset())
    if not forbidden:
        return True
    id_to_comp = {t.task_id: _component_id(t) for t in cand.tasks}
    for t in cand.tasks:
        src = id_to_comp[t.task_id]
        for d in t.depends_on:
            dst = id_to_comp.get(d)
            if dst is None:
                continue
            if (src, dst) in forbidden:
                return False
    return True


def _check_ordering_atoms(
    case: CaseRecord,
    cand: ScopeNormalizedProgram,
    pairs: list[tuple[int, int]],
) -> bool:
    if not case.ordering_atom_ids:
        return True
    # Reuse atom checkers for ordering atoms
    from nlp_gate_modernbert.nl_program_eval.atoms import ATOM_CHECKERS

    for atom_id in case.ordering_atom_ids:
        checker = ATOM_CHECKERS.get((case.case_id, atom_id))
        if checker is None:
            raise RuntimeError(f"COMPARATOR_SCOPE_UNSUPPORTED:ordering:{atom_id}")
        # ordering checkers only need program
        class _Empty:
            task_trace = []
            program_terminal = {}

        if not checker(cand, _Empty()):  # type: ignore[arg-type]
            return False
    return True


def compare_programs(
    frozen: FrozenCandidate,
    oracle_program: ScopeNormalizedProgram,
    initial_ws: ProjectedWorkspace,
    case: CaseRecord,
) -> CompareResult:
    require_frozen(frozen)
    cand_program = frozen.to_runtime_program()
    initial = initial_ws.model_copy(deep=True)

    cand_result = execute_program(cand_program, initial.model_copy(deep=True), case_id=case.case_id)
    ora_result = execute_program(oracle_program, initial.model_copy(deep=True), case_id=case.case_id)

    out = CompareResult(
        semantically_equivalent=False,
        candidate_terminal=dict(cand_result.program_terminal),
        oracle_terminal=dict(ora_result.program_terminal),
        observed_out_of_scope=list(case.observed_out_of_scope),
    )

    # Stage 1: runtime gate
    if not _terminals_match(cand_result.program_terminal, ora_result.program_terminal):
        out.failure_labels.append("RUNTIME_TERMINAL_MISMATCH")
        return out
    if not _terminal_ok(cand_result.program_terminal):
        out.failure_labels.append("RUNTIME_TERMINAL_MISMATCH")
        return out

    # Coverage
    coverage, missing_atoms = evaluate_coverage(
        case.case_id, case.required_atom_ids, cand_program, cand_result
    )
    out.coverage = coverage
    if missing_atoms:
        # Prefer MISSING_TASK when an operation-level atom is gone; else underspec
        out.failure_labels.append("MISSING_TASK")
        if any("RANGE" in a or "SCALE" in a or "BASELINE" in a or "WIDTH" in a or "TITLE" in a for a in missing_atoms):
            # may also be wrong operand — refined below if alignment finds it
            pass
        out.diagnostics.append(f"missing_atoms:{missing_atoms}")

    # Benign redundancy
    benign_ids = _find_benign_redundant(case, cand_program, cand_result, initial)
    out.benign_redundant_task_ids = benign_ids
    skip = set(benign_ids)
    pairs, align_failures, unmatched_ora, unmatched_cand = _align_spines(
        cand_program, oracle_program, cand_result, ora_result, initial, skip
    )
    out.alignment = [
        {
            "candidate_task_id": cand_program.tasks[c].task_id,
            "oracle_task_id": oracle_program.tasks[o].task_id,
        }
        for c, o in pairs
    ]

    # Refine labels from alignment
    for lab in align_failures:
        if lab not in out.failure_labels:
            out.failure_labels.append(lab)

    if unmatched_ora and "MISSING_TASK" not in out.failure_labels and "WRONG_OPERAND" not in out.failure_labels:
        out.failure_labels.append("MISSING_TASK")
    if unmatched_cand and "SEMANTIC_OVERREACH" not in out.failure_labels and not align_failures:
        out.failure_labels.append("SEMANTIC_OVERREACH")

    # Bind ancestry + no depends_on edges between case-independent components
    if len(pairs) == len(oracle_program.tasks):
        if not _check_bind_dependencies(case, cand_program, oracle_program, pairs):
            if "WRONG_DEPENDENCY" not in out.failure_labels:
                out.failure_labels.append("WRONG_DEPENDENCY")

    # Ordering atoms
    if not _check_ordering_atoms(case, cand_program, pairs):
        if "WRONG_ORDER" not in out.failure_labels:
            out.failure_labels.append("WRONG_ORDER")

    # If coverage missing but alignment found wrong operand, prefer WRONG_OPERAND
    if missing_atoms and any(l in out.failure_labels for l in ("WRONG_OPERAND", "WRONG_BINDING", "WRONG_OPERATION")):
        out.failure_labels = [l for l in out.failure_labels if l != "MISSING_TASK"]

    # Underspecification: coverage fail with no structural mismatch label
    if missing_atoms and not out.failure_labels:
        out.failure_labels.append("SEMANTIC_UNDERSPECIFICATION")
    if missing_atoms and out.failure_labels == ["MISSING_TASK"]:
        # keep MISSING_TASK; also allow UNDERSPEC as secondary when only soft atoms missing
        pass

    if benign_ids and "BENIGN_REDUNDANT_TASK" not in out.diagnostics:
        out.diagnostics.append("BENIGN_REDUNDANT_TASK")

    if not out.failure_labels:
        out.semantically_equivalent = True
    else:
        # dedupe preserve order
        seen: set[str] = set()
        deduped = []
        for l in out.failure_labels:
            if l not in seen:
                seen.add(l)
                deduped.append(l)
        out.failure_labels = deduped

    return out

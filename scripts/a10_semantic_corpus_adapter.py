"""Read-only adapter from frozen historical planner corpora to current wire plans.

This module indexes existing gold data and scores production planner output. It
does not parse requests, construct plans, resolve sources, or lower semantics.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wellplot.agent.code_mode.planner import _PlannerWirePlan


@dataclass(frozen=True)
class CorpusSpec:
    """Immutable provenance for one historical corpus fixture."""

    fixture: str
    checkpoint: str
    blob_sha256: str
    raw_sha256: str


CORPORA = (
    CorpusSpec(
        "tests/fixtures/typed_worker/cm57p5_fresh_holdout.json",
        "aea88a0611804b88bf1694448283cd5818977c55",
        "9a28e601617aae0151d0d8e9d93e08dd7f7a2902",
        "29e85998481ce9bcc6eab9ecb7959d470cefbf3a84e5273309c6004aacae334d",
    ),
    CorpusSpec(
        "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json",
        "f952c64f735b6c3bc7519677c2d36ca80e980609",
        "aae31fb572a95e76b1633a462df67baa9aa56350",
        "4aebee0d2734cb272c6ae002aec277e58427dd5dce44e38e5fdf1a14a4dccd12",
    ),
    CorpusSpec(
        "tests/fixtures/typed_worker/cm57p10_final_promotion_cases.json",
        "fd3448487cbd3418bbcb33a89ce5e5b809198e42",
        "2fc48cadeb56f1dd4d4d08634b1d3fb4b0559dfc",
        "43d06f5808340beda1af178e08f3dfd14bd241cad5c84064d50a9dca9216582f",
    ),
    CorpusSpec(
        "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
        "038a68a4f582215b11648e2c659d130adba948e8",
        "c2bc13649f87cb87f7fd51fc075752e4bd76d7b0",
        "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b",
    ),
)

P7_FIXTURE = "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json"
P7_RAW_SHA256 = "4aebee0d2734cb272c6ae002aec277e58427dd5dce44e38e5fdf1a14a4dccd12"
P8_FIXTURE = "tests/fixtures/typed_worker/cm57p8_prompt_factor_cases.json"
P8_RAW_SHA256 = "32ed1e0de1ca8e6ec7c771b50a7ab8ffcc7675503c7951ccd8b6bf401318bb5a"
HOLDOUT_FIXTURE = "workspace/evaluations/a10-sem-01-20261110/benchmark.json"
P_CURRENT_REVISION = "1b9ead3c4a"
C1_REVISION = "3a2cfbe3e9"
P_CURRENT_SHA = "1b9ead3c4acdf70dea0bce6475150f6219421988"
C1_SHA = "3a2cfbe3e9d61acdde2a072828e2256f59abcc4b"
PLANNER_PATH = "src/wellplot/agent/code_mode/planner.py"
PRODUCTION_ROOT = "src/wellplot/"
P8_ARMS = ("P-current", "C1")
A10_BENCHMARK_ID = "A10-SEM-01"
A10_BENCHMARK_SHA256 = "595839779e9ca59d9ce8ff20cbbdaf006ad41138b4510acc0ea26733e080067a"
A10_SOURCE_INVENTORY_SHA256 = "21f11462696af7a9f1d9b18d625a6a311794912b9ef10a70106f0267e83c19b0"
A10_EXPECTATION_SCORING_SCOPE = {
    "SAFE_CORRECT": "PARTLY_SCORABLE",
    "SAFE_CORRECT_GR": "PARTLY_SCORABLE",
    "SAFE_CORRECT_PHYSICAL_GR": "PARTLY_SCORABLE",
    "SAFE_REJECT_ABSENT": "PARTLY_SCORABLE",
    "SAFE_REJECT_ADDRESSABILITY_UNKNOWN": "PARTLY_SCORABLE",
    "SAFE_REJECT_AMBIGUOUS": "PARTLY_SCORABLE",
    "SAFE_REJECT_INCOMPLETE_INVENTORY": "PARTLY_SCORABLE",
    "SAFE_REJECT_NO_BEST_GUESS": "PARTLY_SCORABLE",
    "SAFE_REJECT_UNAUTHORIZED_AMBIGUOUS_CANDIDATES": "PARTLY_SCORABLE",
    "SAFE_REJECT_UNAUTHORIZED_MAPPING": "PARTLY_SCORABLE",
    "UNSUPPORTED_FAIL_CLOSED": "PARTLY_SCORABLE",
    "UNSUPPORTED_operation_if_no_canonical_contract": "PARTLY_SCORABLE",
    "ADD_TRACK": "PARTLY_SCORABLE",
    "ADD_TRACK_order_preserved": "PARTLY_SCORABLE",
    "ADD_TRACK_plus_explicit_scale": "PARTLY_SCORABLE",
    "UPDATE_CURVE_SCALE": "PARTLY_SCORABLE",
    "ordered_add_track_operations": "PARTLY_SCORABLE",
    "semantic_GR_plus_physical_RHOB": "PARTLY_SCORABLE",
    "two_add_track_operations_correct_kinds": "PARTLY_SCORABLE",
    "two_add_track_operations_exact_channels": "PARTLY_SCORABLE",
}


def verify_planner_revision_closure(repo_root: Path) -> dict[str, Any]:
    """Prove the two frozen revisions differ only in planner runtime code."""
    root = repo_root.resolve()
    changed = subprocess.run(
        ["git", "diff", "--name-only", P_CURRENT_REVISION, C1_REVISION, "--", PRODUCTION_ROOT],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if changed != [PLANNER_PATH]:
        raise CorpusIntegrityError(f"Planner production revision closure differs: {changed!r}")
    identities: dict[str, dict[str, str]] = {}
    for arm, revision in (("P-current", P_CURRENT_SHA), ("C1", C1_SHA)):
        blob = subprocess.run(
            ["git", "rev-parse", f"{revision}:{PLANNER_PATH}"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        source = subprocess.run(
            ["git", "show", f"{revision}:{PLANNER_PATH}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        identities[arm] = {
            "revision": subprocess.run(
                ["git", "rev-parse", revision],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "blob": blob,
            "sha256": _sha256(source),
        }
    return {"changed_production_paths": changed, "arms": identities}


def p8_pair_population(repo_root: Path) -> tuple[tuple[str, str], ...]:
    """Return the exact case/arm population, excluding all holdout cases."""
    canaries = load_corpus_index(repo_root).canary_cases
    pairs = tuple((case.case_id, arm) for case in canaries for arm in P8_ARMS)
    if len(canaries) != 12 or len(pairs) != 24:
        raise CorpusIntegrityError("P8 requires exactly 12 canaries and 24 case/arm pairs")
    if len({case_id for case_id, _ in pairs}) != 12:
        raise CorpusIntegrityError("P8 canary case identities are not unique")
    return pairs


class CorpusIntegrityError(ValueError):
    """Raised when immutable historical corpus custody does not match."""


@dataclass(frozen=True)
class A10BenchmarkCase:
    """One immutable request record from the accepted A10 benchmark."""

    case_id: str
    gold: str
    case_class: str
    source: str
    request: str
    structured_channel: str
    expected: str
    inventory_complete: bool = True


@dataclass(frozen=True)
class A10ScoreResult:
    """Bounded planner-only score with explicit unscorable dimensions."""

    disposition: str
    passed: bool
    findings: tuple[str, ...]
    scorable_dimensions: tuple[str, ...]
    unscorable_dimensions: tuple[str, ...]
    operation_count: int
    unresolved_count: int
    semantic_refs: tuple[str, ...]
    channel_tokens: tuple[str, ...]
    explicit_channel_tokens: tuple[str, ...] = ()
    channel_clues: tuple[str, ...] = ()
    object_kinds: tuple[str, ...] = ()
    verbs: tuple[str, ...] = ()
    scale_fields: tuple[str, ...] = ()
    scoring_scope: str = "PARTLY_SCORABLE"


@dataclass(frozen=True)
class AdaptedCase:
    """Historical request and gold semantics with immutable fixture identity."""

    source_fixture: str
    source_checkpoint: str
    source_blob_sha256: str
    case_id: str
    family: str
    request: str
    request_sha256: str
    expected_report_capabilities: tuple[str, ...]
    expected_sections: tuple[tuple[str, ...], ...]
    expected_unresolved_count: int
    residual_class: str | None = None
    protected_role: str | None = None


@dataclass(frozen=True)
class CorpusIndex:
    """Adapted historical cases and their deterministically joined canaries."""

    cases: tuple[AdaptedCase, ...]
    canary_cases: tuple[AdaptedCase, ...]


@dataclass(frozen=True)
class OperationObservation:
    """Current-IR operation fields observable without historical op gold."""

    owner: str
    scope_ref: str
    local_ref: str
    object_kind: str
    verb: str
    semantic_ref: str | None
    target_clue: str | None


@dataclass(frozen=True)
class ScoreResult:
    """Invariant comparison result and explicit unscorable dimensions."""

    disposition: str
    passed: bool
    findings: tuple[str, ...]
    operation_observations: tuple[OperationObservation, ...]
    operation_target_comparison: str
    source_identity_comparison: str
    first_divergence: str
    historical_divergence: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_a10_benchmark(repo_root: Path) -> tuple[A10BenchmarkCase, ...]:
    """Load and validate the exact 53-case A10 benchmark population."""
    root = repo_root.resolve()
    path = root / HOLDOUT_FIXTURE
    raw = path.read_bytes()
    if _sha256(raw) != A10_BENCHMARK_SHA256:
        raise CorpusIntegrityError("A10 benchmark bytes changed")
    payload = json.loads(raw)
    if payload.get("benchmark_id") != A10_BENCHMARK_ID:
        raise CorpusIntegrityError("A10 benchmark identity changed")
    rows = payload.get("cases")
    if not isinstance(rows, list) or len(rows) != 53:
        raise CorpusIntegrityError("A10 benchmark must contain exactly 53 cases")
    cases: list[A10BenchmarkCase] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CorpusIntegrityError("A10 benchmark case is not an object")
        required = {"id", "gold", "class", "source", "request", "structured_channel", "expected"}
        if not required <= row.keys():
            raise CorpusIntegrityError("A10 benchmark case is missing required fields")
        case_id = row["id"]
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise CorpusIntegrityError("A10 benchmark case IDs are not unique")
        seen.add(case_id)
        if row["gold"] not in {"P", "E"}:
            raise CorpusIntegrityError(f"invalid A10 gold label: {case_id}")
        if not all(isinstance(row[key], str) and row[key] for key in required - {"id"}):
            raise CorpusIntegrityError(f"invalid A10 benchmark fields: {case_id}")
        if row["expected"] not in A10_EXPECTATION_SCORING_SCOPE:
            raise CorpusIntegrityError(f"A10 expectation has no scoring disposition: {case_id}")
        inventory_complete = row.get("inventory_complete", True)
        if not isinstance(inventory_complete, bool):
            raise CorpusIntegrityError(f"invalid A10 inventory flag: {case_id}")
        cases.append(
            A10BenchmarkCase(
                case_id=case_id,
                gold=row["gold"],
                case_class=row["class"],
                source=row["source"],
                request=row["request"],
                structured_channel=row["structured_channel"],
                expected=row["expected"],
                inventory_complete=inventory_complete,
            )
        )
    if sum(case.gold == "P" for case in cases) != 35:
        raise CorpusIntegrityError("A10 benchmark production partition changed")
    if sum(case.gold == "E" for case in cases) != 18:
        raise CorpusIntegrityError("A10 benchmark exploratory partition changed")
    return tuple(cases)


def _plan_operations(plan: _PlannerWirePlan) -> tuple[dict[str, Any], ...]:
    """Project planner operations without introducing host-owned identities."""
    operations: list[dict[str, Any]] = []
    if plan.report_task is not None:
        operations.extend(item.model_dump(mode="json") for item in plan.report_task.operations)
    for task in plan.section_tasks:
        operations.extend(item.model_dump(mode="json") for item in task.operations)
    return tuple(operations)


def _a10_presentation_constraints(plan: _PlannerWirePlan) -> tuple[dict[str, Any], ...]:
    """Project the planner's request-local presentation ordering evidence."""
    constraints: list[dict[str, Any]] = []
    if plan.report_task is not None:
        constraints.extend(
            item.model_dump(mode="json") for item in plan.report_task.presentation_constraints
        )
    for task in plan.section_tasks:
        constraints.extend(item.model_dump(mode="json") for item in task.presentation_constraints)
    return tuple(constraints)


_A10_CHANNEL_NAMES = ("GR", "CGR", "GRD", "RHOB", "CBL", "VDL", "SP", "CALI", "TDEP")


def _a10_operation_channel_tokens(operation: dict[str, Any]) -> tuple[str, ...]:
    """Return exact channel evidence in the order present in one operation."""
    tokens: list[str] = []
    for value in operation.get("field_values", ()):
        if value.get("state") == "SET" and value.get("field") == "channel":
            candidate = value.get("value")
            if isinstance(candidate, str):
                tokens.append(candidate)
    clue = operation.get("target_clue")
    if isinstance(clue, str):
        tokens.extend(
            match.group(1).upper()
            for match in re.finditer(
                r"(?<![A-Za-z0-9_.-])(" + "|".join(_A10_CHANNEL_NAMES) + r")(?![A-Za-z0-9_.-])",
                clue,
                flags=re.IGNORECASE,
            )
        )
    return tuple(dict.fromkeys(tokens))


def _a10_channel_observations(
    operations: tuple[dict[str, Any], ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Project explicit channels separately from exact tokens in target clues."""
    explicit: list[str] = []
    clues: list[str] = []
    operation_tokens: list[tuple[str, ...]] = []
    for operation in operations:
        per_operation = _a10_operation_channel_tokens(operation)
        operation_tokens.append(per_operation)
        for value in operation.get("field_values", ()):  # host resolution is not performed here
            if value.get("state") == "SET" and value.get("field") == "channel":
                candidate = value.get("value")
                if isinstance(candidate, str):
                    explicit.append(candidate)
        clue = operation.get("target_clue")
        if isinstance(clue, str):
            for match in re.finditer(
                r"(?<![A-Za-z0-9_.-])(" + "|".join(_A10_CHANNEL_NAMES) + r")(?![A-Za-z0-9_.-])",
                clue,
                flags=re.IGNORECASE,
            ):
                clues.append(match.group(1).upper())
    return tuple(explicit), tuple(clues), tuple(operation_tokens)


def _a10_channel_tokens(operations: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    """Return exact channel tokens without treating CGR or GRD as GR."""
    return tuple(
        token for operation in operations for token in _a10_operation_channel_tokens(operation)
    )


def _a10_has_operation_channel(
    operations: tuple[dict[str, Any], ...],
    operation_tokens: tuple[tuple[str, ...], ...],
    *,
    verb: str | None = None,
    object_kind: str | None = None,
    channel: str,
) -> bool:
    """Require channel evidence and operation shape on the same operation."""
    return any(
        (verb is None or operation.get("verb") == verb)
        and (object_kind is None or operation.get("object_kind") == object_kind)
        and channel in tokens
        for operation, tokens in zip(operations, operation_tokens, strict=True)
    )


def _a10_expected_scale(request: str) -> dict[str, float | str] | None:
    """Extract the finite explicit linear scale used by the frozen scale cases."""
    match = re.search(r"linear\s+(-?\d+(?:\.\d+)?)\s*[–-]\s*(-?\d+(?:\.\d+)?)", request)
    if match is None:
        return None
    return {
        "scale_kind": "linear",
        "scale_minimum": float(match.group(1)),
        "scale_maximum": float(match.group(2)),
    }


def _a10_scale_groups(operations: tuple[dict[str, Any], ...]) -> dict[str, dict[str, object]]:
    """Group scale assignments by the operation-local target identity."""
    groups: dict[str, dict[str, object]] = {}
    for operation in operations:
        target = operation.get("target_clue") or operation.get("semantic_ref")
        if not isinstance(target, str):
            continue
        fields = groups.setdefault(target, {})
        for value in operation.get("field_values", ()):
            field = value.get("field")
            if value.get("state") == "SET" and field in {
                "scale_kind",
                "scale_minimum",
                "scale_maximum",
            }:
                fields[str(field)] = value.get("value")
    return groups


def _a10_has_expected_scale(
    case: A10BenchmarkCase,
    operations: tuple[dict[str, Any], ...],
) -> bool:
    """Require every explicit scale component present in the frozen request."""
    expected = _a10_expected_scale(case.request)
    if expected is None:
        return False
    return any(
        all(fields.get(field) == value for field, value in expected.items())
        for fields in _a10_scale_groups(operations).values()
    )


def score_a10_plan(case: A10BenchmarkCase, plan: _PlannerWirePlan | None) -> A10ScoreResult:
    """Score only frozen A10 planner dimensions; leave host dimensions unscorable."""
    if plan is None:
        return A10ScoreResult(
            disposition="PLANNER_TERMINAL_FAILURE",
            passed=False,
            findings=("planner_returned_no_wire_plan",),
            scorable_dimensions=("final_structural_validity",),
            unscorable_dimensions=("source_channel_grounding", "host_resolution"),
            operation_count=0,
            unresolved_count=0,
            semantic_refs=(),
            channel_tokens=(),
        )
    operations = _plan_operations(plan)
    unresolved_count = len(plan.unresolved_requirements) + len(plan.unresolved_semantics)
    semantic_refs = tuple(
        str(item["semantic_ref"])
        for item in operations
        if isinstance(item.get("semantic_ref"), str)
    )
    explicit_channel_tokens, channel_clues, operation_channel_tokens = _a10_channel_observations(
        operations
    )
    channel_tokens = tuple(token for tokens in operation_channel_tokens for token in tokens)
    object_kinds = tuple(str(operation.get("object_kind")) for operation in operations)
    verbs = tuple(str(operation.get("verb")) for operation in operations)
    scale_fields = tuple(
        sorted({field for fields in _a10_scale_groups(operations).values() for field in fields})
    )
    findings: list[str] = []
    expected = case.expected
    safe_rejection = expected.startswith("SAFE_REJECT") or expected == "UNSUPPORTED_FAIL_CLOSED"
    if safe_rejection:
        if unresolved_count == 0:
            findings.append("safe_rejection_not_declared")
        if operations:
            findings.append("safe_rejection_contains_executable_work")
    elif expected == "SAFE_CORRECT_GR":
        if "binding.gr-curve" not in semantic_refs:
            findings.append("gamma_ray_semantic_binding_missing")
    elif expected == "SAFE_CORRECT_PHYSICAL_GR":
        if "GR" not in explicit_channel_tokens and "GR" not in channel_clues:
            findings.append("physical_gr_channel_missing")
    elif expected == "SAFE_CORRECT":
        expected_channels = tuple(case.structured_channel.split(";"))
        if (
            not operations
            or unresolved_count
            or len(operations) != len(expected_channels)
            or tuple(tokens for tokens in operation_channel_tokens if tokens)
            != tuple((channel,) for channel in expected_channels)
        ):
            findings.append("explicit_physical_plan_incomplete")
    elif expected == "two_add_track_operations_exact_channels":
        if (
            len(operations) != 2
            or tuple(object_kinds) != ("track", "track")
            or operation_channel_tokens != (("GR",), ("RHOB",))
            or tuple(verbs) != ("CREATE", "CREATE")
        ):
            findings.append("multi_operation_channel_shape_mismatch")
    elif expected == "two_add_track_operations_correct_kinds":
        track_kinds = tuple(
            next(
                (
                    value.get("value")
                    for value in operation.get("field_values", ())
                    if value.get("field") == "kind" and value.get("state") == "SET"
                ),
                None,
            )
            for operation in operations
        )
        if (
            len(operations) != 2
            or tuple(object_kinds) != ("track", "track")
            or tuple(verbs) != ("CREATE", "CREATE")
            or operation_channel_tokens != (("CBL",), ("VDL",))
            or track_kinds != ("normal", "array")
        ):
            findings.append("multi_operation_kind_shape_mismatch")
    elif expected == "ordered_add_track_operations":
        if (
            len(operations) != 2
            or tuple(object_kinds) != ("track", "track")
            or tuple(verbs) != ("CREATE", "CREATE")
            or operation_channel_tokens != (("GR",), ("CGR",))
        ):
            findings.append("multi_operation_order_mismatch")
    elif expected == "semantic_GR_plus_physical_RHOB":
        if "binding.gr-curve" not in semantic_refs or "RHOB" not in channel_tokens:
            findings.append("mixed_semantic_physical_shape_mismatch")
    elif expected == "ADD_TRACK_plus_explicit_scale":
        if not _a10_has_operation_channel(
            operations,
            operation_channel_tokens,
            verb="CREATE",
            object_kind="track",
            channel="CBL",
        ) or not _a10_has_expected_scale(case, operations):
            findings.append("track_or_explicit_scale_missing")
    elif expected == "UPDATE_CURVE_SCALE":
        if not _a10_has_operation_channel(
            operations,
            operation_channel_tokens,
            verb="SET",
            object_kind="binding",
            channel="CBL",
        ) or not _a10_has_expected_scale(case, operations):
            findings.append("curve_scale_update_incomplete")
    elif expected == "ADD_TRACK":
        if not _a10_has_operation_channel(
            operations,
            operation_channel_tokens,
            verb="CREATE",
            object_kind="track",
            channel="GR",
        ):
            findings.append("track_operation_missing")
    elif expected == "ADD_TRACK_order_preserved":
        vdl_refs = {
            str(operation.get("local_ref"))
            for operation, tokens in zip(operations, operation_channel_tokens, strict=True)
            if operation.get("verb") == "CREATE"
            and operation.get("object_kind") == "track"
            and "VDL" in tokens
        }
        order_constraint = any(
            constraint.get("relation") == "after"
            and constraint.get("item_ref") in vdl_refs
            and "cbl" in str(constraint.get("anchor_ref", "")).casefold()
            for constraint in _a10_presentation_constraints(plan)
        )
        if (
            not _a10_has_operation_channel(
                operations,
                operation_channel_tokens,
                verb="CREATE",
                object_kind="track",
                channel="VDL",
            )
            or not order_constraint
        ):
            findings.append("ordered_track_operation_missing")
    elif expected == "UNSUPPORTED_operation_if_no_canonical_contract":
        if unresolved_count == 0:
            findings.append("unsupported_mutation_not_rejected")
        if operations:
            findings.append("unsupported_mutation_contains_executable_work")
    else:
        findings.append("unrecognized_a10_expectation")
    return A10ScoreResult(
        disposition="A10_PLANNER_PLAN" if not findings else "A10_PLANNER_MISMATCH",
        passed=not findings,
        findings=tuple(findings),
        scorable_dimensions=("final_structural_validity", "declared_intent_shape"),
        unscorable_dimensions=("source_channel_grounding", "host_resolution", "host_execution"),
        operation_count=len(operations),
        unresolved_count=unresolved_count,
        semantic_refs=semantic_refs,
        channel_tokens=channel_tokens,
        explicit_channel_tokens=explicit_channel_tokens,
        channel_clues=channel_clues,
        object_kinds=object_kinds,
        verbs=verbs,
        scale_fields=scale_fields,
        scoring_scope=A10_EXPECTATION_SCORING_SCOPE[expected],
    )


_FIRST_DIVERGENCE_ORDER = (
    ("transport", "PROVIDER_OR_STRUCTURED", "TRANSPORT"),
    ("structured_decode", "PROVIDER_OR_STRUCTURED", "STRUCTURED_DECODE"),
    ("provider_schema", "PROVIDER_OR_STRUCTURED", "PROVIDER_SCHEMA"),
    ("pydantic_validation", "PLANNER_STRUCTURAL", "PYDANTIC_VALIDATION"),
    ("planner_semantic", "SEMANTIC", "PLANNER_SEMANTIC"),
    ("host_resolution", "TARGET_GROUNDING", "HOST_RESOLUTION"),
    ("host_safety", "HOST_SAFETY", "HOST_SAFETY"),
)


def classify_first_divergence(boundaries: dict[str, str]) -> tuple[str, str]:
    """Return earliest failed stage and its established D5 taxonomy mapping."""
    for boundary, historical, detail in _FIRST_DIVERGENCE_ORDER:
        outcome = boundaries.get(boundary, "PASS")
        if outcome not in {"PASS", "FAIL"}:
            raise ValueError(f"invalid {boundary} boundary outcome")
        if outcome == "FAIL":
            return detail, historical
    return "NO_DIVERGENCE", "NONE"


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256(encoded.encode("utf-8"))


def _git_blob(root: Path, checkpoint: str, fixture: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{checkpoint}:{fixture}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _load_fixture(root: Path, spec: CorpusSpec) -> list[dict[str, Any]]:
    path = root / spec.fixture
    raw = path.read_bytes()
    if _sha256(raw) != spec.raw_sha256:
        raise CorpusIntegrityError(f"Historical fixture bytes changed: {spec.fixture}")
    if _git_blob(root, spec.checkpoint, spec.fixture) != spec.blob_sha256:
        raise CorpusIntegrityError(f"Historical checkpoint blob changed: {spec.fixture}")
    current_blob = subprocess.run(
        ["git", "hash-object", str(path)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current_blob != spec.blob_sha256:
        raise CorpusIntegrityError(f"Current fixture differs from accepted blob: {spec.fixture}")
    payload = json.loads(raw)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list):
        raise CorpusIntegrityError(f"Invalid historical cases list: {spec.fixture}")
    return cases


def _adapt_case(
    case: dict[str, Any],
    *,
    spec: CorpusSpec,
    protected_role: str | None = None,
) -> AdaptedCase:
    request = case.get("request")
    report_caps = case.get("expected_report_capabilities")
    sections = case.get("expected_sections")
    unresolved_count = case.get("expected_unresolved_count")
    if not isinstance(request, str) or not request:
        raise CorpusIntegrityError(f"Missing request text in {spec.fixture}")
    if not isinstance(report_caps, list) or not all(isinstance(item, str) for item in report_caps):
        raise CorpusIntegrityError(f"Invalid report gold in {spec.fixture}")
    if not isinstance(sections, list) or any(
        not isinstance(section, list) or not all(isinstance(item, str) for item in section)
        for section in sections
    ):
        raise CorpusIntegrityError(f"Invalid section gold in {spec.fixture}")
    if not isinstance(unresolved_count, int) or unresolved_count < 0:
        raise CorpusIntegrityError(f"Invalid unresolved-count gold in {spec.fixture}")
    return AdaptedCase(
        source_fixture=spec.fixture,
        source_checkpoint=spec.checkpoint,
        source_blob_sha256=spec.blob_sha256,
        case_id=str(case["case_id"]),
        family=str(case["family"]),
        request=request,
        request_sha256=_sha256(request.encode("utf-8")),
        expected_report_capabilities=tuple(report_caps),
        expected_sections=tuple(tuple(section) for section in sections),
        expected_unresolved_count=unresolved_count,
        residual_class=case.get("residual_class"),
        protected_role=protected_role,
    )


def load_corpus_index(repo_root: Path) -> CorpusIndex:
    """Read the frozen 96-case corpus and deterministically join P8 canaries."""
    root = repo_root.resolve()
    adapted: list[AdaptedCase] = []
    by_fixture: dict[str, dict[str, dict[str, Any]]] = {}
    specs = {spec.fixture: spec for spec in CORPORA}

    for spec in CORPORA:
        rows = _load_fixture(root, spec)
        identities: dict[str, dict[str, Any]] = {}
        for row in rows:
            case_id = row.get("case_id")
            if not isinstance(case_id, str) or not case_id or case_id in identities:
                raise CorpusIntegrityError(f"Missing or duplicate case ID in {spec.fixture}")
            identities[case_id] = row
            adapted.append(_adapt_case(row, spec=spec))
        by_fixture[spec.fixture] = identities

    all_ids = [case.case_id for case in adapted]
    if len(all_ids) != len(set(all_ids)):
        raise CorpusIntegrityError("Duplicate case identity across historical planner corpora")
    request_counts = Counter(case.request.encode("utf-8") for case in adapted)
    if any(count > 1 for count in request_counts.values()):
        raise CorpusIntegrityError("Duplicate exact request bytes across historical corpora")

    p7_path = root / P7_FIXTURE
    if _sha256(p7_path.read_bytes()) != P7_RAW_SHA256:
        raise CorpusIntegrityError("P7 authoritative fixture bytes changed")
    p8_path = root / P8_FIXTURE
    p8_raw = p8_path.read_bytes()
    if _sha256(p8_raw) != P8_RAW_SHA256:
        raise CorpusIntegrityError("P8 canary fixture bytes changed")
    p8 = json.loads(p8_raw)

    p7_rows = by_fixture[P7_FIXTURE]
    canary_rows = _join_p8_rows(p7_rows, p8)
    canaries: list[AdaptedCase] = []
    p7_spec = specs[P7_FIXTURE]
    for source, role in canary_rows:
        canaries.append(_adapt_case(source, spec=p7_spec, protected_role=role))
    return CorpusIndex(cases=tuple(adapted), canary_cases=tuple(canaries))


def _join_p8_rows(
    p7_rows: dict[str, dict[str, Any]],
    p8_payload: dict[str, Any],
) -> tuple[tuple[dict[str, Any], str], ...]:
    """Resolve hash-only P8 labels against exact P7 request and gold bytes."""
    canaries: list[tuple[dict[str, Any], str]] = []
    seen_p8: set[str] = set()
    rows = p8_payload.get("cases")
    if not isinstance(rows, list):
        raise CorpusIntegrityError("P8 cases must be a list")
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or case_id in seen_p8:
            raise CorpusIntegrityError("Missing or duplicate P8 canary case identity")
        seen_p8.add(case_id)
        if "request" in row:
            raise CorpusIntegrityError("P8 must not duplicate authoritative request text")
        source = p7_rows.get(case_id)
        if source is None:
            raise CorpusIntegrityError(f"P8 case has no unique P7 source: {case_id}")
        if not isinstance(source.get("request"), str):
            raise CorpusIntegrityError(f"P7 request is malformed: {case_id}")
        request_sha = _sha256(str(source["request"]).encode("utf-8"))
        if row.get("request_sha256") != request_sha:
            raise CorpusIntegrityError(f"P8 request hash mismatch: {case_id}")
        expected_gold = {
            "family": source["family"],
            "expected_report_capabilities": source["expected_report_capabilities"],
            "expected_sections": source["expected_sections"],
            "expected_unresolved_count": source["expected_unresolved_count"],
        }
        if row.get("gold_sha256") != _canonical_json_sha256(expected_gold):
            raise CorpusIntegrityError(f"P8 gold hash mismatch: {case_id}")
        role = row.get("role")
        if not isinstance(role, str) or not role:
            raise CorpusIntegrityError(f"P8 canary role is missing: {case_id}")
        canaries.append((source, role))
    if len(canaries) != 12:
        raise CorpusIntegrityError(f"Expected 12 P8 canaries, found {len(canaries)}")
    return tuple(canaries)


def audit_holdout_request(repo_root: Path, request: str = "Plot Gamma Ray.") -> dict[str, Any]:
    """Compare B01 against the frozen holdout by exact UTF-8 request bytes."""
    path = repo_root / HOLDOUT_FIXTURE
    payload = json.loads(path.read_bytes())
    request_bytes = request.encode("utf-8")
    request_sha = _sha256(request_bytes)
    matches = []
    for case in payload.get("cases", []):
        candidate = case.get("request")
        if isinstance(candidate, str):
            candidate_bytes = candidate.encode("utf-8")
            if candidate_bytes == request_bytes or _sha256(candidate_bytes) == request_sha:
                matches.append({"case_id": case.get("id"), "request_sha256": request_sha})
    if len(matches) > 1:
        raise CorpusIntegrityError("B01 request has multiple exact holdout matches")
    return {
        "request_sha256": request_sha,
        "match_count": len(matches),
        "matches": matches,
        "disposition": "EXPOSED_DIAGNOSTIC_CASE" if matches else "B01_NOT_IN_A10_HOLDOUT",
        "fresh_holdout_count": len(payload["cases"]) - len(matches),
    }


def _operation_observations(plan: _PlannerWirePlan) -> tuple[OperationObservation, ...]:
    observations: list[OperationObservation] = []
    if plan.report_task is not None:
        for operation in plan.report_task.operations:
            observations.append(
                OperationObservation(
                    owner="report",
                    scope_ref=operation.scope_ref,
                    local_ref=operation.local_ref,
                    object_kind=operation.object_kind,
                    verb=operation.verb,
                    semantic_ref=operation.semantic_ref,
                    target_clue=operation.target_clue,
                )
            )
    for task in plan.section_tasks:
        for operation in task.operations:
            observations.append(
                OperationObservation(
                    owner=f"section:{task.scope_ref}",
                    scope_ref=operation.scope_ref,
                    local_ref=operation.local_ref,
                    object_kind=operation.object_kind,
                    verb=operation.verb,
                    semantic_ref=operation.semantic_ref,
                    target_clue=operation.target_clue,
                )
            )
    return tuple(observations)


def score_plan(case: AdaptedCase, plan: _PlannerWirePlan | None) -> ScoreResult:
    """Score frozen historical invariants against an actual current wire plan."""
    if plan is None:
        return ScoreResult(
            disposition="PLANNER_TERMINAL_FAILURE",
            passed=False,
            findings=("planner_returned_no_wire_plan",),
            operation_observations=(),
            operation_target_comparison="NO_PLAN",
            source_identity_comparison="UNSCORABLE_NO_HISTORICAL_SOURCE_GOLD",
            first_divergence="PLANNER_TERMINAL_FAILURE",
            historical_divergence="PROVIDER_OR_STRUCTURED",
        )

    findings: list[str] = []
    expected_report = bool(case.expected_report_capabilities)
    if (plan.report_task is not None) != expected_report:
        findings.append("report_work_ownership_mismatch")
    if plan.report_task is not None and Counter(plan.report_task.capability_ids) != Counter(
        case.expected_report_capabilities
    ):
        findings.append("report_capability_set_mismatch")

    actual_sections = [Counter(task.capability_ids) for task in plan.section_tasks]
    expected_sections = [Counter(section) for section in case.expected_sections]
    if len(actual_sections) != len(expected_sections):
        findings.append("section_count_mismatch")
    elif Counter(frozenset(counter.items()) for counter in actual_sections) != Counter(
        frozenset(counter.items()) for counter in expected_sections
    ):
        findings.append("section_capability_set_mismatch")

    actual_unresolved = len(plan.unresolved_requirements) + len(plan.unresolved_semantics)
    if actual_unresolved != case.expected_unresolved_count:
        findings.append("unresolved_count_mismatch")

    operations = _operation_observations(plan)
    if any(
        operation.scope_ref != "report" for operation in operations if operation.owner == "report"
    ):
        findings.append("report_operation_scope_mismatch")
    for observation in operations:
        if observation.owner.startswith("section:"):
            expected_scope = observation.owner.removeprefix("section:")
            if observation.scope_ref != expected_scope:
                findings.append("section_operation_scope_mismatch")
                break

    if actual_unresolved and actual_unresolved == case.expected_unresolved_count and not findings:
        disposition = "UNRESOLVED_SAFE"
    elif actual_unresolved and actual_unresolved != case.expected_unresolved_count:
        disposition = "UNRESOLVED_MISMATCH"
    else:
        disposition = "PLANNER_PLAN"
    return ScoreResult(
        disposition=disposition,
        passed=not findings,
        findings=tuple(findings),
        operation_observations=operations,
        operation_target_comparison="UNSCORABLE_NO_HISTORICAL_OPERATION_GOLD",
        source_identity_comparison="UNSCORABLE_NO_HISTORICAL_SOURCE_GOLD",
        first_divergence=("NO_DIVERGENCE" if not findings else "PLANNER_SEMANTIC"),
        historical_divergence="NONE" if not findings else "SEMANTIC",
    )

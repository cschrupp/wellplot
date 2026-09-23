"""CM-56R8R corrected semantic evaluation and future live harness."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import re
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from scripts.cm56_post_r4_typed_shadow import production_source_summary
from scripts.cm56_typed_section_shadow import (
    _case_request,
    _document,
    audit_input_sufficiency,
    build_fixture_enricher,
    build_source_candidates,
    case_corpus_sha256,
    load_case_definitions,
)
from scripts.cm56r6_authoritative_request import (
    AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
    _select_case_section,
    _sha256,
    build_authoritative_worker_input,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import SemanticPlanner
from wellplot.agent.code_mode.section_semantics import (
    SectionSemanticDraft,
    SectionSemanticValidationError,
    SemanticSampleAxis,
    SemanticScale,
)
from wellplot.agent.code_mode.semantic_section_compiler import (
    SectionSemanticCompilationError,
    compile_section_semantics,
)
from wellplot.agent.code_mode.typed_section_worker import (
    RESPONSE_SCHEMA_SHA256,
    build_typed_section_input,
    serialize_typed_section_input,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

EXPERIMENT_VERSION = "CM-56R8R"
EVALUATOR_VERSION = "cm56r8r.corrected-evaluator.v1"
BASELINE_SHA = "17da03e"
FROZEN_MODEL = "Qwen3.6-35B-A3B-MTP-GGUF"
CASE_CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
CONTRACT_PATH = Path(__file__).resolve().parents[1] / (
    "docs/evaluations/agent-code-mode/CM-56R8R-semantic-contracts.json"
)
EVALUATION_CONTRACT_PATH = Path(__file__).resolve().parents[1] / (
    "docs/evaluations/agent-code-mode/CM-56R8R-evaluation-contract.json"
)
EVALUATION_CONTRACT_VERSION = "cm56r8r.semantic-evaluation.v1"
PLANNER_TEMPERATURE = 0.0
WORKER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 3
MAX_TOKENS_PARAMETER = "max_tokens"
EVALUATOR_SOURCE_PATH = Path(__file__).resolve()
REPRESENTATION_CASES = (
    "scalar_linear",
    "reverse_scale",
    "generic_raster",
    "waveform",
    "vdl_sample_axis",
)
CONTRACT_INSTRUCTION = (
    "\n\nSemantic contract use:\n"
    "The semantic_contracts object defines the authoritative mapping between "
    "domain-language concepts and WellPlot semantic IR fields. Use those mappings "
    "when translating explicit scientific semantics into SectionSemanticDraft. "
    "The JSON response schema defines legal structure; the contracts define what "
    "that structure means and when each field is used. Do not invent semantics "
    "absent from the authoritative original request. Contract examples illustrate "
    "mappings only; never copy example values unless the authoritative request "
    "contains those values."
)
_PATH_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_SCALE_DEFAULTS = {"kind": "linear", "reverse": False}
_SCALE_FIELDS = ("kind", "minimum", "maximum", "reverse", "unit")
_SAMPLE_AXIS_FIELDS = (
    "unit",
    "source_origin",
    "source_step",
    "minimum",
    "maximum",
    "tick_count",
)


@dataclass(frozen=True, slots=True)
class CorrectedSemanticEvaluation:
    """Leaf-level semantic comparison for one validated draft."""

    checks: dict[str, bool]
    leaf_statuses: dict[str, str]
    omissions: tuple[str, ...]
    unrequested_semantics: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        """Return whether all applicable semantics passed without extras."""
        return not self.omissions and not self.unrequested_semantics


def evaluator_source_sha256() -> str:
    """Return the exact digest of the evaluator source used for execution."""
    return _sha256_bytes(EVALUATOR_SOURCE_PATH.read_bytes())


def _canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    """Return a SHA-256 digest for an artifact's exact bytes."""
    return hashlib.sha256(value).hexdigest()


def _load_json_artifact(path: Path) -> tuple[dict[str, object], str]:
    """Load one versioned JSON artifact and return its exact-byte digest."""
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}.")
    return value, _sha256_bytes(raw)


def load_semantic_contracts(
    path: Path = CONTRACT_PATH,
) -> tuple[dict[str, object], str]:
    """Load the corrected machine-checkable semantic contracts."""
    artifact, digest = _load_json_artifact(path)
    if artifact.get("version") != "cm56r8r.semantic-contracts.v1":
        raise ValueError("Unexpected CM-56R8R semantic-contract version.")
    contracts = artifact.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("Semantic contract artifact must contain contracts.")
    return artifact, digest


def load_evaluation_contract(
    path: Path = EVALUATION_CONTRACT_PATH,
) -> tuple[dict[str, object], str]:
    """Load the corrected evaluator policy and its exact-byte digest."""
    artifact, digest = _load_json_artifact(path)
    if artifact.get("version") != EVALUATION_CONTRACT_VERSION:
        raise ValueError("Unexpected CM-56R8R evaluation-contract version.")
    return artifact, digest


def select_semantic_contracts(
    capability_ids: Sequence[str],
    artifact: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    """Select only capability-local contracts relevant to the task."""
    requested = set(capability_ids)
    contracts = artifact.get("contracts", ())
    return tuple(
        contract
        for contract in contracts
        if isinstance(contract, dict) and contract.get("capability_id") in requested
    )


def build_contract_worker_input(
    authoritative_input: str,
    *,
    contracts: Sequence[Mapping[str, object]],
) -> str:
    """Add only corrected semantic contracts to the authoritative payload."""
    payload = json.loads(authoritative_input)
    if not isinstance(payload, dict):
        raise ValueError("Authoritative typed input must serialize to an object.")
    payload["semantic_contracts"] = list(contracts)
    return _canonical_json(payload)


def semantic_contract_only_differs(variant_a: str, variant_b: str) -> bool:
    """Verify B is exactly A plus one semantic-contract field."""
    left = json.loads(variant_a)
    right = json.loads(variant_b)
    contracts = right.pop("semantic_contracts", None)
    return isinstance(contracts, list) and left == right


def build_contract_system_prompt() -> str:
    """Return the R8 authoritative prompt plus the bounded R8R instruction."""
    return AUTHORITATIVE_REQUEST_SYSTEM_PROMPT + CONTRACT_INSTRUCTION


def _path_tokens(path: str) -> tuple[str, ...]:
    """Parse a bounded dotted/list path used by the declarative overlay."""
    return tuple(_PATH_TOKEN_RE.findall(path))


def _remove_expected_path(expected: dict[str, object], path: str) -> None:
    """Remove one declared expected field without case-specific evaluator code."""
    tokens = _path_tokens(path)
    current: object = expected
    for token in tokens[:-1]:
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise ValueError(f"Cannot traverse expected path {path!r}.")
    leaf = tokens[-1]
    if isinstance(current, list):
        raise ValueError(f"Expected overlay path must end at an object field: {path!r}.")
    if not isinstance(current, dict):
        raise ValueError(f"Expected overlay path does not address an object: {path!r}.")
    current.pop(leaf, None)


def corrected_expected_for_case(
    case: Mapping[str, object],
    evaluation_contract: Mapping[str, object],
) -> dict[str, object]:
    """Apply only the declarative R8R expected-semantic overlay."""
    expected_sections = case.get("expected_sections", ())
    if not expected_sections:
        raise ValueError(f"Case {case.get('case_id')!r} has no expected section.")
    expected = copy.deepcopy(expected_sections[0])
    if not isinstance(expected, dict):
        raise ValueError("Expected section must be a JSON object.")
    overlays = evaluation_contract.get("case_overlays", {})
    overlay = overlays.get(case.get("case_id"), {}) if isinstance(overlays, dict) else {}
    for path in overlay.get("remove_expected_paths", ()):
        _remove_expected_path(expected, str(path))
    return expected


def normalize_scale(value: object) -> dict[str, object] | None:
    """Normalize expected and generated scales through the same semantic model."""
    if value is None:
        return None
    return SemanticScale.model_validate(value).model_dump(mode="json", exclude_none=True)


def normalize_sample_axis(value: object) -> dict[str, object] | None:
    """Normalize expected and generated sample axes symmetrically."""
    if value is None:
        return None
    return SemanticSampleAxis.model_validate(value).model_dump(mode="json", exclude_none=True)


def _status_for_value(expected: object, actual: object) -> str:
    """Compare normalized scalar values at one semantic leaf."""
    return "PASS" if expected == actual else "WRONG_VALUE"


def _compare_nested(
    *,
    path: str,
    expected: object,
    actual: object,
    normalizer: object,
    intrinsic_defaults: Mapping[str, object],
) -> tuple[dict[str, str], list[str]]:
    """Compare one normalized object and classify missing/extra leaves."""
    normalize = normalizer
    expected_value = normalize(expected)  # type: ignore[operator]
    actual_value = normalize(actual) if actual is not None else None  # type: ignore[operator]
    statuses: dict[str, str] = {}
    extras: list[str] = []
    if expected_value is None:
        if actual_value is not None:
            for field, value in actual_value.items():
                if field in intrinsic_defaults and value == intrinsic_defaults[field]:
                    continue
                extras.append(f"{path}.{field}")
        return statuses, extras
    if actual_value is None:
        for field in expected_value:
            statuses[f"{path}.{field}"] = "MISSING"
        return statuses, extras
    for field, expected_field in expected_value.items():
        leaf = f"{path}.{field}"
        if field not in actual_value:
            statuses[leaf] = "MISSING"
        else:
            statuses[leaf] = _status_for_value(expected_field, actual_value[field])
    for field, actual_field in actual_value.items():
        if field not in expected_value:
            if field in intrinsic_defaults and actual_field == intrinsic_defaults[field]:
                continue
            extras.append(f"{path}.{field}")
    return statuses, extras


def _enum_value(value: object) -> object:
    """Project string-enum values without retaining implementation objects."""
    return getattr(value, "value", value)


def evaluate_semantic_draft_r8r(
    draft: SectionSemanticDraft,
    *,
    expected: Mapping[str, object],
) -> CorrectedSemanticEvaluation:
    """Evaluate semantic leaves with symmetric model normalization."""
    checks: dict[str, bool] = {}
    statuses: dict[str, str] = {}
    unrequested: list[str] = []

    def add_check(path: str, passed: bool) -> None:
        checks[path] = passed
        statuses[path] = "PASS" if passed else "WRONG_VALUE"

    def add_unrequested(paths: Sequence[str]) -> None:
        for path in paths:
            statuses[path] = "UNREQUESTED_EXTRA"
            unrequested.append(path)

    add_check("title_valid", draft.title == expected.get("title"))
    add_check("source_selection_valid", draft.source_candidate == expected.get("source_candidate"))
    expected_tracks = list(expected.get("tracks", ()))
    add_check("track_count_valid", len(draft.tracks) == len(expected_tracks))
    add_check(
        "track_order_valid",
        [track.kind for track in draft.tracks] == [item.get("kind") for item in expected_tracks],
    )
    add_check(
        "track_titles_valid",
        [track.title for track in draft.tracks] == [item.get("title") for item in expected_tracks],
    )

    for index, expected_track in enumerate(expected_tracks):
        prefix = f"tracks[{index}]"
        actual_track = draft.tracks[index] if index < len(draft.tracks) else None
        if actual_track is None:
            add_check(f"{prefix}.present", False)
            continue
        if "x_scale" in expected_track:
            scale_statuses, extras = _compare_nested(
                path=f"{prefix}.x_scale",
                expected=expected_track["x_scale"],
                actual=actual_track.x_scale,
                normalizer=normalize_scale,
                intrinsic_defaults=_SCALE_DEFAULTS,
            )
            statuses.update(scale_statuses)
            add_unrequested(extras)
        elif actual_track.x_scale is not None:
            _, extras = _compare_nested(
                path=f"{prefix}.x_scale",
                expected=None,
                actual=actual_track.x_scale,
                normalizer=normalize_scale,
                intrinsic_defaults=_SCALE_DEFAULTS,
            )
            add_unrequested(extras)

        expected_bindings = list(expected_track.get("bindings", ()))
        actual_bindings = list(actual_track.bindings)
        add_check(f"{prefix}.binding_count", len(actual_bindings) == len(expected_bindings))
        add_check(
            f"{prefix}.binding_order",
            [binding.kind for binding in actual_bindings]
            == [item.get("kind", "curve") for item in expected_bindings],
        )
        add_check(
            f"{prefix}.binding_channels",
            [binding.channel for binding in actual_bindings]
            == [item.get("channel") for item in expected_bindings],
        )
        ids = [binding.semantic_id for binding in actual_bindings]
        add_check(f"{prefix}.binding_ids", len(ids) == len(set(ids)) and all(ids))
        for binding_index, expected_binding in enumerate(expected_bindings):
            binding_prefix = f"{prefix}.bindings[{binding_index}]"
            actual_binding = (
                actual_bindings[binding_index] if binding_index < len(actual_bindings) else None
            )
            if actual_binding is None:
                for field_name in ("scale", "profile", "sample_axis"):
                    if field_name in expected_binding:
                        expected_value = expected_binding[field_name]
                        if field_name == "scale":
                            normalized = normalize_scale(expected_value)
                        elif field_name == "sample_axis":
                            normalized = normalize_sample_axis(expected_value)
                        else:
                            normalized = None
                        if field_name == "profile":
                            statuses[f"{binding_prefix}.profile"] = "MISSING"
                            continue
                        for field in normalized or {}:
                            statuses[f"{binding_prefix}.{field_name}.{field}"] = "MISSING"
                continue
            if "scale" in expected_binding:
                scale_statuses, extras = _compare_nested(
                    path=f"{binding_prefix}.scale",
                    expected=expected_binding["scale"],
                    actual=getattr(actual_binding, "scale", None),
                    normalizer=normalize_scale,
                    intrinsic_defaults=_SCALE_DEFAULTS,
                )
                statuses.update(scale_statuses)
                add_unrequested(extras)
            elif getattr(actual_binding, "scale", None) is not None:
                _, extras = _compare_nested(
                    path=f"{binding_prefix}.scale",
                    expected=None,
                    actual=getattr(actual_binding, "scale", None),
                    normalizer=normalize_scale,
                    intrinsic_defaults=_SCALE_DEFAULTS,
                )
                add_unrequested(extras)
            if "profile" in expected_binding:
                expected_profile = _enum_value(expected_binding["profile"])
                actual_profile = _enum_value(getattr(actual_binding, "profile", None))
                status = "PASS" if actual_profile == expected_profile else "WRONG_VALUE"
                statuses[f"{binding_prefix}.profile"] = (
                    "MISSING" if actual_profile is None else status
                )
            elif getattr(actual_binding, "profile", None) is not None:
                add_unrequested((f"{binding_prefix}.profile",))
            if "sample_axis" in expected_binding:
                axis_statuses, extras = _compare_nested(
                    path=f"{binding_prefix}.sample_axis",
                    expected=expected_binding["sample_axis"],
                    actual=getattr(actual_binding, "sample_axis", None),
                    normalizer=normalize_sample_axis,
                    intrinsic_defaults={},
                )
                statuses.update(axis_statuses)
                add_unrequested(extras)
            elif getattr(actual_binding, "sample_axis", None) is not None:
                _, extras = _compare_nested(
                    path=f"{binding_prefix}.sample_axis",
                    expected=None,
                    actual=getattr(actual_binding, "sample_axis", None),
                    normalizer=normalize_sample_axis,
                    intrinsic_defaults={},
                )
                add_unrequested(extras)

    omissions = tuple(sorted(path for path, status in statuses.items() if status != "PASS"))
    return CorrectedSemanticEvaluation(
        checks=checks,
        leaf_statuses=dict(sorted(statuses.items())),
        omissions=omissions,
        unrequested_semantics=tuple(sorted(set(unrequested))),
    )


def _scientific_family(path: str) -> str | None:
    """Map corrected leaf paths to scientific families."""
    if ".x_scale." in path:
        return "track_scale"
    if ".scale." in path:
        return "binding_scale"
    if path.endswith(".profile"):
        return "raster_profile"
    if ".sample_axis." in path:
        return "sample_axis"
    return None


def _rate(numerator: int, denominator: int) -> dict[str, object]:
    """Represent a bounded rate."""
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent": round(100 * numerator / denominator, 2) if denominator else None,
    }


def _eligible(result: Mapping[str, object]) -> bool:
    """Return whether a variant reached semantic comparison."""
    return bool(
        result.get("structured_valid")
        and result.get("context_valid")
        and result.get("compiler_valid")
    )


def _r8r_generation_request(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
) -> StructuredGenerationRequest:
    """Build the worker request from the frozen R8R execution controls."""
    return StructuredGenerationRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_seconds=timeout_seconds,
        temperature=WORKER_TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def _population_integrity(
    rows: Sequence[Mapping[str, object]],
    *,
    expected_by_case: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Check that rows form the complete, comparable R8R population."""
    expected_cases = set(REPRESENTATION_CASES)
    reasons: list[str] = []
    expected_keys = {
        (case_id, attempt_index)
        for case_id in REPRESENTATION_CASES
        for attempt_index in range(ATTEMPTS)
    }
    actual_keys: list[tuple[object, object]] = [
        (row.get("case_id"), row.get("attempt_index")) for row in rows
    ]

    if len(rows) != len(expected_keys):
        reasons.append("row_count")
    if set(expected_by_case) != expected_cases:
        reasons.append("expected_case_population")
    if len(set(actual_keys)) != len(actual_keys):
        reasons.append("duplicate_case_attempt")
    if set(actual_keys) != expected_keys:
        reasons.append("missing_or_unexpected_case_attempt")
    for row in rows:
        input_sufficiency = row.get("input_sufficiency")
        if (
            not isinstance(input_sufficiency, Mapping)
            or input_sufficiency.get("sufficient") is not True
        ):
            reasons.append("input_insufficient")
        if row.get("semantic_contract_only_diff") is not True:
            reasons.append("semantic_contract_diff")
        for variant in ("a", "b"):
            value = row.get(variant)
            if not isinstance(value, Mapping) or not _eligible(value):
                reasons.append(f"{variant}_not_evaluation_eligible")

    return {
        "complete": not reasons,
        "expected_rows": len(expected_keys),
        "actual_rows": len(rows),
        "expected_cases": list(REPRESENTATION_CASES),
        "actual_cases": sorted(
            {str(row.get("case_id")) for row in rows if row.get("case_id") is not None}
        ),
        "reasons": sorted(set(reasons)),
    }


def aggregate_r8r_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    expected_by_case: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Aggregate corrected leaf statuses without changing generated outputs."""
    result: dict[str, object] = {
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_source_sha256": evaluator_source_sha256(),
    }
    population = _population_integrity(rows, expected_by_case=expected_by_case)
    pairwise: dict[str, dict[str, int]] = defaultdict(
        lambda: {"both_pass": 0, "a_fail_b_pass": 0, "a_pass_b_fail": 0, "both_fail": 0}
    )
    recoveries = 0
    regressions = 0
    for variant in ("a", "b"):
        eligible_rows = [
            row for row in rows if isinstance(row.get(variant), Mapping) and _eligible(row[variant])
        ]
        family_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        field_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        scientific_pass = 0
        accepted = 0
        for row in eligible_rows:
            output = row[variant]
            assert isinstance(output, Mapping)
            statuses = output.get("leaf_statuses", {})
            if output.get("semantic_accepted"):
                accepted += 1
            applicable = 0
            passed = True
            for path, status in dict(statuses).items():
                family = _scientific_family(str(path))
                if family is None:
                    continue
                applicable += 1
                field_counts[str(path)][0] += 1
                field_counts[str(path)][1] += status == "PASS"
                family_counts[family][0] += 1
                family_counts[family][1] += status == "PASS"
                passed = passed and status == "PASS"
            scientific_pass += applicable > 0 and passed
        result[variant.upper()] = {
            "rows": len(rows),
            "evaluation_eligible": len(eligible_rows),
            "scientific_only_pass": _rate(scientific_pass, len(eligible_rows)),
            "semantic_accepted": _rate(accepted, len(eligible_rows)),
            "scientific_fields": {
                path: {
                    "pass": _rate(passed, applicable),
                    "fail": _rate(applicable - passed, applicable),
                }
                for path, (applicable, passed) in sorted(field_counts.items())
            },
            "scientific_families": {
                family: {
                    "pass": _rate(passed, applicable),
                    "fail": _rate(applicable - passed, applicable),
                }
                for family, (applicable, passed) in sorted(family_counts.items())
            },
        }

    for row in rows:
        a = row.get("a")
        b = row.get("b")
        if (
            not isinstance(a, Mapping)
            or not isinstance(b, Mapping)
            or not _eligible(a)
            or not _eligible(b)
        ):
            continue
        a_statuses = dict(a.get("leaf_statuses", {}))
        b_statuses = dict(b.get("leaf_statuses", {}))
        for path in sorted(set(a_statuses) | set(b_statuses)):
            family = _scientific_family(path)
            if family is None or path not in a_statuses or path not in b_statuses:
                continue
            a_pass = a_statuses[path] == "PASS"
            b_pass = b_statuses[path] == "PASS"
            bucket = pairwise[path]
            if a_pass and b_pass:
                bucket["both_pass"] += 1
            elif not a_pass and b_pass:
                bucket["a_fail_b_pass"] += 1
                recoveries += 1
            elif a_pass and not b_pass:
                bucket["a_pass_b_fail"] += 1
                regressions += 1
            else:
                bucket["both_fail"] += 1

    b_scientific_pass = result["B"]["scientific_only_pass"]["numerator"]
    b_eligible = result["B"]["evaluation_eligible"]
    if not population["complete"]:
        decision = "INCONCLUSIVE_SEMANTIC_CONTRACT"
    elif recoveries == 0:
        decision = "SEMANTIC_CONTRACT_NO_RECOVERY"
    elif b_scientific_pass == b_eligible and regressions == 0:
        decision = "SEMANTIC_CONTRACT_FULL_RECOVERY"
    elif b_scientific_pass:
        decision = "SEMANTIC_CONTRACT_PARTIAL_RECOVERY"
    else:
        decision = "SEMANTIC_CONTRACT_FIELD_RECOVERY_ONLY"
    result["pairwise_scientific_leaves"] = dict(sorted(pairwise.items()))
    result["scientific_recoveries"] = recoveries
    result["scientific_regressions"] = regressions
    result["population_integrity"] = population
    result["decision"] = decision
    return result


async def _generate_corrected_variant(
    backend: ModelBackendProtocol,
    *,
    serialized_input: str,
    system_prompt: str,
    section_context: object,
    document: object,
    expected: Mapping[str, object],
    timeout_seconds: float,
) -> dict[str, object]:
    """Run one provider response through corrected evaluation only."""
    try:
        generated = await backend.generate_structured(
            request=_r8r_generation_request(
                system_prompt=system_prompt,
                user_prompt=serialized_input,
                timeout_seconds=timeout_seconds,
            ),
            response_model=SectionSemanticDraft,
        )
    except ProviderRequestError as error:
        return {
            "provider_call_completed": False,
            "structured_valid": False,
            "context_valid": False,
            "compiler_valid": False,
            "semantic_accepted": False,
            "provider_category": getattr(getattr(error, "category", None), "value", None),
            "error_type": type(error).__name__,
            "provider_input_sha256": _sha256(serialized_input),
            "provider_input_chars": len(serialized_input),
        }
    try:
        draft = SectionSemanticDraft.model_validate(generated.value)
    except ValidationError as error:
        return {
            "provider_call_completed": True,
            "structured_valid": False,
            "context_valid": False,
            "compiler_valid": False,
            "semantic_accepted": False,
            "provider_category": "validation",
            "error_type": type(error).__name__,
            "provider_input_sha256": _sha256(serialized_input),
            "provider_input_chars": len(serialized_input),
            "provider_metrics": generated.metrics.public_metadata(),
        }
    base = {
        "provider_call_completed": True,
        "structured_valid": True,
        "provider_input_sha256": _sha256(serialized_input),
        "provider_input_chars": len(serialized_input),
        "provider_metrics": generated.metrics.public_metadata(),
    }
    try:
        from wellplot.agent.code_mode.section_semantics import validate_section_semantics

        validate_section_semantics(draft, section_context=section_context)
    except SectionSemanticValidationError as error:
        return {
            **base,
            "context_valid": False,
            "compiler_valid": False,
            "semantic_accepted": False,
            "error_type": type(error).__name__,
            "error_code": getattr(getattr(error, "code", None), "value", None),
        }
    try:
        compile_section_semantics(
            draft,
            section_context=section_context,
            document=document,
            section_id_hint="cm56r8r-diagnostic",
        )
    except SectionSemanticCompilationError as error:
        return {
            **base,
            "context_valid": True,
            "compiler_valid": False,
            "semantic_accepted": False,
            "error_type": type(error).__name__,
            "error_code": getattr(getattr(error, "code", None), "value", None),
        }
    evaluation = evaluate_semantic_draft_r8r(draft, expected=expected)
    return {
        **base,
        "context_valid": True,
        "compiler_valid": True,
        "semantic_accepted": evaluation.accepted,
        "checks": evaluation.checks,
        "leaf_statuses": evaluation.leaf_statuses,
        "omissions": evaluation.omissions,
        "unrequested_semantics": evaluation.unrequested_semantics,
        "generated_semantic_projection": draft.model_dump(mode="json", exclude_none=True),
        "expected_semantic_projection": expected,
    }


async def run_corrected_attempt(
    case: Mapping[str, object],
    *,
    backend: ModelBackendProtocol,
    model: str,
    planner: SemanticPlanner,
    registry: CapabilityRegistry,
    contracts_artifact: Mapping[str, object],
    contract_sha256: str,
    evaluation_contract: Mapping[str, object],
    evaluation_contract_sha256: str,
    timeout_seconds: float,
    attempt_index: int,
) -> dict[str, object]:
    """Run one shared planner/enrichment result through corrected A and B."""
    row_metadata = {
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_source_sha256": evaluator_source_sha256(),
        "execution_controls": {
            "model": model,
            "planner_temperature": PLANNER_TEMPERATURE,
            "worker_temperature": WORKER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": timeout_seconds,
            "attempts_per_case": ATTEMPTS,
        },
    }
    document = _document()
    request = _case_request(case)
    started = time.perf_counter()
    try:
        plan = await planner.plan(
            request=request,
            mode="reconstruct",
            current_document_summary=AuthoringInspectionFacade(document)
            .document_summary()
            .model_dump(mode="json"),
            source_summary=production_source_summary(case),
            timeout_seconds=timeout_seconds,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        enriched = build_fixture_enricher(case).enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except (ProviderRequestError, SemanticEnrichmentError) as error:
        return {
            **row_metadata,
            "case_id": case["case_id"],
            "attempt_index": attempt_index,
            "classification": "PLANNER_OR_ENRICHMENT_FAILURE",
            "error_type": type(error).__name__,
            "error_code": getattr(getattr(error, "code", None), "value", None),
            "provider_category": getattr(getattr(error, "category", None), "value", None),
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }

    selected = _select_case_section(str(case["case_id"]), plan, enriched)
    if selected is None:
        return {
            **row_metadata,
            "case_id": case["case_id"],
            "attempt_index": attempt_index,
            "classification": "PLANNER_SECTION_SELECTION_FAILURE",
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    task, section_context = selected
    typed_input = build_typed_section_input(
        task,
        section_context=section_context,
        registry=registry,
    )
    base_input = serialize_typed_section_input(typed_input)
    authoritative_input = build_authoritative_worker_input(base_input, request)
    contracts = select_semantic_contracts(task.capability_ids, contracts_artifact)
    contract_input = build_contract_worker_input(authoritative_input, contracts=contracts)
    audit = audit_input_sufficiency(
        case,
        task=task,
        section_context=section_context,
        serialized_input=authoritative_input,
    )
    expected = corrected_expected_for_case(case, evaluation_contract)
    result_a = await _generate_corrected_variant(
        backend,
        serialized_input=authoritative_input,
        system_prompt=AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    result_b = await _generate_corrected_variant(
        backend,
        serialized_input=contract_input,
        system_prompt=build_contract_system_prompt(),
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    return {
        **row_metadata,
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "classification": "PAIRED_TYPED_ATTEMPT",
        "planner_temperature": PLANNER_TEMPERATURE,
        "worker_temperature": WORKER_TEMPERATURE,
        "natural_request_sha256": _sha256(request),
        "case_corpus_sha256": case_corpus_sha256(),
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "evaluation_contract_sha256": evaluation_contract_sha256,
        "a_system_prompt_sha256": _sha256(AUTHORITATIVE_REQUEST_SYSTEM_PROMPT),
        "b_system_prompt_sha256": _sha256(build_contract_system_prompt()),
        "semantic_contract_sha256": contract_sha256,
        "selected_capability_ids": list(task.capability_ids),
        "selected_contract_capability_ids": [
            str(contract["capability_id"]) for contract in contracts
        ],
        "authoritative_input_sha256": _sha256(authoritative_input),
        "contract_input_sha256": _sha256(contract_input),
        "semantic_contract_only_diff": semantic_contract_only_differs(
            authoritative_input, contract_input
        ),
        "input_sufficiency": {
            "sufficient": audit.sufficient,
            "facts": audit.facts,
            "missing_fact_ids": audit.missing_fact_ids,
        },
        "a": result_a,
        "b": result_b,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def validate_frozen_execution_controls(args: argparse.Namespace) -> None:
    """Reject any live invocation that differs from the frozen R8R controls."""
    expected = {
        "model": FROZEN_MODEL,
        "planner_temperature": PLANNER_TEMPERATURE,
        "worker_temperature": WORKER_TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_tokens_parameter": MAX_TOKENS_PARAMETER,
        "timeout": TIMEOUT_SECONDS,
        "attempts": ATTEMPTS,
    }
    actual = {
        "model": getattr(args, "model", None),
        "planner_temperature": getattr(args, "planner_temperature", PLANNER_TEMPERATURE),
        "worker_temperature": getattr(args, "worker_temperature", WORKER_TEMPERATURE),
        "max_output_tokens": getattr(args, "max_output_tokens", MAX_OUTPUT_TOKENS),
        "max_tokens_parameter": getattr(args, "max_tokens_parameter", MAX_TOKENS_PARAMETER),
        "timeout": getattr(args, "timeout", TIMEOUT_SECONDS),
        "attempts": getattr(args, "attempts", ATTEMPTS),
    }
    mismatches = {
        name: {"expected": expected[name], "actual": actual[name]}
        for name in expected
        if actual[name] != expected[name]
    }
    if mismatches:
        raise ValueError(f"CM-56R8R frozen controls rejected: {mismatches}")


def ensure_empty_evidence_path(path: Path) -> None:
    """Allow only a new or empty output file for one R8R population."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        raise FileExistsError(f"Refusing to append to non-empty CM-56R8R evidence file: {path}")


async def run_matrix(args: argparse.Namespace) -> None:
    """Run the corrected live matrix only after separate authorization."""
    from scripts.cm56_typed_section_shadow import _provider_configuration

    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise RuntimeError("CM-56 corpus hash changed from the frozen baseline.")
    validate_frozen_execution_controls(args)
    ensure_empty_evidence_path(args.output_jsonl)
    contracts_artifact, contract_sha256 = load_semantic_contracts()
    evaluation_contract, evaluation_contract_sha256 = load_evaluation_contract()
    provider_values = vars(args).copy()
    provider_values.update(
        timeout=TIMEOUT_SECONDS,
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )
    provider_args = argparse.Namespace(**provider_values)
    backend = _provider_configuration(provider_args)
    registry = create_builtin_registry()
    cases = [case for case in load_case_definitions() if case["case_id"] in REPRESENTATION_CASES]
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            planner = SemanticPlanner(backend=backend, registry=registry)
            for attempt_index in range(args.attempts):
                row = await run_corrected_attempt(
                    case,
                    backend=backend,
                    model=args.model,
                    planner=planner,
                    registry=registry,
                    contracts_artifact=contracts_artifact,
                    contract_sha256=contract_sha256,
                    evaluation_contract=evaluation_contract,
                    evaluation_contract_sha256=evaluation_contract_sha256,
                    timeout_seconds=TIMEOUT_SECONDS,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build the future R8R live CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def main() -> None:
    """Run R8R only when explicitly invoked after review."""
    asyncio.run(run_matrix(_parser().parse_args()))


if __name__ == "__main__":  # pragma: no cover
    main()

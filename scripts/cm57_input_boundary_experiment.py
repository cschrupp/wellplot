"""CM-57IB authoritative-request and metadata input-boundary experiment.

The default command performs deterministic pre-live validation only. Future
provider execution requires ``--live-authorized`` and an explicit checkpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

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
    _safe_text,
    _select_case_section,
)
from scripts.cm56r8r_semantic_contract_correction import (
    EVALUATOR_VERSION,
    MAX_OUTPUT_TOKENS,
    MAX_TOKENS_PARAMETER,
    PLANNER_TEMPERATURE,
    REPRESENTATION_CASES,
    RESPONSE_SCHEMA_SHA256,
    TIMEOUT_SECONDS,
    WORKER_TEMPERATURE,
    _generate_corrected_variant,
    corrected_expected_for_case,
    evaluator_source_sha256,
    load_evaluation_contract,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import PlannerSemanticFailure, SemanticPlanner
from wellplot.agent.code_mode.typed_section_worker import (
    TYPED_SECTION_SYSTEM_PROMPT,
    build_typed_section_input,
    response_schema_sha256,
    serialize_typed_section_input,
)
from wellplot.agent.providers.base import ModelBackendProtocol, ProviderRequestError
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

EXPERIMENT_VERSION = "CM-57IB"
DESIGN_BASELINE_SHA = "8d065ce44cef9459aec2c2608a627356c3085725"
FROZEN_MODEL = "qwen3.6-35b-a3b"
CASE_CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
EVALUATION_CONTRACT_SHA256 = "3e6c3c36d967acb60e6bb7cda13db95d76ed7a754eb92c4bcf5688d76b0da4da"
EVALUATOR_SHA256 = "4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49"
REQUEST_FIELD = "authoritative_request"
SEMANTIC_FIELD = "semantic_contracts"
ATTEMPTS = 3
OUTPUT_PATH = Path("/tmp/cm57ib-live-qwen.jsonl")
HARNESS_PATH = Path(__file__).resolve()
EVALUATION_CONTRACT_PATH = Path(__file__).resolve().parents[1] / (
    "docs/evaluations/agent-code-mode/CM-56R8R-evaluation-contract.json"
)

REQUEST_INSTRUCTION = (
    "\n\nInput authority:\n"
    "The authoritative_request field contains the user's original request and is "
    "the authoritative source of requested semantics. The section task provides "
    "scoped decomposition and routing. The bounded source/channel context provides "
    "available inputs. Preserve explicit semantics requested by the authoritative "
    "request, but do not invent semantics absent from it."
)
SEMANTIC_INSTRUCTION = (
    "\n\nCapability semantic metadata:\n"
    "The semantic_contracts field contains capability-specific WellPlot meanings "
    "that require explicit clarification. Use those mappings where applicable. "
    "For semantics not documented there, interpret the section task and normal "
    "SectionSemanticDraft schema without adding extra semantics."
)
ARM_ORDER = ("P", "R", "S", "RS")
_TARGET_PATHS = {
    "binding.profile",
    "binding.sample_axis.unit",
    "binding.sample_axis.source_origin",
    "binding.sample_axis.source_step",
    "binding.sample_axis.tick_count",
}
_FORBIDDEN_TARGET_PREFIXES = ("binding.scale", "track.x_scale.")
_FORBIDDEN_TEXT = (
    "cm-56",
    "r8r",
    "s1",
    "reverse_scale",
    "scalar_linear",
    "gate-a",
    "expected_semantic",
    "200 to 0",
    "0 to 200",
    "0 to 150",
    "200 to 1200",
    "-25 to 75",
    "10 to 90",
)


def _canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    """Hash exact artifact bytes."""
    return hashlib.sha256(value).hexdigest()


def _sha256(value: str) -> str:
    """Hash exact UTF-8 text."""
    return _sha256_bytes(value.encode("utf-8"))


def harness_source_sha256() -> str:
    """Return the exact byte hash of this harness."""
    return _sha256_bytes(HARNESS_PATH.read_bytes())


def validate_authorized_checkpoint(value: object) -> str:
    """Require a full lowercase hexadecimal Git SHA for future live runs."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("CM-57IB live execution requires a full lowercase 40-character Git SHA.")
    return value


def validate_frozen_execution_controls(args: argparse.Namespace) -> None:
    """Reject any future live invocation that changes frozen controls."""
    actual = {
        "model": getattr(args, "model", FROZEN_MODEL),
        "planner_temperature": getattr(args, "planner_temperature", PLANNER_TEMPERATURE),
        "worker_temperature": getattr(args, "worker_temperature", WORKER_TEMPERATURE),
        "max_output_tokens": getattr(args, "max_output_tokens", MAX_OUTPUT_TOKENS),
        "max_tokens_parameter": getattr(args, "max_tokens_parameter", MAX_TOKENS_PARAMETER),
        "timeout": getattr(args, "timeout", TIMEOUT_SECONDS),
        "attempts": getattr(args, "attempts", ATTEMPTS),
    }
    expected = {
        "model": FROZEN_MODEL,
        "planner_temperature": 0.0,
        "worker_temperature": 0.0,
        "max_output_tokens": 16384,
        "max_tokens_parameter": "max_tokens",
        "timeout": 900.0,
        "attempts": 3,
    }
    mismatches = {
        key: {"expected": expected[key], "actual": value}
        for key, value in actual.items()
        if value != expected[key]
    }
    if mismatches:
        raise ValueError(f"CM-57IB frozen controls rejected: {mismatches}")


def ensure_empty_evidence_path(path: Path = OUTPUT_PATH) -> None:
    """Reject an existing non-empty future evidence population."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        raise FileExistsError(f"Refusing to append to non-empty CM-57IB evidence: {path}")


def _metadata_projection(spec: object) -> dict[str, object]:
    """Project one capability's production metadata into provider-safe JSON."""
    metadata = getattr(spec, "semantic_metadata", None)
    if metadata is None:
        raise ValueError("Cannot project a capability without semantic metadata.")
    return {
        "capability_id": spec.capability_id,
        "purpose": metadata.purpose,
        "mappings": [
            {
                "concept": mapping.concept,
                "language_patterns": list(mapping.language_patterns),
                "targets": [
                    {"path": path, "value_cue": value_cue} for path, value_cue in mapping.targets
                ],
            }
            for mapping in metadata.mappings
        ],
        "distinctions": list(metadata.distinctions),
    }


def select_production_semantic_metadata(
    capability_ids: Sequence[str],
    registry: CapabilityRegistry,
) -> tuple[dict[str, object], ...]:
    """Select metadata by task-order from the production registry authority."""
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    for capability_id in capability_ids:
        spec = registry.get(capability_id)
        if spec.capability_id in seen or spec.semantic_metadata is None:
            continue
        selected.append(_metadata_projection(spec))
        seen.add(spec.capability_id)
    return tuple(selected)


def semantic_metadata_projection_sha256(
    projection: Sequence[Mapping[str, object]],
) -> str:
    """Hash a canonical provider-safe semantic metadata projection."""
    return _sha256(_canonical_json(list(projection)))


def _add_payload_field(serialized_input: str, field: str, value: object) -> str:
    """Add one structured experimental field without changing the base payload."""
    payload = json.loads(serialized_input)
    if not isinstance(payload, dict):
        raise ValueError("Typed worker input must serialize to a JSON object.")
    payload[field] = value
    return _canonical_json(payload)


def build_request_input(serialized_input: str, request: str) -> str:
    """Add only the redacted authoritative request field."""
    return _add_payload_field(serialized_input, REQUEST_FIELD, _safe_text(request))


def build_semantic_input(
    serialized_input: str,
    contracts: Sequence[Mapping[str, object]],
) -> str:
    """Add only the selected production metadata projection."""
    return _add_payload_field(serialized_input, SEMANTIC_FIELD, list(contracts))


def build_arm_inputs(
    serialized_input: str,
    *,
    request: str,
    contracts: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    """Build the four factorial payloads from one exact production payload."""
    request_input = build_request_input(serialized_input, request)
    semantic_input = (
        build_semantic_input(serialized_input, contracts) if contracts else serialized_input
    )
    future_input = build_semantic_input(request_input, contracts) if contracts else request_input
    return {"P": serialized_input, "R": request_input, "S": semantic_input, "RS": future_input}


def _without_field(serialized_input: str, field: str) -> tuple[dict[str, object], object]:
    """Remove one arm field for structural isolation checks."""
    value = json.loads(serialized_input)
    if not isinstance(value, dict):
        raise ValueError("Serialized arm input must be a JSON object.")
    removed = value.pop(field, None)
    return value, removed


def arm_isolation_flags(inputs: Mapping[str, str]) -> dict[str, bool]:
    """Prove each arm differs from P only by its authorized factor fields."""
    p = json.loads(inputs["P"])
    r_full = json.loads(inputs["R"])
    s_full = json.loads(inputs["S"])
    r, request = _without_field(inputs["R"], REQUEST_FIELD)
    s, contracts = _without_field(inputs["S"], SEMANTIC_FIELD)
    rs_full = json.loads(inputs["RS"])
    if not isinstance(rs_full, dict):
        raise ValueError("Serialized RS input must be a JSON object.")
    rs_without_request = dict(rs_full)
    rs_request = rs_without_request.pop(REQUEST_FIELD, None)
    rs_without_semantic = dict(rs_full)
    rs_contracts = rs_without_semantic.pop(SEMANTIC_FIELD, None)
    future = dict(rs_full)
    future.pop(REQUEST_FIELD, None)
    future.pop(SEMANTIC_FIELD, None)
    semantic_applicable = bool(contracts)
    return {
        "request_only_diff": isinstance(request, str) and r == p,
        "semantic_only_diff": (isinstance(contracts, list) and s == p)
        if semantic_applicable
        else s == p,
        "future_contract_only_diff": isinstance(rs_request, str) and future == p,
        "rs_without_request_equals_s": (
            isinstance(rs_request, str) and rs_without_request == s_full
        ),
        "rs_without_semantic_equals_r": (
            (isinstance(rs_contracts, list) and rs_without_semantic == r_full)
            if semantic_applicable
            else rs_without_semantic == r_full
        ),
        "semantic_contract_applicable": semantic_applicable,
        "P_equals_S": s == p,
        "R_equals_RS": json.loads(inputs["R"]) == json.loads(inputs["RS"])
        if not semantic_applicable
        else False,
    }


def build_arm_prompts(*, semantic_applicable: bool) -> dict[str, str]:
    """Compose prompts from the exact base and applicable factor instructions."""
    semantic = SEMANTIC_INSTRUCTION if semantic_applicable else ""
    return {
        "P": TYPED_SECTION_SYSTEM_PROMPT,
        "R": TYPED_SECTION_SYSTEM_PROMPT + REQUEST_INSTRUCTION,
        "S": TYPED_SECTION_SYSTEM_PROMPT + semantic,
        "RS": TYPED_SECTION_SYSTEM_PROMPT + REQUEST_INSTRUCTION + semantic,
    }


def validate_production_metadata(registry: CapabilityRegistry) -> dict[str, object]:
    """Audit the production metadata projection without mutating its source."""
    raster = registry.get("binding.raster")
    first = select_production_semantic_metadata(("binding.raster",), registry)
    second = select_production_semantic_metadata(("binding.raster",), registry)
    if first != second:
        raise ValueError("Production semantic metadata projection is not deterministic.")
    if not first or first[0]["capability_id"] != "binding.raster":
        raise ValueError("binding.raster metadata is not available from the registry.")
    target_paths = [
        target["path"] for mapping in first[0]["mappings"] for target in mapping["targets"]
    ]
    if set(target_paths) != _TARGET_PATHS:
        raise ValueError(f"Unexpected production metadata targets: {target_paths!r}")
    if any(path.startswith(_FORBIDDEN_TARGET_PREFIXES) for path in target_paths):
        raise ValueError("Production metadata contains forbidden scale mapping targets.")
    serialized = _canonical_json(first).casefold()
    leaked = [text for text in _FORBIDDEN_TEXT if text in serialized]
    if leaked:
        raise ValueError(f"Forbidden experiment text in production metadata: {leaked}")
    profile_pairs = {
        (target["path"], target["value_cue"])
        for mapping in first[0]["mappings"]
        for target in mapping["targets"]
        if target["path"] == "binding.profile"
    }
    if profile_pairs != {
        ("binding.profile", "generic"),
        ("binding.profile", "waveform"),
        ("binding.profile", "vdl"),
    }:
        raise ValueError("Production raster profile mappings differ from the accepted content.")
    sample_targets = {
        target["path"]
        for mapping in first[0]["mappings"]
        for target in mapping["targets"]
        if target["path"].startswith("binding.sample_axis.")
    }
    if sample_targets != _TARGET_PATHS - {"binding.profile"}:
        raise ValueError("Production sample-axis mappings differ from the accepted content.")
    if not any("track.x_scale" in text for text in first[0]["distinctions"]):
        raise ValueError("Production metadata lost the track/sample-axis distinction.")
    if raster.semantic_metadata is None:
        raise ValueError("binding.raster metadata unexpectedly disappeared.")
    return {
        "metadata_source": "CapabilitySpec.semantic_metadata",
        "capability_id": "binding.raster",
        "projection": first,
        "projection_sha256": semantic_metadata_projection_sha256(first),
        "target_paths": sorted(set(target_paths)),
        "same_intended_semantic_content_as_s1": True,
        "additional_scale_guidance": False,
    }


def _family(path: str) -> str | None:
    """Map evaluator leaves to scientific families."""
    if ".x_scale." in path:
        return "track_scale"
    if ".scale." in path:
        return "binding_scale"
    if path.endswith(".profile"):
        return "raster_profile"
    if ".sample_axis." in path:
        return "sample_axis"
    return None


def expected_family_inventory() -> dict[str, list[str]]:
    """Derive applicable scientific leaves from the frozen evaluator inputs."""
    contract, _ = load_evaluation_contract(EVALUATION_CONTRACT_PATH)
    inventory: dict[str, list[str]] = {}
    for case in load_case_definitions():
        case_id = str(case["case_id"])
        if case_id not in REPRESENTATION_CASES:
            continue
        expected = corrected_expected_for_case(case, contract)
        paths: set[str] = set()
        for track_index, track in enumerate(expected["tracks"]):
            prefix = f"tracks[{track_index}]"
            if "x_scale" in track:
                paths.update(f"{prefix}.x_scale.{field}" for field in track["x_scale"])
            for binding_index, binding in enumerate(track.get("bindings", ())):
                binding_prefix = f"{prefix}.bindings[{binding_index}]"
                if "scale" in binding:
                    paths.update(f"{binding_prefix}.scale.{field}" for field in binding["scale"])
                if "profile" in binding:
                    paths.add(f"{binding_prefix}.profile")
                if "sample_axis" in binding:
                    paths.update(
                        f"{binding_prefix}.sample_axis.{field}" for field in binding["sample_axis"]
                    )
        inventory[case_id] = sorted(paths)
    return inventory


def _frozen_artifact_metadata(registry: CapabilityRegistry) -> dict[str, object]:
    """Validate all frozen inputs before any future provider construction."""
    metadata = validate_production_metadata(registry)
    evaluation_contract, evaluation_sha = load_evaluation_contract(EVALUATION_CONTRACT_PATH)
    del evaluation_contract
    if evaluation_sha != EVALUATION_CONTRACT_SHA256:
        raise ValueError("Frozen evaluation-contract hash changed.")
    if evaluator_source_sha256() != EVALUATOR_SHA256:
        raise ValueError("Frozen evaluator source hash changed.")
    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise ValueError("Frozen case-corpus hash changed.")
    if response_schema_sha256() != RESPONSE_SCHEMA_SHA256:
        raise ValueError("Frozen response-schema hash changed.")
    return {
        "case_corpus_sha256": CASE_CORPUS_SHA256,
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_source_sha256": EVALUATOR_SHA256,
        "evaluation_contract_sha256": evaluation_sha,
        "production_metadata_projection_sha256": metadata["projection_sha256"],
        "metadata_source": metadata["metadata_source"],
    }


def build_pre_live_metadata() -> dict[str, object]:
    """Build deterministic provenance without constructing a provider."""
    registry = create_builtin_registry()
    artifacts = _frozen_artifact_metadata(registry)
    prompts = build_arm_prompts(semantic_applicable=True)
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": DESIGN_BASELINE_SHA,
        "authorized_checkpoint": None,
        "provider_calls": 0,
        "production_changes": 0,
        "arms": list(ARM_ORDER),
        "cases": list(REPRESENTATION_CASES),
        "attempts_per_case": ATTEMPTS,
        "future_shared_rows": 15,
        "future_worker_calls": 60,
        "future_planner_calls": 15,
        "request_field": REQUEST_FIELD,
        "semantic_field": SEMANTIC_FIELD,
        "artifacts": artifacts,
        "production_metadata": validate_production_metadata(registry),
        "prompt_sha256": {arm: _sha256(prompt) for arm, prompt in prompts.items()},
        "expected_family_inventory": expected_family_inventory(),
        "execution_controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "worker_temperature": WORKER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
            "attempts_per_case": ATTEMPTS,
        },
    }


def validate_frozen_artifacts(registry: CapabilityRegistry) -> dict[str, object]:
    """Return frozen artifact provenance or fail before provider construction."""
    return _frozen_artifact_metadata(registry)


def _variant_counts(rows: Sequence[Mapping[str, object]], arm: str) -> dict[str, object]:
    """Aggregate eligibility and scientific leaves for one arm."""
    eligible = [
        row["arms"][arm]
        for row in rows
        if isinstance(row.get("arms"), Mapping)
        and isinstance(row["arms"].get(arm), Mapping)
        and row["arms"][arm].get("compiler_valid")
    ]
    family_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "applicable": 0})
    accepted = sum(bool(value.get("semantic_accepted")) for value in eligible)
    for value in eligible:
        for path, status in value.get("leaf_statuses", {}).items():
            family = _family(str(path))
            if family is None:
                continue
            family_counts[family]["applicable"] += 1
            family_counts[family]["pass"] += status == "PASS"
    return {
        "evaluation_eligible": len(eligible),
        "full_semantic_acceptance": f"{accepted}/{len(eligible)}",
        "families": {
            family: {
                **counts,
                "fail": counts["applicable"] - counts["pass"],
            }
            for family, counts in sorted(family_counts.items())
        },
    }


def _population_integrity(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Fail closed unless all 15 shared rows contain four isolated arms."""
    expected = {
        (case_id, attempt) for case_id in REPRESENTATION_CASES for attempt in range(ATTEMPTS)
    }
    actual = [(row.get("case_id"), row.get("attempt_index")) for row in rows]
    reasons: list[str] = []
    if len(rows) != 15:
        reasons.append("row_count")
    if set(actual) != expected:
        reasons.append("missing_or_unexpected_case_attempt")
    if len(actual) != len(set(actual)):
        reasons.append("duplicate_case_attempt")
    for row in rows:
        input_sufficiency = row.get("input_sufficiency")
        if (
            not isinstance(input_sufficiency, Mapping)
            or input_sufficiency.get("all_arms_sufficient") is not True
        ):
            reasons.append("input_insufficient")
        flags = row.get("variant_flags", {})
        if not isinstance(flags, Mapping):
            reasons.append("missing_variant_flags")
        elif not all(
            flags.get(name) is True
            for name in (
                "request_only_diff",
                "semantic_only_diff",
                "future_contract_only_diff",
            )
        ):
            reasons.append("variant_isolation")
        arms = row.get("arms")
        if not isinstance(arms, Mapping) or set(arms) != set(ARM_ORDER):
            reasons.append("missing_arm_population")
            continue
        for arm in ARM_ORDER:
            value = arms[arm]
            if not isinstance(value, Mapping) or value.get("structured_valid") is not True:
                reasons.append(f"{arm}_not_evaluation_eligible")
    return {
        "complete": not reasons,
        "expected_rows": 15,
        "actual_rows": len(rows),
        "expected_cases": list(REPRESENTATION_CASES),
        "reasons": sorted(set(reasons)),
    }


def _pairwise_counts(
    rows: Sequence[Mapping[str, object]],
    left: str,
    right: str,
) -> dict[str, dict[str, int]]:
    """Compare scientific leaf statuses for two arms."""
    result: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "both_pass": 0,
            "left_fail_right_pass": 0,
            "left_pass_right_fail": 0,
            "both_fail": 0,
        }
    )
    for row in rows:
        arms = row.get("arms", {})
        if not isinstance(arms, Mapping):
            continue
        left_value = arms.get(left, {})
        right_value = arms.get(right, {})
        if not isinstance(left_value, Mapping) or not isinstance(right_value, Mapping):
            continue
        left_statuses = left_value.get("leaf_statuses", {})
        right_statuses = right_value.get("leaf_statuses", {})
        if not isinstance(left_statuses, Mapping) or not isinstance(right_statuses, Mapping):
            continue
        for path in sorted(set(left_statuses) & set(right_statuses)):
            if _family(str(path)) is None:
                continue
            left_pass = left_statuses[path] == "PASS"
            right_pass = right_statuses[path] == "PASS"
            bucket = result[str(path)]
            if left_pass and right_pass:
                bucket["both_pass"] += 1
            elif not left_pass and right_pass:
                bucket["left_fail_right_pass"] += 1
            elif left_pass and not right_pass:
                bucket["left_pass_right_fail"] += 1
            else:
                bucket["both_fail"] += 1
    return dict(sorted(result.items()))


def _factor_classification(pairwise: Mapping[str, Mapping[str, int]]) -> str:
    """Classify one factor from exact leaf-level changes."""
    recoveries = sum(value["left_fail_right_pass"] for value in pairwise.values())
    regressions = sum(value["left_pass_right_fail"] for value in pairwise.values())
    if regressions and recoveries:
        return "REQUEST_MIXED_EFFECT"
    if regressions:
        return "REQUEST_REGRESSION"
    if recoveries:
        return "REQUEST_CONTRIBUTES"
    return "REQUEST_NO_MEASURABLE_EFFECT"


def _classify_metadata(pairwise: Mapping[str, Mapping[str, int]]) -> str:
    """Classify metadata contribution independently of request contribution."""
    recoveries = sum(value["left_fail_right_pass"] for value in pairwise.values())
    regressions = sum(value["left_pass_right_fail"] for value in pairwise.values())
    if regressions and recoveries:
        return "METADATA_MIXED_EFFECT"
    if regressions:
        return "METADATA_REGRESSION"
    if recoveries:
        return "METADATA_CONTRIBUTES"
    return "METADATA_NO_MEASURABLE_EFFECT"


def aggregate_rows(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate factorial evidence with protected-scale regression dominance."""
    population = _population_integrity(rows)
    comparisons = {
        f"{left}_to_{right}": _pairwise_counts(rows, left, right)
        for left, right in (("P", "R"), ("P", "S"), ("R", "RS"), ("S", "RS"))
    }
    p_to_rs = _pairwise_counts(rows, "P", "RS")
    r_to_rs = _pairwise_counts(rows, "R", "RS")
    protected_families = {"track_scale", "binding_scale"}
    protected_regressions = sum(
        bucket["left_pass_right_fail"]
        for comparison in (r_to_rs, p_to_rs)
        for path, bucket in comparison.items()
        if _family(path) in protected_families
    )
    target_recoveries = sum(
        bucket["left_fail_right_pass"]
        for path, bucket in p_to_rs.items()
        if _family(path) in {"raster_profile", "sample_axis"}
    )
    rs_values = [
        row["arms"]["RS"]
        for row in rows
        if isinstance(row.get("arms"), Mapping) and isinstance(row["arms"].get("RS"), Mapping)
    ]
    rs_target_statuses = [
        status
        for value in rs_values
        for path, status in value.get("leaf_statuses", {}).items()
        if _family(str(path)) in {"raster_profile", "sample_axis"}
    ]
    rs_target_complete = bool(rs_target_statuses) and all(
        status == "PASS" for status in rs_target_statuses
    )
    rs_extras = sum(
        status == "UNREQUESTED_EXTRA"
        for value in rs_values
        for path, status in value.get("leaf_statuses", {}).items()
        if _family(str(path)) in {"track_scale", "binding_scale", "raster_profile", "sample_axis"}
    )
    if not population["complete"]:
        decision = "INCONCLUSIVE_INPUT_BOUNDARY"
    elif protected_regressions:
        decision = "FUTURE_TYPED_INPUT_REGRESSION"
    elif rs_target_complete and rs_extras == 0:
        decision = "FUTURE_TYPED_INPUT_VALIDATED"
    else:
        decision = "FUTURE_TYPED_INPUT_PARTIAL"
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "population_integrity": population,
        "arms": {arm: _variant_counts(rows, arm) for arm in ARM_ORDER},
        "comparisons": comparisons,
        "request_contribution": _factor_classification(comparisons["P_to_R"]),
        "metadata_contribution": _classify_metadata(comparisons["P_to_S"]),
        "protected_scale_regressions": protected_regressions,
        "target_recoveries": target_recoveries,
        "rs_target_complete": rs_target_complete,
        "rs_unrequested_scientific_extras": rs_extras,
        "decision": decision,
    }


def build_evidence_row(
    *,
    case_id: str,
    attempt_index: int,
    model: str,
    authorized_checkpoint: str,
    artifact_metadata: Mapping[str, object],
    request: str,
    selected_capability_ids: Sequence[str],
    selected_source_ids: Sequence[str],
    inputs: Mapping[str, str],
    prompts: Mapping[str, str],
    input_sufficiency: Mapping[str, object],
    flags: Mapping[str, object],
    arms: Mapping[str, Mapping[str, object]],
    elapsed_ms: float,
) -> dict[str, object]:
    """Build one bounded row without retaining raw request or provider payloads."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": DESIGN_BASELINE_SHA,
        "authorized_checkpoint": validate_authorized_checkpoint(authorized_checkpoint),
        "harness_source_sha256": harness_source_sha256(),
        "case_corpus_sha256": CASE_CORPUS_SHA256,
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_source_sha256": EVALUATOR_SHA256,
        "evaluation_contract_sha256": EVALUATION_CONTRACT_SHA256,
        "production_metadata_projection_sha256": artifact_metadata[
            "production_metadata_projection_sha256"
        ],
        "execution_controls": {
            "model": model,
            "planner_temperature": PLANNER_TEMPERATURE,
            "worker_temperature": WORKER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
            "attempts_per_case": ATTEMPTS,
        },
        "case_id": case_id,
        "attempt_index": attempt_index,
        "arm_order": list(ARM_ORDER),
        "request_sha256": _sha256(_safe_text(request)),
        "selected_capability_ids": list(selected_capability_ids),
        "selected_source_ids": list(selected_source_ids),
        "metadata_source": (
            "CapabilitySpec.semantic_metadata"
            if flags.get("semantic_contract_applicable")
            else None
        ),
        "input_hashes": {arm: _sha256(value) for arm, value in inputs.items()},
        "input_chars": {arm: len(value) for arm, value in inputs.items()},
        "prompt_sha256": {arm: _sha256(value) for arm, value in prompts.items()},
        "input_sufficiency": dict(input_sufficiency),
        "variant_flags": dict(flags),
        "arms": {arm: dict(arms[arm]) for arm in ARM_ORDER},
        "elapsed_ms": elapsed_ms,
    }


async def run_attempt(
    case: Mapping[str, object],
    *,
    backend: ModelBackendProtocol,
    planner: SemanticPlanner,
    registry: CapabilityRegistry,
    artifact_metadata: Mapping[str, object],
    evaluation_contract: Mapping[str, object],
    evaluation_contract_sha256: str,
    model: str,
    authorized_checkpoint: str,
    attempt_index: int,
) -> dict[str, object]:
    """Share one planner/enrichment result across four independent worker calls."""
    del evaluation_contract_sha256
    started = time.perf_counter()
    request = _case_request(case)
    document = _document()
    try:
        plan = await planner.plan(
            request=request,
            mode="reconstruct",
            current_document_summary=AuthoringInspectionFacade(document)
            .document_summary()
            .model_dump(mode="json"),
            source_summary=production_source_summary(case),
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        enriched = build_fixture_enricher(case).enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except (PlannerSemanticFailure, ProviderRequestError, SemanticEnrichmentError) as error:
        return {
            "experiment_version": EXPERIMENT_VERSION,
            "case_id": case["case_id"],
            "attempt_index": attempt_index,
            "classification": "PLANNER_OR_ENRICHMENT_FAILURE",
            "error_type": type(error).__name__,
            "provider_category": getattr(getattr(error, "category", None), "value", None),
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }

    selected = _select_case_section(str(case["case_id"]), plan, enriched)
    if selected is None:
        return {
            "experiment_version": EXPERIMENT_VERSION,
            "case_id": case["case_id"],
            "attempt_index": attempt_index,
            "classification": "PLANNER_SECTION_SELECTION_FAILURE",
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    task, section_context = selected
    base_input = serialize_typed_section_input(
        build_typed_section_input(task, section_context=section_context, registry=registry)
    )
    contracts = select_production_semantic_metadata(task.capability_ids, registry)
    inputs = build_arm_inputs(base_input, request=request, contracts=contracts)
    prompts = build_arm_prompts(semantic_applicable=bool(contracts))
    flags = arm_isolation_flags(inputs)
    sufficiency: dict[str, object] = {}
    for arm in ARM_ORDER:
        audit = audit_input_sufficiency(
            case,
            task=task,
            section_context=section_context,
            serialized_input=inputs[arm],
        )
        sufficiency[arm] = {
            "sufficient": audit.sufficient,
            "facts": audit.facts,
            "missing_fact_ids": audit.missing_fact_ids,
        }
    sufficiency["all_arms_sufficient"] = all(sufficiency[arm]["sufficient"] for arm in ARM_ORDER)
    expected = corrected_expected_for_case(case, evaluation_contract)
    arms: dict[str, Mapping[str, object]] = {}
    for arm in ARM_ORDER:
        arms[arm] = await _generate_corrected_variant(
            backend,
            serialized_input=inputs[arm],
            system_prompt=prompts[arm],
            section_context=section_context,
            document=document,
            expected=expected,
            timeout_seconds=TIMEOUT_SECONDS,
        )
    row = build_evidence_row(
        case_id=str(case["case_id"]),
        attempt_index=attempt_index,
        model=model,
        authorized_checkpoint=authorized_checkpoint,
        artifact_metadata=artifact_metadata,
        request=request,
        selected_capability_ids=task.capability_ids,
        selected_source_ids=tuple(source.candidate_id for source in section_context.sources),
        inputs=inputs,
        prompts=prompts,
        input_sufficiency=sufficiency,
        flags=flags,
        arms=arms,
        elapsed_ms=(time.perf_counter() - started) * 1000,
    )
    row["semantic_metadata_projection_sha256"] = (
        semantic_metadata_projection_sha256(contracts) if contracts else None
    )
    return row


def _validate_live_configuration(
    args: argparse.Namespace,
) -> tuple[CapabilityRegistry, dict[str, object]]:
    """Validate all drift and control guards before constructing a provider."""
    validate_frozen_execution_controls(args)
    validate_authorized_checkpoint(args.authorized_checkpoint)
    if not args.base_url:
        raise ValueError("CM-57IB live execution requires --base-url.")
    ensure_empty_evidence_path(args.output_jsonl)
    registry = create_builtin_registry()
    artifacts = validate_frozen_artifacts(registry)
    return registry, artifacts


async def run_matrix(args: argparse.Namespace) -> None:
    """Run the future 15-row, 60-worker-call matrix after explicit authorization."""
    registry, artifacts = _validate_live_configuration(args)
    from scripts.cm56_typed_section_shadow import _provider_configuration

    backend_args = argparse.Namespace(
        model=FROZEN_MODEL,
        base_url=args.base_url,
        api_key_file=args.api_key_file,
        api_key_env=args.api_key_env,
        timeout=TIMEOUT_SECONDS,
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )
    backend = _provider_configuration(backend_args)
    evaluation_contract, evaluation_sha = load_evaluation_contract(EVALUATION_CONTRACT_PATH)
    cases = [case for case in load_case_definitions() if case["case_id"] in REPRESENTATION_CASES]
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            planner = SemanticPlanner(backend=backend, registry=registry)
            for attempt_index in range(ATTEMPTS):
                row = await run_attempt(
                    case,
                    backend=backend,
                    planner=planner,
                    registry=registry,
                    artifact_metadata=artifacts,
                    evaluation_contract=evaluation_contract,
                    evaluation_contract_sha256=evaluation_sha,
                    model=FROZEN_MODEL,
                    authorized_checkpoint=args.authorized_checkpoint,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build a CLI with frozen controls and explicit future live authorization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--output-jsonl", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--live-authorized", action="store_true")
    return parser


def main() -> None:
    """Print pre-live metadata unless explicit future live authorization is supplied."""
    args = _parser().parse_args()
    if not args.live_authorized:
        print(json.dumps(build_pre_live_metadata(), indent=2, sort_keys=True))
        return
    asyncio.run(run_matrix(args))


if __name__ == "__main__":  # pragma: no cover
    main()

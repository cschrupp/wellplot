"""CM-56R8R-S1 selective semantic-contract harness.

The default command path performs only deterministic pre-live validation. A
future live run requires the explicit ``--live-authorized`` flag and uses the
same frozen provider controls as CM-56R8R.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
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
    AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
    _select_case_section,
    _sha256,
    build_authoritative_worker_input,
)
from scripts.cm56r8r_semantic_contract_correction import (
    EVALUATOR_VERSION,
    FROZEN_MODEL,
    MAX_OUTPUT_TOKENS,
    MAX_TOKENS_PARAMETER,
    PLANNER_TEMPERATURE,
    REPRESENTATION_CASES,
    RESPONSE_SCHEMA_SHA256,
    TIMEOUT_SECONDS,
    WORKER_TEMPERATURE,
    _generate_corrected_variant,
    build_typed_section_input,
    corrected_expected_for_case,
    evaluator_source_sha256,
    load_evaluation_contract,
    select_semantic_contracts,
    serialize_typed_section_input,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import SemanticPlanner
from wellplot.agent.providers.base import ModelBackendProtocol, ProviderRequestError
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

EXPERIMENT_VERSION = "CM-56R8R-S1"
BASELINE_SHA = "7e0233421f8c9c6142d35eaeb29f533a0604667b"
CASE_CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
EVALUATION_CONTRACT_SHA256 = "3e6c3c36d967acb60e6bb7cda13db95d76ed7a754eb92c4bcf5688d76b0da4da"
EVALUATOR_SHA256 = "4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49"
SELECTIVE_CONTRACT_PATH = Path(__file__).resolve().parents[1] / (
    "docs/evaluations/agent-code-mode/CM-56R8R-S1-selective-semantic-contracts.json"
)
EVALUATION_CONTRACT_PATH = Path(__file__).resolve().parents[1] / (
    "docs/evaluations/agent-code-mode/CM-56R8R-evaluation-contract.json"
)
SELECTIVE_CONTRACT_VERSION = "cm56r8r-s1.selective-semantic-contracts.v1"
SELECTIVE_CAPABILITY_IDS = ("binding.raster",)
ATTEMPTS = 3
S1_OUTPUT_PATH = Path("/tmp/cm56r8r-s1-live-qwen.jsonl")

SELECTIVE_CONTRACT_INSTRUCTION = (
    "\n\nSelective semantic-contract use:\n"
    "The selective_semantic_contracts object documents only WellPlot-specific "
    "semantic mappings that require explicit clarification. Use these mappings "
    "where applicable. For concepts not documented by the selective contracts, "
    "interpret the authoritative request using the normal SectionSemanticDraft "
    "schema and existing worker instructions. Do not infer additional semantics "
    "and do not copy example values."
)

_FORBIDDEN_TARGETS = {
    "binding.scale",
    "binding.scale.kind",
    "binding.scale.minimum",
    "binding.scale.maximum",
    "binding.scale.reverse",
    "binding.scale.unit",
    "track.x_scale.kind",
    "track.x_scale.minimum",
    "track.x_scale.maximum",
    "track.x_scale.reverse",
    "track.x_scale.unit",
}
_FORBIDDEN_TEXT = (
    "0 to 150",
    "200 to 0",
    "0 to 200",
    "200 to 1200",
    "-25 to 75",
    "10 to 90",
    "reverse_scale",
    "scalar_linear",
    "expected_semantic_projection",
)


def _sha256_bytes(value: bytes) -> str:
    """Return a SHA-256 digest for exact artifact bytes."""
    return hashlib.sha256(value).hexdigest()


def selective_contract_sha256() -> str:
    """Return the digest of the frozen selective-contract artifact."""
    return _sha256_bytes(SELECTIVE_CONTRACT_PATH.read_bytes())


def load_selective_contracts(
    path: Path = SELECTIVE_CONTRACT_PATH,
) -> tuple[dict[str, object], str]:
    """Load and validate the minimal selective contract artifact."""
    raw = path.read_bytes()
    artifact = json.loads(raw)
    if artifact.get("version") != SELECTIVE_CONTRACT_VERSION:
        raise ValueError("Unexpected CM-56R8R-S1 contract version.")
    contracts = artifact.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("Selective contract artifact must contain contracts.")
    capability_ids = {contract.get("capability_id") for contract in contracts}
    if capability_ids != set(SELECTIVE_CAPABILITY_IDS):
        raise ValueError(f"Unexpected selective capabilities: {capability_ids}")
    validate_selective_contract_artifact(artifact)
    return artifact, _sha256_bytes(raw)


def _mapping_targets(artifact: Mapping[str, object]) -> list[str]:
    """Return all declarative mapping target paths."""
    targets: list[str] = []
    for contract in artifact.get("contracts", ()):
        for mapping in contract.get("mappings", ()):
            targets.extend(str(path) for path in mapping.get("targets", {}))
    return targets


def validate_selective_contract_artifact(artifact: Mapping[str, object]) -> None:
    """Reject scale mappings and benchmark leakage in the selective artifact."""
    targets = _mapping_targets(artifact)
    forbidden = sorted(set(targets) & _FORBIDDEN_TARGETS)
    if forbidden:
        raise ValueError(f"Forbidden selective-contract targets: {forbidden}")
    if any(target.startswith("binding.scale") for target in targets):
        raise ValueError("Selective contract must not map binding.scale.")
    serialized = json.dumps(artifact, sort_keys=True)
    leaked = [text for text in _FORBIDDEN_TEXT if text in serialized]
    if leaked:
        raise ValueError(f"Benchmark text leaked into selective contract: {leaked}")


def build_selective_worker_input(
    authoritative_input: str,
    *,
    contracts: Sequence[Mapping[str, object]],
) -> str:
    """Add only the selective contract field to the authoritative payload."""
    payload = json.loads(authoritative_input)
    if not isinstance(payload, dict):
        raise ValueError("Authoritative typed input must serialize to an object.")
    payload["selective_semantic_contracts"] = list(contracts)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def selective_contract_only_differs(authoritative_input: str, selective_input: str) -> bool:
    """Verify S is exactly A plus one selective-contract field."""
    left = json.loads(authoritative_input)
    right = json.loads(selective_input)
    contracts = right.pop("selective_semantic_contracts", None)
    return isinstance(contracts, list) and left == right


def build_selective_system_prompt() -> str:
    """Return the exact A prompt plus the bounded S instruction."""
    return AUTHORITATIVE_REQUEST_SYSTEM_PROMPT + SELECTIVE_CONTRACT_INSTRUCTION


def validate_frozen_execution_controls(args: argparse.Namespace) -> None:
    """Reject any future live invocation that changes frozen controls."""
    actual = {
        "model": getattr(args, "model", None),
        "planner_temperature": getattr(args, "planner_temperature", PLANNER_TEMPERATURE),
        "worker_temperature": getattr(args, "worker_temperature", WORKER_TEMPERATURE),
        "max_output_tokens": getattr(args, "max_output_tokens", MAX_OUTPUT_TOKENS),
        "max_tokens_parameter": getattr(
            args,
            "max_tokens_parameter",
            MAX_TOKENS_PARAMETER,
        ),
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
        raise ValueError(f"CM-56R8R-S1 frozen controls rejected: {mismatches}")


def ensure_empty_evidence_path(path: Path = S1_OUTPUT_PATH) -> None:
    """Reject an existing non-empty S1 evidence file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        raise FileExistsError(f"Refusing to append to non-empty S1 evidence file: {path}")


def _family(path: str) -> str | None:
    """Map an evaluator leaf path to an S1 scientific family."""
    if ".x_scale." in path:
        return "track_scale"
    if ".scale." in path:
        return "binding_scale"
    if path.endswith(".profile"):
        return "raster_profile"
    if ".sample_axis." in path:
        return "sample_axis"
    return None


def _expected_family_inventory() -> dict[str, list[str]]:
    """Derive applicable scientific families from the frozen evaluator inputs."""
    evaluation_contract, _ = load_evaluation_contract(EVALUATION_CONTRACT_PATH)
    inventory: dict[str, list[str]] = {}
    for case in load_case_definitions():
        case_id = str(case["case_id"])
        if case_id not in REPRESENTATION_CASES:
            continue
        expected = corrected_expected_for_case(case, evaluation_contract)
        paths: set[str] = set()
        for track_index, track in enumerate(expected["tracks"]):
            prefix = f"tracks[{track_index}]"
            if "x_scale" in track:
                paths.update(f"{prefix}.x_scale.{field}" for field in track["x_scale"])
            for binding_index, binding in enumerate(track["bindings"]):
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


def build_pre_live_metadata() -> dict[str, object]:
    """Build deterministic metadata without provider calls."""
    artifact, contract_sha256 = load_selective_contracts()
    evaluation_contract, evaluation_sha256 = load_evaluation_contract(EVALUATION_CONTRACT_PATH)
    if evaluator_source_sha256() != EVALUATOR_SHA256:
        raise ValueError("Frozen evaluator source hash changed.")
    if evaluation_sha256 != EVALUATION_CONTRACT_SHA256:
        raise ValueError("Frozen evaluation-contract hash changed.")
    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise ValueError("Frozen case-corpus hash changed.")
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_checkpoint": BASELINE_SHA,
        "provider_calls": 0,
        "production_changes": 0,
        "selective_contract_version": artifact["version"],
        "selective_contract_sha256": contract_sha256,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_source_sha256": evaluator_source_sha256(),
        "evaluation_contract_sha256": evaluation_sha256,
        "expected_family_inventory": _expected_family_inventory(),
        "frozen_controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "worker_temperature": WORKER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
            "attempts_per_case": ATTEMPTS,
        },
        "corpus_sha256": case_corpus_sha256(),
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "evaluation_contract_loaded": bool(evaluation_contract),
        "future_population": {
            "cases": list(REPRESENTATION_CASES),
            "paired_rows": 15,
            "worker_calls": 30,
        },
    }


def _population_integrity(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Fail closed unless rows form the complete paired S1 population."""
    expected_keys = {
        (case_id, attempt) for case_id in REPRESENTATION_CASES for attempt in range(ATTEMPTS)
    }
    actual_keys = [(row.get("case_id"), row.get("attempt_index")) for row in rows]
    reasons: list[str] = []
    if len(rows) != 15:
        reasons.append("row_count")
    if set(actual_keys) != expected_keys:
        reasons.append("missing_or_unexpected_case_attempt")
    if len(actual_keys) != len(set(actual_keys)):
        reasons.append("duplicate_case_attempt")
    for row in rows:
        input_sufficiency = row.get("input_sufficiency")
        if (
            not isinstance(input_sufficiency, Mapping)
            or input_sufficiency.get("sufficient") is not True
        ):
            reasons.append("input_insufficient")
        if row.get("selective_contract_only_diff") is not True:
            reasons.append("selective_contract_diff")
        a = row.get("a")
        s = row.get("s")
        if not isinstance(a, Mapping) or a.get("structured_valid") is not True:
            reasons.append("a_not_evaluation_eligible")
        if not isinstance(s, Mapping) or s.get("structured_valid") is not True:
            reasons.append("s_not_evaluation_eligible")
        for variant in ("a", "s"):
            value = row.get(variant, {})
            if (
                not isinstance(value, Mapping)
                or not value.get("context_valid")
                or not value.get("compiler_valid")
            ):
                reasons.append(f"{variant}_not_evaluation_eligible")
    return {
        "complete": not reasons,
        "expected_rows": 15,
        "actual_rows": len(rows),
        "reasons": sorted(set(reasons)),
    }


def _variant_counts(rows: Sequence[Mapping[str, object]], variant: str) -> dict[str, object]:
    """Aggregate full acceptance and scientific leaves for one arm."""
    eligible = [row[variant] for row in rows if row.get(variant, {}).get("compiler_valid")]
    families: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "applicable": 0})
    accepted = sum(bool(value.get("semantic_accepted")) for value in eligible)
    for value in eligible:
        for path, status in value.get("leaf_statuses", {}).items():
            family = _family(path)
            if family is None:
                continue
            families[family]["applicable"] += 1
            families[family]["pass"] += status == "PASS"
    return {
        "evaluation_eligible": len(eligible),
        "full_semantic_acceptance": f"{accepted}/{len(eligible)}",
        "families": {
            family: {
                **counts,
                "fail": counts["applicable"] - counts["pass"],
            }
            for family, counts in sorted(families.items())
        },
    }


def aggregate_s1_rows(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate S1 rows and apply exact, regression-dominant decisions."""
    population = _population_integrity(rows)
    pairwise: dict[str, dict[str, int]] = defaultdict(
        lambda: {"both_pass": 0, "a_fail_s_pass": 0, "a_pass_s_fail": 0, "both_fail": 0}
    )
    scale_regressions = 0
    target_recoveries = 0
    selective_extras = 0
    for row in rows:
        a = row.get("a", {})
        s = row.get("s", {})
        a_statuses = dict(a.get("leaf_statuses", {}))
        s_statuses = dict(s.get("leaf_statuses", {}))
        selective_extras += sum(
            status == "UNREQUESTED_EXTRA"
            for path, status in s_statuses.items()
            if _family(path) is not None
        )
        for path in sorted(set(a_statuses) & set(s_statuses)):
            family = _family(path)
            if family is None:
                continue
            a_pass = a_statuses[path] == "PASS"
            s_pass = s_statuses[path] == "PASS"
            bucket = pairwise[path]
            if a_pass and s_pass:
                bucket["both_pass"] += 1
            elif not a_pass and s_pass:
                bucket["a_fail_s_pass"] += 1
                if family in {"raster_profile", "sample_axis"}:
                    target_recoveries += 1
            elif a_pass and not s_pass:
                bucket["a_pass_s_fail"] += 1
                if family in {"track_scale", "binding_scale"}:
                    scale_regressions += 1
            else:
                bucket["both_fail"] += 1

    if not population["complete"]:
        decision = "INCONCLUSIVE_SELECTIVE_CONTRACT"
    elif scale_regressions:
        decision = "SELECTIVE_CONTRACT_REGRESSION"
    elif target_recoveries:
        profile_fail = any(
            bucket["a_pass_s_fail"] + bucket["both_fail"]
            for path, bucket in pairwise.items()
            if _family(path) == "raster_profile"
        )
        sample_fail = any(
            bucket["a_pass_s_fail"] + bucket["both_fail"]
            for path, bucket in pairwise.items()
            if _family(path) == "sample_axis"
        )
        decision = (
            "SELECTIVE_CONTRACT_FULL_RECOVERY"
            if not profile_fail and not sample_fail and selective_extras == 0
            else "SELECTIVE_CONTRACT_PARTIAL_RECOVERY"
        )
    else:
        decision = "SELECTIVE_CONTRACT_NO_BENEFIT"

    return {
        "experiment_version": EXPERIMENT_VERSION,
        "population_integrity": population,
        "A": _variant_counts(rows, "a"),
        "S": _variant_counts(rows, "s"),
        "pairwise_scientific_leaves": dict(sorted(pairwise.items())),
        "scale_regressions": scale_regressions,
        "target_recoveries": target_recoveries,
        "selective_unrequested_scientific_extras": selective_extras,
        "decision": decision,
    }


async def run_s1_attempt(
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
    attempt_index: int,
) -> dict[str, object]:
    """Run one shared planner/enrichment result through independent A/S calls."""
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
    except (ProviderRequestError, SemanticEnrichmentError) as error:
        return {
            "experiment_version": EXPERIMENT_VERSION,
            "case_id": case["case_id"],
            "attempt_index": attempt_index,
            "classification": "PLANNER_OR_ENRICHMENT_FAILURE",
            "error_type": type(error).__name__,
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
    typed_input = build_typed_section_input(
        task,
        section_context=section_context,
        registry=registry,
    )
    base_input = serialize_typed_section_input(typed_input)
    authoritative_input = build_authoritative_worker_input(base_input, request)
    selected_contracts = select_semantic_contracts(task.capability_ids, contracts_artifact)
    selective_input = build_selective_worker_input(
        authoritative_input,
        contracts=selected_contracts,
    )
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
        timeout_seconds=TIMEOUT_SECONDS,
    )
    result_s = await _generate_corrected_variant(
        backend,
        serialized_input=selective_input,
        system_prompt=build_selective_system_prompt(),
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_checkpoint": BASELINE_SHA,
        "harness_source_sha256": _sha256(Path(__file__).read_bytes()),
        "selective_contract_sha256": contract_sha256,
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_source_sha256": evaluator_source_sha256(),
        "evaluation_contract_sha256": evaluation_contract_sha256,
        "case_corpus_sha256": case_corpus_sha256(),
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "execution_controls": {
            "model": model,
            "planner_temperature": PLANNER_TEMPERATURE,
            "worker_temperature": WORKER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
            "attempts_per_case": ATTEMPTS,
        },
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "a_system_prompt_sha256": _sha256(AUTHORITATIVE_REQUEST_SYSTEM_PROMPT),
        "s_system_prompt_sha256": _sha256(build_selective_system_prompt()),
        "authoritative_input_sha256": _sha256(authoritative_input),
        "selective_input_sha256": _sha256(selective_input),
        "selective_contract_only_diff": selective_contract_only_differs(
            authoritative_input,
            selective_input,
        ),
        "input_sufficiency": {
            "sufficient": audit.sufficient,
            "facts": audit.facts,
            "missing_fact_ids": audit.missing_fact_ids,
        },
        "a": result_a,
        "s": result_s,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


async def run_matrix(args: argparse.Namespace) -> None:
    """Run the future S1 matrix with frozen controls and flushed rows."""
    from scripts.cm56_typed_section_shadow import _provider_configuration

    validate_frozen_execution_controls(args)
    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise RuntimeError("CM-56 corpus hash changed from the frozen baseline.")
    ensure_empty_evidence_path(args.output_jsonl)
    contracts_artifact, contract_sha256 = load_selective_contracts()
    evaluation_contract, evaluation_contract_sha256 = load_evaluation_contract(
        EVALUATION_CONTRACT_PATH
    )
    if evaluator_source_sha256() != EVALUATOR_SHA256:
        raise ValueError("Frozen evaluator source hash changed.")
    if evaluation_contract_sha256 != EVALUATION_CONTRACT_SHA256:
        raise ValueError("Frozen evaluation-contract hash changed.")
    provider_values = vars(args).copy()
    provider_values.update(
        timeout=TIMEOUT_SECONDS,
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )
    backend = _provider_configuration(argparse.Namespace(**provider_values))
    registry = create_builtin_registry()
    cases = [case for case in load_case_definitions() if case["case_id"] in REPRESENTATION_CASES]
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            planner = SemanticPlanner(backend=backend, registry=registry)
            for attempt_index in range(ATTEMPTS):
                row = await run_s1_attempt(
                    case,
                    backend=backend,
                    model=args.model,
                    planner=planner,
                    registry=registry,
                    contracts_artifact=contracts_artifact,
                    contract_sha256=contract_sha256,
                    evaluation_contract=evaluation_contract,
                    evaluation_contract_sha256=evaluation_contract_sha256,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build the future S1 CLI without mutable control options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--output-jsonl", type=Path, default=S1_OUTPUT_PATH)
    parser.add_argument("--live-authorized", action="store_true")
    return parser


def main() -> None:
    """Perform pre-live checks unless an explicit future live flag is supplied."""
    args = _parser().parse_args()
    if not args.live_authorized:
        print(json.dumps(build_pre_live_metadata(), indent=2, sort_keys=True))
        return
    asyncio.run(run_matrix(args))


if __name__ == "__main__":  # pragma: no cover
    main()

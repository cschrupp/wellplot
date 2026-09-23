"""CM-56R8 capability-local semantic contract diagnostic harness."""

from __future__ import annotations

import argparse
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
    generate_authoritative_variant,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import SemanticPlanner
from wellplot.agent.code_mode.typed_section_worker import (
    RESPONSE_SCHEMA_SHA256,
    build_typed_section_input,
    serialize_typed_section_input,
)
from wellplot.agent.providers.base import ModelBackendProtocol, ProviderRequestError
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

EXPERIMENT_VERSION = "CM-56R8"
BASELINE_SHA = "a8acbf1"
CASE_CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
CONTRACT_PATH = Path(__file__).resolve().parents[1] / (
    "docs/evaluations/agent-code-mode/CM-56R8-semantic-contracts.json"
)
PLANNER_TEMPERATURE = 0.0
WORKER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 3
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


def _canonical_json(value: object) -> str:
    """Serialize JSON-shaped contract/input data deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: object) -> str:
    """Hash one deterministic JSON-shaped value."""
    return _sha256(_canonical_json(value))


def load_semantic_contracts(path: Path = CONTRACT_PATH) -> tuple[dict[str, object], str]:
    """Load and hash the frozen evaluation-only contract artifact."""
    raw = path.read_bytes()
    artifact = json.loads(raw)
    contracts = artifact.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("CM-56R8 contract artifact must contain contracts.")
    return artifact, hashlib.sha256(raw).hexdigest()


def select_semantic_contracts(
    capability_ids: tuple[str, ...],
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
    contracts: tuple[dict[str, object], ...],
) -> str:
    """Add only the selected semantic contracts to the authoritative payload."""
    payload = json.loads(authoritative_input)
    if not isinstance(payload, dict):
        raise ValueError("Authoritative typed input must serialize to an object.")
    payload["semantic_contracts"] = contracts
    return _canonical_json(payload)


def semantic_contract_only_differs(variant_a: str, variant_b: str) -> bool:
    """Verify B is exactly A plus semantic_contracts."""
    left = json.loads(variant_a)
    right = json.loads(variant_b)
    contracts = right.pop("semantic_contracts", None)
    return isinstance(contracts, list) and left == right


def build_contract_system_prompt() -> str:
    """Return the bounded B prompt addition without duplicating contract content."""
    return AUTHORITATIVE_REQUEST_SYSTEM_PROMPT + CONTRACT_INSTRUCTION


def _expected_for_case(case: Mapping[str, object]) -> Mapping[str, object]:
    """Read expected output only for post-generation evaluation."""
    expected_sections = list(case.get("expected_sections", ()))
    return expected_sections[0] if expected_sections else {}


async def run_contract_attempt(
    case: Mapping[str, object],
    *,
    backend: ModelBackendProtocol,
    planner: SemanticPlanner,
    registry: CapabilityRegistry,
    artifact: Mapping[str, object],
    contract_sha256: str,
    timeout_seconds: float,
    attempt_index: int,
) -> dict[str, object]:
    """Run one shared planner/enrichment result through A and B."""
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
            "experiment_version": EXPERIMENT_VERSION,
            "baseline_sha": BASELINE_SHA,
            "case_id": case["case_id"],
            "attempt_index": attempt_index,
            "classification": "PLANNER_OR_ENRICHMENT_FAILURE",
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "provider_category": getattr(getattr(error, "category", None), "value", None),
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }

    selected = _select_case_section(str(case["case_id"]), plan, enriched)
    if selected is None:
        return {
            "experiment_version": EXPERIMENT_VERSION,
            "baseline_sha": BASELINE_SHA,
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
    contracts = select_semantic_contracts(task.capability_ids, artifact)
    contract_input = build_contract_worker_input(authoritative_input, contracts=contracts)
    audit = audit_input_sufficiency(
        case,
        task=task,
        section_context=section_context,
        serialized_input=authoritative_input,
    )
    expected = _expected_for_case(case)
    result_a = await generate_authoritative_variant(
        backend,
        serialized_input=authoritative_input,
        system_prompt=AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    result_b = await generate_authoritative_variant(
        backend,
        serialized_input=contract_input,
        system_prompt=build_contract_system_prompt(),
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "classification": "PAIRED_TYPED_ATTEMPT",
        "planner_temperature": PLANNER_TEMPERATURE,
        "worker_temperature": WORKER_TEMPERATURE,
        "natural_request_sha256": _sha256(request),
        "case_corpus_sha256": case_corpus_sha256(),
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "a_system_prompt_sha256": _sha256(AUTHORITATIVE_REQUEST_SYSTEM_PROMPT),
        "b_system_prompt_sha256": _sha256(build_contract_system_prompt()),
        "semantic_contract_sha256": contract_sha256,
        "selected_capability_ids": list(task.capability_ids),
        "selected_contract_capability_ids": [
            str(contract["capability_id"]) for contract in contracts
        ],
        "authoritative_input_sha256": _sha256(authoritative_input),
        "authoritative_input_chars": len(authoritative_input),
        "contract_input_sha256": _sha256(contract_input),
        "contract_input_chars": len(contract_input),
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


def _scientific_checks(expected: Mapping[str, object]) -> tuple[str, ...]:
    """Return applicable scientific paths using the frozen evaluator vocabulary."""
    from scripts.cm56r7_semantic_failure_decomposition import applicable_checks, check_family

    return tuple(
        check
        for check in applicable_checks(expected)
        if check_family(check) in {"track_scale", "binding_scale", "raster_profile", "sample_axis"}
    )


def aggregate_contract_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    expected_by_case: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Aggregate R8 rows without changing the frozen evaluator semantics."""
    from scripts.cm56r7_semantic_failure_decomposition import _rate

    result: dict[str, object] = {}
    pairwise = defaultdict(
        lambda: {
            "both_pass": 0,
            "a_fail_b_pass": 0,
            "a_pass_b_fail": 0,
            "both_fail": 0,
        }
    )
    for variant in ("a", "b"):
        eligible = [
            row
            for row in rows
            if isinstance(row.get(variant), Mapping)
            and all(
                row[variant].get(field)
                for field in ("structured_valid", "context_valid", "compiler_valid")
            )
        ]
        scientific_pass_rows = 0
        accepted = 0
        check_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in eligible:
            output = row[variant]
            assert isinstance(output, Mapping)
            if output.get("semantic_accepted"):
                accepted += 1
            omissions = set(output.get("omissions", ()))
            scientific = _scientific_checks(expected_by_case[str(row["case_id"])])
            if all(check not in omissions for check in scientific):
                scientific_pass_rows += 1
            for check in scientific:
                check_counts[check][0] += 1
                check_counts[check][1] += check not in omissions
        result[variant.upper()] = {
            "rows": len(rows),
            "evaluation_eligible": len(eligible),
            "scientific_only_pass": _rate(scientific_pass_rows, len(eligible)),
            "semantic_accepted": _rate(accepted, len(eligible)),
            "scientific_checks": {
                check: {
                    "pass": _rate(passed, applicable),
                    "fail": _rate(applicable - passed, applicable),
                }
                for check, (applicable, passed) in sorted(check_counts.items())
            },
        }
    for row in rows:
        a = row.get("a")
        b = row.get("b")
        if not isinstance(a, Mapping) or not isinstance(b, Mapping):
            continue
        if not all(
            a.get(field) and b.get(field)
            for field in ("structured_valid", "context_valid", "compiler_valid")
        ):
            continue
        omissions_a = set(a.get("omissions", ()))
        omissions_b = set(b.get("omissions", ()))
        for check in _scientific_checks(expected_by_case[str(row["case_id"])]):
            a_pass = check not in omissions_a
            b_pass = check not in omissions_b
            bucket = pairwise[check]
            if a_pass and b_pass:
                bucket["both_pass"] += 1
            elif not a_pass and b_pass:
                bucket["a_fail_b_pass"] += 1
            elif a_pass and not b_pass:
                bucket["a_pass_b_fail"] += 1
            else:
                bucket["both_fail"] += 1
    recoveries = sum(bucket["a_fail_b_pass"] for bucket in pairwise.values())
    regressions = sum(bucket["a_pass_b_fail"] for bucket in pairwise.values())
    b_scientific_pass = result["B"]["scientific_only_pass"]["numerator"]
    if not rows:
        decision = "INCONCLUSIVE_SEMANTIC_CONTRACT"
    elif recoveries == 0:
        decision = "SEMANTIC_CONTRACT_NO_RECOVERY"
    elif b_scientific_pass:
        decision = (
            "SEMANTIC_CONTRACT_FULL_RECOVERY"
            if regressions == 0 and b_scientific_pass == result["B"]["evaluation_eligible"]
            else "SEMANTIC_CONTRACT_PARTIAL_RECOVERY"
        )
    else:
        decision = "SEMANTIC_CONTRACT_FIELD_RECOVERY_ONLY"
    result["pairwise_scientific_checks"] = dict(sorted(pairwise.items()))
    result["scientific_recoveries"] = recoveries
    result["scientific_regressions"] = regressions
    result["decision"] = decision
    return result


async def run_matrix(args: argparse.Namespace) -> None:
    """Run the authorized 15-pair matrix when explicitly invoked."""
    from scripts.cm56_typed_section_shadow import _provider_configuration

    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise RuntimeError("CM-56 corpus hash changed from the frozen baseline.")
    artifact, contract_sha256 = load_semantic_contracts()
    backend = _provider_configuration(args)
    registry = create_builtin_registry()
    cases = [case for case in load_case_definitions() if case["case_id"] in REPRESENTATION_CASES]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            planner = SemanticPlanner(backend=backend, registry=registry)
            for attempt_index in range(args.attempts):
                row = await run_contract_attempt(
                    case,
                    backend=backend,
                    planner=planner,
                    registry=registry,
                    artifact=artifact,
                    contract_sha256=contract_sha256,
                    timeout_seconds=args.timeout,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build the future live diagnostic CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--max-output-tokens", type=int, default=MAX_OUTPUT_TOKENS)
    parser.add_argument("--max-tokens-parameter", default="max_tokens")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS)
    parser.add_argument("--attempts", type=int, default=ATTEMPTS)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def main() -> None:
    """Run the live R8 matrix only when explicitly invoked after review."""
    import asyncio

    asyncio.run(run_matrix(_parser().parse_args()))


if __name__ == "__main__":  # pragma: no cover
    main()

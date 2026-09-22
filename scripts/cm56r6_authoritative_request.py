"""CM-56R6 authoritative-request and repeated-channel diagnostics."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from collections.abc import Mapping
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
    evaluate_semantic_draft,
    load_case_definitions,
)
from scripts.cm56r2_planner_diagnostic import (
    CountingBackend,
    _provider_category,
    _provider_configuration,
    safe_plan_projection,
)
from scripts.cm56r4_planner_forensics import (
    ForensicCapture,
    _ForensicClient,
    classify_source_plan,
)
from scripts.cm56r5_typed_input_forensics import (
    _select_case_section,
    _sha256,
    _sha256_json,
    _variant_failure,
)
from wellplot.agent.code_mode.enrichment import (
    ResolvedSectionContext,
    SemanticEnrichmentError,
)
from wellplot.agent.code_mode.planner import (
    PlannerSemanticFailure,
    SectionTask,
    SemanticPlanner,
)
from wellplot.agent.code_mode.section_semantics import (
    SectionSemanticDraft,
    SectionSemanticValidationError,
)
from wellplot.agent.code_mode.semantic_section_compiler import (
    SectionSemanticCompilationError,
    compile_section_semantics,
)
from wellplot.agent.code_mode.typed_section_worker import (
    RESPONSE_SCHEMA_SHA256,
    TYPED_SECTION_SYSTEM_PROMPT,
    build_typed_section_input,
    serialize_typed_section_input,
)
from wellplot.agent.providers.base import ModelBackendProtocol, ProviderRequestError
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

EXPERIMENT_VERSION = "CM-56R6"
BASELINE_SHA = "2db8d9f"
CASE_CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
PLANNER_TEMPERATURE = 0.0
WORKER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 3
AUTHORITATIVE_FIELD = "authoritative_original_request"
REPRESENTATION_CASES = (
    "scalar_linear",
    "reverse_scale",
    "generic_raster",
    "waveform",
    "cbl_continuity",
    "vdl_sample_axis",
)
REPEATED_CHANNEL_CASE = "repeated_channel"
REPEATED_CHANNEL_ATTEMPTS = 10

_POSIX_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s\"'<>]+/)+[^\s\"'<>]+")
_WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s\"'<>]+")

AUTHORITATIVE_REQUEST_SYSTEM_PROMPT = (
    TYPED_SECTION_SYSTEM_PROMPT + "\n\nInput authority:\n"
    "The authoritative_original_request field is the authoritative source of "
    "requested scientific semantics. The section task provides routing and scope. "
    "The bounded source/channel context provides available inputs. Preserve every "
    "explicit semantic request from the authoritative original request, but do not "
    "invent semantics absent from it."
)


def build_authoritative_worker_input(serialized_input: str, request: str) -> str:
    """Add only the path-redacted original request to the production payload."""
    payload = json.loads(serialized_input)
    if not isinstance(payload, dict):
        raise ValueError("Typed worker input must serialize to a JSON object.")
    payload[AUTHORITATIVE_FIELD] = _safe_text(request)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def only_authoritative_field_differs(variant_a: str, variant_c: str) -> bool:
    """Verify C is exactly A plus the authoritative request field."""
    left = json.loads(variant_a)
    right = json.loads(variant_c)
    authoritative = right.pop(AUTHORITATIVE_FIELD, None)
    return isinstance(authoritative, str) and left == right


def _safe_text(value: str) -> str:
    """Redact filesystem-shaped text before exposing the request to a provider."""
    return _WINDOWS_PATH_RE.sub("[redacted-path]", _POSIX_PATH_RE.sub("[redacted-path]", value))


async def generate_authoritative_variant(
    backend: ModelBackendProtocol,
    *,
    serialized_input: str,
    system_prompt: str,
    section_context: ResolvedSectionContext,
    document: object,
    expected: Mapping[str, object],
    timeout_seconds: float,
) -> dict[str, object]:
    """Run the unchanged typed validation/compiler/evaluator path once."""
    try:
        generated = await backend.generate_structured(
            request=_generation_request(
                system_prompt=system_prompt,
                user_prompt=serialized_input,
                timeout_seconds=timeout_seconds,
            ),
            response_model=SectionSemanticDraft,
        )
    except ProviderRequestError as error:
        return _variant_failure(
            "structured_output_failure",
            error,
            provider_category=_provider_category(error),
            serialized_input=serialized_input,
        )

    try:
        draft = SectionSemanticDraft.model_validate(generated.value)
    except ValidationError as error:
        return _variant_failure(
            "structured_output_failure",
            error,
            provider_category="validation",
            serialized_input=serialized_input,
            provider_call_completed=True,
        )

    structured = {"provider_call_completed": True, "structured_valid": True}
    try:
        from wellplot.agent.code_mode.section_semantics import validate_section_semantics

        validate_section_semantics(draft, section_context=section_context)
    except SectionSemanticValidationError as error:
        return {
            **structured,
            "context_valid": False,
            "compiler_valid": False,
            "semantic_accepted": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None).value,
            "provider_input_sha256": _sha256(serialized_input),
            "provider_input_chars": len(serialized_input),
            "provider_metrics": generated.metrics.public_metadata(),
        }

    try:
        compile_section_semantics(
            draft,
            section_context=section_context,
            document=document,
            section_id_hint="cm56r6-diagnostic",
        )
    except SectionSemanticCompilationError as error:
        return {
            **structured,
            "context_valid": True,
            "compiler_valid": False,
            "semantic_accepted": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "provider_input_sha256": _sha256(serialized_input),
            "provider_input_chars": len(serialized_input),
            "provider_metrics": generated.metrics.public_metadata(),
        }

    evaluation = evaluate_semantic_draft(draft, expected=expected)
    return {
        **structured,
        "context_valid": True,
        "compiler_valid": True,
        "semantic_accepted": evaluation.accepted,
        "omissions": evaluation.omissions,
        "unrequested_semantics": evaluation.unrequested_semantics,
        "provider_input_sha256": _sha256(serialized_input),
        "provider_input_chars": len(serialized_input),
        "provider_metrics": generated.metrics.public_metadata(),
    }


def _generation_request(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
) -> object:
    """Build the fixed worker request for both diagnostic variants."""
    from wellplot.agent.providers.base import StructuredGenerationRequest

    return StructuredGenerationRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_seconds=timeout_seconds,
        temperature=WORKER_TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


async def run_authoritative_attempt(
    case: Mapping[str, object],
    *,
    backend: ModelBackendProtocol,
    planner: SemanticPlanner,
    registry: CapabilityRegistry,
    timeout_seconds: float,
    attempt_index: int,
) -> dict[str, object]:
    """Run one shared planner/enrichment result through A and C workers."""
    document = _document()
    request = _case_request(case)
    started = time.perf_counter()
    base = {
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "arm": "authoritative-request",
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "planner_temperature": PLANNER_TEMPERATURE,
        "worker_temperature": WORKER_TEMPERATURE,
        "natural_request_sha256": _sha256(request),
        "case_corpus_sha256": case_corpus_sha256(),
        "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        "system_prompt_a_sha256": _sha256(TYPED_SECTION_SYSTEM_PROMPT),
        "system_prompt_c_sha256": _sha256(AUTHORITATIVE_REQUEST_SYSTEM_PROMPT),
    }
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
    except (ProviderRequestError, PlannerSemanticFailure) as error:
        return {
            **base,
            "classification": "PLANNER_FAILURE",
            "error_type": type(error).__name__,
            "provider_category": _provider_category(error),
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    except SemanticEnrichmentError as error:
        return {
            **base,
            "classification": "ENRICHMENT_FAILURE",
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None).value,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }

    selected = _select_case_section(str(case["case_id"]), plan, enriched)
    if selected is None:
        return {
            **base,
            "classification": "PLANNER_SECTION_SELECTION_FAILURE",
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    task, section_context = selected
    serialized_a = serialize_typed_section_input(
        build_typed_section_input(task, section_context=section_context, registry=registry)
    )
    serialized_c = build_authoritative_worker_input(serialized_a, request)
    expected_sections = list(case.get("expected_sections", ()))
    expected = expected_sections[0] if expected_sections else {}
    audit = audit_input_sufficiency(
        case,
        task=task,
        section_context=section_context,
        serialized_input=serialized_a,
    )
    result_a = await generate_authoritative_variant(
        backend,
        serialized_input=serialized_a,
        system_prompt=TYPED_SECTION_SYSTEM_PROMPT,
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    result_c = await generate_authoritative_variant(
        backend,
        serialized_input=serialized_c,
        system_prompt=AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    return {
        **base,
        "classification": "PAIRED_TYPED_ATTEMPT",
        "production_input_sha256": _sha256(serialized_a),
        "production_input_chars": len(serialized_a),
        "authoritative_input_sha256": _sha256(serialized_c),
        "authoritative_input_chars": len(serialized_c),
        "authoritative_field_only_diff": only_authoritative_field_differs(
            serialized_a, serialized_c
        ),
        "input_sufficiency": {
            "sufficient": audit.sufficient,
            "facts": audit.facts,
            "missing_fact_ids": audit.missing_fact_ids,
        },
        "vdl_axis_facts_in_task": _axis_facts_present(task),
        "a": result_a,
        "c": result_c,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def _axis_facts_present(task: SectionTask) -> dict[str, bool]:
    """Report whether planner prose retained VDL axis facts."""
    text = " ".join((*task.requirements, *task.constraints, task.goal)).lower()
    return {
        "unit": bool(re.search(r"sample\s+unit\s+[a-z]+", text)),
        "source_origin": "source origin" in text,
        "source_step": "source step" in text,
        "tick_count": bool(re.search(r"\d+\s+ticks", text)),
    }


def classify_repeated_channel_calls(calls: list[object]) -> str:
    """Classify the terminal repeated-channel provider response safely."""
    if not calls:
        return "NO_PROVIDER_RESPONSE"
    call = calls[-1]
    if call.provider_exception_type:
        return "PROVIDER_EXCEPTION"
    if call.has_refusal or call.has_tool_calls or not call.content_is_string:
        return "PROVIDER_SHAPE_FAILURE"
    if call.finish_reason == "length" or call.content_chars == 0:
        return "INCOMPLETE_RESPONSE"
    if call.json_parse_valid is False:
        return "JSON_PARSE_FAILURE"
    if call.pydantic_valid is False:
        return "SCHEMA_VALIDATION_FAILURE"
    if call.semantic_plan_valid is False:
        return "SEMANTIC_PLAN_FAILURE"
    if call.semantic_plan_valid is True:
        return "PLAN_SUCCESS"
    return "UNCLASSIFIED_RESPONSE"


async def run_authoritative_matrix(args: argparse.Namespace) -> None:
    """Run the six-case paired A/C matrix with incremental writes."""
    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise RuntimeError("CM-56 corpus hash changed from the frozen baseline.")
    from scripts.cm56_typed_section_shadow import _provider_configuration

    backend = _provider_configuration(args)
    registry = create_builtin_registry()
    cases = [case for case in load_case_definitions() if case["case_id"] in REPRESENTATION_CASES]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            planner = SemanticPlanner(backend=backend, registry=registry)
            for attempt_index in range(args.attempts):
                row = await run_authoritative_attempt(
                    case,
                    backend=backend,
                    planner=planner,
                    registry=registry,
                    timeout_seconds=args.timeout,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


async def run_repeated_channel_matrix(args: argparse.Namespace) -> None:
    """Run ten planner-only repeated-channel forensic attempts."""
    from scripts.cm56r2_planner_diagnostic import source_summary
    from wellplot.agent.code_mode.planner import SemanticPlan
    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    case = next(
        case for case in load_case_definitions() if case["case_id"] == REPEATED_CHANNEL_CASE
    )
    source_payload = source_summary(case)
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for attempt_index in range(REPEATED_CHANNEL_ATTEMPTS):
            capture = ForensicCapture(response_model=SemanticPlan)
            base_backend = _provider_configuration(args)
            backend = CountingBackend(
                OpenAICompatibleBackendV2(
                    model=base_backend.model,  # type: ignore[attr-defined]
                    client=_ForensicClient(base_backend.client, capture),  # type: ignore[attr-defined]
                    structured_output="json_schema",
                    max_tokens_parameter=args.max_tokens_parameter,
                )
            )
            request = _case_request(case)
            started = time.perf_counter()
            planner_error: BaseException | None = None
            plan = None
            try:
                plan = await SemanticPlanner(
                    backend=backend,
                    registry=create_builtin_registry(),
                ).plan(
                    request=request,
                    mode="reconstruct",
                    current_document_summary=AuthoringInspectionFacade(_document())
                    .document_summary()
                    .model_dump(mode="json"),
                    source_summary=source_payload,
                    timeout_seconds=args.timeout,
                    temperature=PLANNER_TEMPERATURE,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )
            except (ProviderRequestError, PlannerSemanticFailure) as error:
                planner_error = error
            except Exception as error:
                planner_error = error
            row = {
                "experiment_version": EXPERIMENT_VERSION,
                "baseline_sha": BASELINE_SHA,
                "arm": "repeated-channel-forensics",
                "case_id": REPEATED_CHANNEL_CASE,
                "attempt_index": attempt_index,
                "planner_temperature": PLANNER_TEMPERATURE,
                "natural_request_sha256": _sha256(request),
                "source_summary_sha256": _sha256_json(source_payload),
                "planner_calls": backend.structured_calls,
                "calls": [
                    call.public(derived_call_role=role)
                    for call, role in zip(
                        capture.calls,
                        _derived_call_roles(capture.calls),
                        strict=True,
                    )
                ],
                "classification": (
                    "PLAN_SUCCESS"
                    if plan is not None
                    else classify_repeated_channel_calls(capture.calls)
                ),
                "source_plan_classification": (
                    None if plan is None else classify_source_plan(plan)
                ),
                "planner_error_type": (
                    None if planner_error is None else type(planner_error).__name__
                ),
                "planner_error_code": (
                    None if planner_error is None else getattr(planner_error, "code", None)
                ),
                "provider_category": _provider_category(planner_error),
                "plan": None if plan is None else safe_plan_projection(plan),
                "elapsed_ms": (time.perf_counter() - started) * 1000,
            }
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()


def _derived_call_roles(calls: list[object]) -> tuple[str, ...]:
    """Label initial and bounded invalid-response retry calls."""
    if not calls:
        return ()
    return ("initial",) + tuple("invalid_response_retry" for _ in calls[1:])


def _parser() -> argparse.ArgumentParser:
    """Build the CM-56R6 diagnostic CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("authoritative", "repeated-channel"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--max-output-tokens", type=int, default=MAX_OUTPUT_TOKENS)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_tokens", "max_completion_tokens"),
        default="max_tokens",
    )
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS)
    parser.add_argument("--attempts", type=int, default=ATTEMPTS)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def main() -> None:
    """Run one CM-56R6 diagnostic arm."""
    args = _parser().parse_args()
    if args.arm == "repeated-channel":
        asyncio.run(run_repeated_channel_matrix(args))
    else:
        asyncio.run(run_authoritative_matrix(args))


__all__ = [
    "AUTHORITATIVE_FIELD",
    "AUTHORITATIVE_REQUEST_SYSTEM_PROMPT",
    "REPEATED_CHANNEL_ATTEMPTS",
    "REPRESENTATION_CASES",
    "build_authoritative_worker_input",
    "classify_repeated_channel_calls",
    "only_authoritative_field_differs",
    "run_authoritative_attempt",
]


if __name__ == "__main__":  # pragma: no cover
    main()

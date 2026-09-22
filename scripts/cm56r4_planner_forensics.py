"""Capture bounded planner/provider failure forensics for CM-56R4."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel, ValidationError

from scripts.cm56_typed_section_shadow import (
    REPO_ROOT,
    _document,
    build_fixture_enricher,
    build_source_candidates,
    case_corpus_sha256,
    load_case_definitions,
)
from scripts.cm56r2_planner_diagnostic import (
    CountingBackend,
    _provider_category,
    _provider_configuration,
    safe_enrichment_projection,
    safe_plan_projection,
    source_summary,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import (
    PlannerSemanticFailure,
    SemanticPlan,
    SemanticPlanner,
    validate_semantic_plan,
)
from wellplot.agent.providers.base import ProviderRequestError
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import create_builtin_registry

EXPERIMENT_VERSION = "CM-56R4"
BASELINE_SHA = "755f59e"
CASE_CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
PLANNER_TEMPERATURE = 0.0
PRIMARY_CASE_IDS = ("reverse_scale", "source_selection")


@dataclass(slots=True)
class ForensicCall:
    """Transient inspection of one provider response, without raw content storage."""

    provider_call_index: int
    finish_reason: str | None = None
    message_role: str | None = None
    has_refusal: bool = False
    has_tool_calls: bool = False
    content_is_string: bool = False
    content_chars: int | None = None
    content_sha256: str | None = None
    json_parse_valid: bool | None = None
    json_error_type: str | None = None
    json_error_position: int | None = None
    json_top_level_type: str | None = None
    json_top_level_keys: tuple[str, ...] = ()
    pydantic_valid: bool | None = None
    pydantic_error_locations: tuple[dict[str, object], ...] = ()
    pydantic_error_types: tuple[str, ...] = ()
    pydantic_error_count: int = 0
    semantic_plan_valid: bool | None = None
    semantic_error_code: str | None = None
    plan_projection: dict[str, object] | None = None
    provider_exception_type: str | None = None

    def public(self, *, derived_call_role: str) -> dict[str, object]:
        """Return redacted, deterministic evidence for this call."""
        return {
            "provider_call_index": self.provider_call_index,
            "derived_call_role": derived_call_role,
            "finish_reason": self.finish_reason,
            "message_role": self.message_role,
            "has_refusal": self.has_refusal,
            "has_tool_calls": self.has_tool_calls,
            "content_is_string": self.content_is_string,
            "content_chars": self.content_chars,
            "content_sha256": self.content_sha256,
            "json_parse_valid": self.json_parse_valid,
            "json_error_type": self.json_error_type,
            "json_error_position": self.json_error_position,
            "json_top_level_type": self.json_top_level_type,
            "json_top_level_keys": list(self.json_top_level_keys),
            "pydantic_valid": self.pydantic_valid,
            "pydantic_error_locations": list(self.pydantic_error_locations),
            "pydantic_error_types": list(self.pydantic_error_types),
            "pydantic_error_count": self.pydantic_error_count,
            "semantic_plan_valid": self.semantic_plan_valid,
            "semantic_error_code": self.semantic_error_code,
            "plan": self.plan_projection,
            "provider_exception_type": self.provider_exception_type,
        }


@dataclass(slots=True)
class ForensicCapture:
    """Collect response metadata behind an evaluation-only client proxy."""

    response_model: type[BaseModel] = SemanticPlan
    calls: list[ForensicCall] = field(default_factory=list)

    def capture_response(self, response: object) -> ForensicCall:
        """Inspect one response independently of the production adapter."""
        call = ForensicCall(provider_call_index=len(self.calls) + 1)
        self.calls.append(call)
        choices = _field(response, "choices")
        if not isinstance(choices, (list, tuple)) or not choices:
            return call
        choice = choices[0]
        call.finish_reason = _optional_text(_field(choice, "finish_reason"))
        message = _field(choice, "message")
        if message is None:
            return call
        call.message_role = _optional_text(_field(message, "role"))
        call.has_refusal = _field(message, "refusal") is not None
        tool_calls = _field(message, "tool_calls")
        call.has_tool_calls = bool(tool_calls)
        content = _field(message, "content")
        call.content_is_string = isinstance(content, str)
        if not call.content_is_string:
            return call
        assert isinstance(content, str)
        call.content_chars = len(content)
        call.content_sha256 = _sha256(content)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            call.json_parse_valid = False
            call.json_error_type = type(error).__name__
            call.json_error_position = error.pos
            return call
        call.json_parse_valid = True
        call.json_top_level_type = _json_type(parsed)
        if isinstance(parsed, dict):
            call.json_top_level_keys = tuple(sorted(str(key) for key in parsed))
        try:
            plan = self.response_model.model_validate(parsed)
        except ValidationError as error:
            call.pydantic_valid = False
            locations, error_types = _safe_validation_errors(error)
            call.pydantic_error_locations = locations
            call.pydantic_error_types = error_types
            call.pydantic_error_count = len(locations)
            return call
        call.pydantic_valid = True
        call.plan_projection = safe_plan_projection(plan)
        try:
            validate_semantic_plan(plan, create_builtin_registry())
        except Exception as error:
            call.semantic_plan_valid = False
            call.semantic_error_code = getattr(error, "code", type(error).__name__)
        else:
            call.semantic_plan_valid = True
        return call

    def capture_provider_exception(self, error: BaseException) -> ForensicCall:
        """Record a call that failed before a provider response existed."""
        call = ForensicCall(
            provider_call_index=len(self.calls) + 1,
            provider_exception_type=type(error).__name__,
        )
        self.calls.append(call)
        return call


class _ForensicCompletions:
    """Delegate completions unchanged while capturing response metadata."""

    def __init__(self, delegate: object, capture: ForensicCapture) -> None:
        self._delegate = delegate
        self._capture = capture

    async def create(self, **kwargs: object) -> object:
        """Forward exact request arguments and return the exact response object."""
        create = self._delegate.create
        try:
            response = await create(**kwargs)
        except Exception as error:
            self._capture.capture_provider_exception(error)
            raise
        self._capture.capture_response(response)
        return response


class _ForensicClient:
    """Minimal client-shaped proxy used only by the forensic runner."""

    def __init__(self, client: object, capture: ForensicCapture) -> None:
        chat = client.chat
        completions = chat.completions
        self.chat = SimpleNamespace(
            completions=_ForensicCompletions(completions, capture),
        )


def capture_forensic_response(
    response: object,
    *,
    response_model: type[BaseModel] = SemanticPlan,
) -> ForensicCall:
    """Inspect a synthetic response with the same independent checks as live runs."""
    return ForensicCapture(response_model=response_model).capture_response(response)


def classify_reverse_call(calls: list[ForensicCall]) -> str:
    """Classify the terminal planner boundary for the reverse-scale case."""
    if not calls:
        return "REVERSE_OTHER_PROVIDER_FAILURE"
    call = calls[-1]
    if call.provider_exception_type:
        return "REVERSE_OTHER_PROVIDER_FAILURE"
    if call.has_refusal or call.has_tool_calls or not call.content_is_string:
        return "REVERSE_PROVIDER_SHAPE_FAILURE"
    if call.finish_reason == "length" or call.content_chars == 0:
        return "REVERSE_INCOMPLETE_RESPONSE"
    if call.json_parse_valid is False:
        return "REVERSE_JSON_PARSE_FAILURE"
    if call.pydantic_valid is False:
        return "REVERSE_SCHEMA_VALIDATION_FAILURE"
    if call.semantic_plan_valid is False:
        return "REVERSE_SEMANTIC_CAPABILITY_FAILURE"
    if call.semantic_plan_valid is True:
        return "REVERSE_PLAN_SUCCESS"
    return "REVERSE_OTHER_PROVIDER_FAILURE"


def classify_source_plan(plan: SemanticPlan) -> str:
    """Classify source-hint shape without performing lexical resolution."""
    tasks = plan.section_tasks
    hint_sets = [tuple(_normalize(value) for value in task.source_hints) for task in tasks]
    if len(tasks) == 1:
        hints = hint_sets[0]
        if not hints:
            return "SOURCE_MISSING_HINT"
        if any(value == "secondary" for value in hints):
            return "SOURCE_EXACT_SECONDARY"
        if any(value == "primary" for value in hints):
            return "SOURCE_WRONG_PRIMARY"
        return "SOURCE_INVALID_HINT"
    if len(tasks) != 2:
        return "SOURCE_OTHER_PLAN_SHAPE"
    if all(not hints for hints in hint_sets):
        return "SOURCE_DUPLICATE_TASKS_NO_HINT"
    if all(hints and hints == hint_sets[0] for hints in hint_sets[1:]):
        return "SOURCE_DUPLICATE_TASKS_SAME_HINT"
    if len({hint for hints in hint_sets for hint in hints}) > 1:
        return "SOURCE_DUPLICATE_TASKS_MIXED_HINTS"
    return "SOURCE_OTHER_PLAN_SHAPE"


def classify_enrichment(enriched: object) -> str:
    """Classify source selection using only selected opaque candidate identities."""
    sections = tuple(getattr(enriched, "sections", ()))
    selected = tuple(
        source.candidate_id for section in sections for source in getattr(section, "sources", ())
    )
    if selected and all(candidate_id == "secondary-source" for candidate_id in selected):
        return "ENRICHED_SECONDARY"
    if selected and all(candidate_id == "primary-source" for candidate_id in selected):
        return "ENRICHED_PRIMARY"
    return "OTHER_ENRICHMENT_FAILURE"


def derived_call_roles(calls: list[ForensicCall]) -> tuple[str, ...]:
    """Label call roles from the bounded planner call sequence."""
    if not calls:
        return ()
    if len(calls) == 1:
        return ("initial",)
    first = calls[0]
    second_role = "semantic_correction" if first.semantic_error_code else "invalid_response_retry"
    return ("initial",) + (second_role,) + tuple("additional_unexpected_call" for _ in calls[2:])


async def run_attempt(
    case: dict[str, object],
    *,
    args: argparse.Namespace,
    attempt_index: int,
) -> dict[str, object]:
    """Run one planner/enricher attempt through the unchanged production adapter."""
    request_file = case.get("request_file")
    request = (
        (REPO_ROOT / str(request_file)).read_text(encoding="utf-8")
        if request_file
        else str(case["request"])
    )
    source_payload = source_summary(case)
    capture = ForensicCapture()
    base_backend = _provider_configuration(args)
    backend = CountingBackend(
        OpenAICompatibleBackendV2(
            model=base_backend.model,  # type: ignore[attr-defined]
            client=_ForensicClient(base_backend.client, capture),  # type: ignore[attr-defined]
            structured_output="json_schema",
            max_tokens_parameter=args.max_tokens_parameter,
        )
    )
    started = time.perf_counter()
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())
    document = _document()
    plan: SemanticPlan | None = None
    planner_error: BaseException | None = None
    try:
        plan = await planner.plan(
            request=request,
            mode="reconstruct",
            current_document_summary=AuthoringInspectionFacade(document)
            .document_summary()
            .model_dump(mode="json"),
            source_summary=source_payload,
            timeout_seconds=args.timeout,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=args.max_output_tokens,
        )
    except (ProviderRequestError, PlannerSemanticFailure) as error:
        planner_error = error
    except Exception as error:
        planner_error = error

    row: dict[str, object] = {
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "planner_temperature": PLANNER_TEMPERATURE,
        "natural_request_sha256": _sha256(request),
        "source_summary_sha256": _sha256_json(source_payload),
        "planner_calls": backend.structured_calls,
        "calls": [
            call.public(derived_call_role=role)
            for call, role in zip(capture.calls, derived_call_roles(capture.calls), strict=True)
        ],
        "plan": None if plan is None else safe_plan_projection(plan),
        "planner_error_type": None if planner_error is None else type(planner_error).__name__,
        "planner_error_code": (
            None if planner_error is None else getattr(planner_error, "code", None)
        ),
        "provider_category": _provider_category(planner_error),
        "classification": None,
        "source_plan_classification": None,
        "enrichment_classification": None,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }
    if case["case_id"] == "reverse_scale":
        row["classification"] = (
            "REVERSE_PLAN_SUCCESS" if plan is not None else classify_reverse_call(capture.calls)
        )
    elif plan is None:
        row["classification"] = "SOURCE_PLANNER_FAILURE"
    else:
        row["source_plan_classification"] = classify_source_plan(plan)

    if plan is not None:
        try:
            enriched = build_fixture_enricher(case).enrich(
                plan=plan,
                document=document,
                source_candidates=build_source_candidates(case),
                mode="reconstruct",
            )
        except SemanticEnrichmentError as error:
            code = getattr(error.code, "value", error.code)
            row["enrichment_classification"] = {
                "source_ambiguous": "SOURCE_AMBIGUOUS",
                "source_missing": "SOURCE_MISSING",
            }.get(str(code), "OTHER_ENRICHMENT_FAILURE")
            row["enrichment_code"] = str(code)
        else:
            row["enrichment_classification"] = classify_enrichment(enriched)
            row["enrichment"] = safe_enrichment_projection(enriched)
            if case["case_id"] == "source_selection":
                row["classification"] = row["enrichment_classification"]
    return row


async def run_matrix(args: argparse.Namespace) -> None:
    """Run the two primary cases sequentially with incremental JSONL writes."""
    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise RuntimeError("CM-56 corpus hash changed from the frozen CM-56R4 baseline.")
    cases_by_id = {case["case_id"]: case for case in load_case_definitions()}
    cases = [cases_by_id[case_id] for case_id in PRIMARY_CASE_IDS]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            for attempt_index in range(args.attempts):
                row = await run_attempt(case, args=args, attempt_index=attempt_index)
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


def _field(value: object, name: str) -> object:
    """Read a field from an SDK object or a test mapping."""
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _optional_text(value: object) -> str | None:
    """Return non-empty text only for safe response metadata."""
    return value if isinstance(value, str) else None


def _json_type(value: object) -> str:
    """Return a stable JSON type label without retaining values."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _safe_validation_errors(
    error: ValidationError,
) -> tuple[tuple[dict[str, object], ...], tuple[str, ...]]:
    """Reduce Pydantic errors to locations and types only."""
    locations: list[dict[str, object]] = []
    error_types: list[str] = []
    for item in error.errors():
        loc = tuple(str(part) for part in item.get("loc", ()))
        error_type = str(item.get("type", "unknown"))
        locations.append({"loc": list(loc), "type": error_type})
        error_types.append(error_type)
    return tuple(locations), tuple(error_types)


def _normalize(value: str) -> str:
    """Normalize source labels for exact classification only."""
    return " ".join(value.casefold().split())


def _sha256(value: str) -> str:
    """Hash text without retaining it in evidence."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: object) -> str:
    """Hash one deterministic JSON-compatible value."""
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    """Build the bounded CM-56R4 live runner CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--max-output-tokens", type=int, default=16384)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_tokens", "max_completion_tokens"),
        default="max_tokens",
    )
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def main() -> None:
    """Run the frozen two-case forensic matrix."""
    asyncio.run(run_matrix(_parser().parse_args()))


if __name__ == "__main__":  # pragma: no cover
    main()

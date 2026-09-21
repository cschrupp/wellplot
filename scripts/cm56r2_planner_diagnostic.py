"""Planner-only CM-56R2 diagnostic matrix."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from scripts.cm56_typed_section_shadow import (
    REPO_ROOT,
    _document,
    build_fixture_enricher,
    build_source_candidates,
    load_case_definitions,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import SemanticPlan, SemanticPlanner
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import create_builtin_registry

SOURCE_SUMMARY_VERSION = "cm56r2.source-summary.v1"
VARIANT_NAMES = ("A", "B", "C", "D")
_PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;]+")


@dataclass(frozen=True, slots=True)
class DiagnosticVariant:
    """One fixed planner-only experiment condition."""

    name: Literal["A", "B", "C", "D"]
    temperature: float
    include_source_summary: bool


VARIANTS = {
    "A": DiagnosticVariant("A", temperature=1.0, include_source_summary=False),
    "B": DiagnosticVariant("B", temperature=0.0, include_source_summary=False),
    "C": DiagnosticVariant("C", temperature=1.0, include_source_summary=True),
    "D": DiagnosticVariant("D", temperature=0.0, include_source_summary=True),
}


@dataclass
class CountingBackend:
    """Count bounded planner calls without retaining provider responses."""

    delegate: ModelBackendProtocol
    structured_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Count and delegate one structured planner request."""
        self.structured_calls += 1
        return await self.delegate.generate_structured(request, response_model=response_model)

    async def generate_program(self, request: object) -> object:
        """Fail if the planner diagnostic accidentally enters a worker path."""
        raise AssertionError(f"Unexpected program generation request: {request!r}")


def source_summary(case: dict[str, object]) -> dict[str, object]:
    """Build a compact path-free summary of the explicit source universe."""
    sources = []
    for source in case.get("sources", ()):
        source_data = dict(source)
        labels = [_safe_text(str(label)) for label in source_data.get("labels", ())]
        channels = [
            {
                "mnemonic": str(channel["mnemonic"]),
                "kind": str(channel["kind"]),
            }
            for channel in source_data.get("channels", ())
        ]
        sources.append({"labels": labels, "channels": channels})
    return {"version": SOURCE_SUMMARY_VERSION, "sources": sources}


def diagnostic_request(case: dict[str, object], *, include_source_summary: bool) -> str:
    """Return the frozen request with an optional bounded source summary."""
    request_file = case.get("request_file")
    request = (
        (REPO_ROOT / str(request_file)).read_text(encoding="utf-8")
        if request_file
        else str(case["request"])
    )
    if not include_source_summary:
        return request
    return (
        request
        + "\n\nBounded source summary for planning only:\n"
        + json.dumps(source_summary(case), sort_keys=True, separators=(",", ":"))
    )


def safe_plan_projection(plan: SemanticPlan) -> dict[str, object]:
    """Serialize semantic plan evidence while redacting path-shaped text."""
    return _redact_json(plan.model_dump(mode="json"))


def safe_enrichment_projection(enriched: object) -> dict[str, object]:
    """Record bounded enrichment shape without host paths or source identities."""
    sections = getattr(enriched, "sections", ())
    return {
        "section_count": len(sections),
        "section_source_counts": [len(getattr(section, "sources", ())) for section in sections],
    }


def _redact_json(value: object) -> object:
    """Recursively redact path-shaped strings from diagnostic projections."""
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        return {str(key): _redact_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def _safe_text(value: str) -> str:
    """Redact filesystem-shaped text without changing scientific values."""
    return _PATH_RE.sub("[redacted-path]", value)


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the explicitly configured OpenAI-compatible backend."""
    from openai import AsyncOpenAI

    api_key = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        key_path = Path(args.api_key_file)
        if not key_path.is_absolute():
            key_path = REPO_ROOT / key_path
        api_key = api_key or key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No CM-56R2 API key configured.")
    return OpenAICompatibleBackendV2(
        model=args.model,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=args.timeout),
        structured_output="json_schema",
        max_tokens_parameter=args.max_tokens_parameter,
    )


def _base_row(
    *,
    case: dict[str, object],
    variant: DiagnosticVariant,
    attempt_index: int,
    request: str,
    source_summary_payload: dict[str, object] | None,
    started: float,
    backend: CountingBackend,
    classification: str,
    error: BaseException | None,
    plan: SemanticPlan | None = None,
) -> dict[str, object]:
    """Build bounded redacted evidence for one planner attempt."""
    return {
        "experiment_version": "CM-56R2",
        "case_id": case["case_id"],
        "variant": variant.name,
        "temperature": variant.temperature,
        "source_summary_included": variant.include_source_summary,
        "source_summary_sha256": _sha256_json(source_summary_payload),
        "attempt_index": attempt_index,
        "natural_request_sha256": _sha256(request),
        "planner_calls": backend.structured_calls,
        "classification": classification,
        "error_type": type(error).__name__ if error is not None else None,
        "error_code": getattr(error, "code", None),
        "provider_category": _provider_category(error),
        "plan": None if plan is None else safe_plan_projection(plan),
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


async def run_attempt(
    case: dict[str, object],
    *,
    backend: CountingBackend,
    variant: DiagnosticVariant,
    args: argparse.Namespace,
    attempt_index: int,
) -> dict[str, object]:
    """Run planning and enrichment only; never invoke a typed worker."""
    request = diagnostic_request(case, include_source_summary=variant.include_source_summary)
    source_payload = source_summary(case) if variant.include_source_summary else None
    started = time.perf_counter()
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())
    document = _document()
    try:
        plan = await planner.plan(
            request=request,
            mode="reconstruct",
            current_document_summary=AuthoringInspectionFacade(document)
            .document_summary()
            .model_dump(mode="json"),
            timeout_seconds=args.timeout,
            temperature=variant.temperature,
            max_output_tokens=args.max_output_tokens,
        )
    except ProviderRequestError as error:
        return _base_row(
            case=case,
            variant=variant,
            attempt_index=attempt_index,
            request=request,
            source_summary_payload=source_payload,
            started=started,
            backend=backend,
            classification="PLANNER_FAILURE",
            error=error,
        )
    except Exception as error:
        return _base_row(
            case=case,
            variant=variant,
            attempt_index=attempt_index,
            request=request,
            source_summary_payload=source_payload,
            started=started,
            backend=backend,
            classification="PLANNER_FAILURE",
            error=error,
        )

    try:
        enriched = build_fixture_enricher(case).enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except SemanticEnrichmentError as error:
        row = _base_row(
            case=case,
            variant=variant,
            attempt_index=attempt_index,
            request=request,
            source_summary_payload=source_payload,
            started=started,
            backend=backend,
            classification="ENRICHMENT_FAILURE",
            error=error,
            plan=plan,
        )
        row["enrichment_code"] = getattr(error, "code", None)
        return row

    row = _base_row(
        case=case,
        variant=variant,
        attempt_index=attempt_index,
        request=request,
        source_summary_payload=source_payload,
        started=started,
        backend=backend,
        classification="PLANNED",
        error=None,
        plan=plan,
    )
    row["enrichment"] = safe_enrichment_projection(enriched)
    row["section_task_count"] = len(plan.section_tasks)
    return row


async def run_matrix(args: argparse.Namespace) -> None:
    """Run the four fixed planner-only variants sequentially."""
    cases = load_case_definitions()
    variants = [VARIANTS[name] for name in args.variants]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for variant in variants:
            for case in cases:
                for attempt_index in range(args.attempts):
                    delegate = _provider_configuration(args)
                    backend = CountingBackend(delegate)
                    row = await run_attempt(
                        case,
                        backend=backend,
                        variant=variant,
                        args=args,
                        attempt_index=attempt_index,
                    )
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                    handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build the planner-only diagnostic CLI."""
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
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--variants", nargs="+", choices=VARIANT_NAMES, default=VARIANT_NAMES)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def _sha256(value: str) -> str:
    """Hash UTF-8 diagnostic text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: object) -> str | None:
    """Hash a JSON-shaped diagnostic payload when one is present."""
    if value is None:
        return None
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _provider_category(error: BaseException | None) -> str | None:
    """Serialize a provider category without exception text."""
    category = getattr(error, "category", None)
    return getattr(category, "value", category)


def main() -> None:
    """Run the sequential planner-only matrix."""
    asyncio.run(run_matrix(_parser().parse_args()))


if __name__ == "__main__":  # pragma: no cover
    main()

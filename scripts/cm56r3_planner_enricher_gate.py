"""Run the CM-56R3 planner/enricher-only gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from scripts.cm56_typed_section_shadow import (
    REPO_ROOT,
    _document,
    build_fixture_enricher,
    build_source_candidates,
    load_case_definitions,
)
from scripts.cm56r2_planner_diagnostic import (
    CountingBackend,
    _provider_category,
    _provider_configuration,
    _sha256,
    _sha256_json,
    safe_enrichment_projection,
    safe_plan_projection,
    source_summary,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import SemanticPlanner
from wellplot.agent.providers.base import ProviderRequestError
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import create_builtin_registry

PLANNER_TEMPERATURE = 0.0
EXPERIMENT_VERSION = "CM-56R3"


async def run_attempt(
    case: dict[str, object],
    *,
    backend: CountingBackend,
    args: argparse.Namespace,
    attempt_index: int,
) -> dict[str, object]:
    """Run one planner/enricher attempt without invoking a typed worker."""
    request_file = case.get("request_file")
    request = (
        (REPO_ROOT / str(request_file)).read_text(encoding="utf-8")
        if request_file
        else str(case["request"])
    )
    source_payload = source_summary(case)
    started = time.perf_counter()
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())
    document = _document()
    base = {
        "experiment_version": EXPERIMENT_VERSION,
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "planner_temperature": PLANNER_TEMPERATURE,
        "natural_request_sha256": _sha256(request),
        "source_summary_sha256": _sha256_json(source_payload),
    }

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
    except ProviderRequestError as error:
        return {
            **base,
            "classification": "PLANNER_FAILURE",
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "provider_category": _provider_category(error),
            "planner_calls": backend.structured_calls,
            "plan": None,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    except Exception as error:
        return {
            **base,
            "classification": "PLANNER_FAILURE",
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "provider_category": _provider_category(error),
            "planner_calls": backend.structured_calls,
            "plan": None,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }

    try:
        enriched = build_fixture_enricher(case).enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except SemanticEnrichmentError as error:
        return {
            **base,
            "classification": "ENRICHMENT_FAILURE",
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "provider_category": None,
            "plan": safe_plan_projection(plan),
            "enrichment": None,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }

    return {
        **base,
        "classification": "PLANNED_AND_ENRICHED",
        "error_type": None,
        "error_code": None,
        "provider_category": None,
        "planner_calls": backend.structured_calls,
        "plan": safe_plan_projection(plan),
        "enrichment": safe_enrichment_projection(enriched),
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


async def run_matrix(args: argparse.Namespace) -> None:
    """Run the frozen ten-case corpus at the fixed planner temperature."""
    cases = load_case_definitions()
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            for attempt_index in range(args.attempts):
                backend = CountingBackend(_provider_configuration(args))
                row = await run_attempt(
                    case,
                    backend=backend,
                    args=args,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build the CM-56R3 gate command-line parser."""
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
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def main() -> None:
    """Run the sequential planner/enricher gate."""
    asyncio.run(run_matrix(_parser().parse_args()))


if __name__ == "__main__":  # pragma: no cover
    main()

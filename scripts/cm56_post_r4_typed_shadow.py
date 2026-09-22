"""Run the post-CM-56R4 typed-worker shadow gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from scripts.cm56_typed_section_shadow import (
    _base_row,
    _case_request,
    _context_row,
    _document,
    _provider_category,
    _success_row,
    audit_input_sufficiency,
    build_fixture_enricher,
    build_source_candidates,
    case_corpus_sha256,
    evaluate_semantic_draft,
    load_case_definitions,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import SemanticPlanner
from wellplot.agent.code_mode.section_semantics import SectionSemanticValidationError
from wellplot.agent.code_mode.semantic_section_compiler import (
    SectionSemanticCompilationError,
)
from wellplot.agent.code_mode.typed_section_worker import (
    TYPED_SECTION_SYSTEM_PROMPT,
    TypedSectionCompiler,
    TypedSectionRepresentabilityError,
    TypedSectionWorkerError,
    build_typed_section_input,
    response_schema_sha256,
    serialize_typed_section_input,
)
from wellplot.agent.code_mode.workflow import _planner_source_summary
from wellplot.agent.providers.base import ProviderRequestError
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import create_builtin_registry

EXPERIMENT_VERSION = "CM-56-post-r4-typed-shadow.v1"
PLANNER_TEMPERATURE = 0.0
WORKER_TEMPERATURE = 1.0
STAGE_ONE_ATTEMPTS = 3
STAGE_TWO_CBL_ATTEMPTS = 10
STAGE_TWO_GENERALIZATION_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class ProductionPlannerBoundary:
    """Call the production planner with the production source-summary shape."""

    planner: SemanticPlanner
    source_summary: Mapping[str, object]

    async def plan(
        self,
        *,
        request: str,
        mode: str,
        current_document_summary: Mapping[str, object],
        source_summary: Mapping[str, object] | None = None,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> object:
        """Ignore caller overrides and preserve the production planner boundary."""
        del source_summary, temperature
        return await self.planner.plan(
            request=request,
            mode=mode,
            current_document_summary=current_document_summary,
            source_summary=self.source_summary,
            timeout_seconds=timeout_seconds,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=max_output_tokens,
        )


def production_source_summary(case: Mapping[str, object]) -> dict[str, object]:
    """Build the exact source summary used by the production graph."""
    candidates = build_source_candidates(case)
    state = {"source_candidates": [candidate.model_dump(mode="json") for candidate in candidates]}
    return _planner_source_summary(state)  # type: ignore[arg-type]


def attempt_range(case_id: str, stage: str) -> range:
    """Return the frozen attempt range for one gate stage."""
    if stage == "stage1":
        return range(STAGE_ONE_ATTEMPTS)
    if stage != "stage2":
        raise ValueError(f"Unknown CM-56 post-R4 stage {stage!r}.")
    final_attempt = (
        STAGE_TWO_CBL_ATTEMPTS if case_id == "cbl_continuity" else STAGE_TWO_GENERALIZATION_ATTEMPTS
    )
    return range(STAGE_ONE_ATTEMPTS, final_attempt)


async def run_case_attempt(
    case: Mapping[str, object],
    *,
    planner: ProductionPlannerBoundary,
    typed: TypedSectionCompiler,
    args: argparse.Namespace,
    attempt_index: int,
    stage: str,
) -> dict[str, object]:
    """Run one production-boundary planner/enricher/typed-worker attempt."""
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
            timeout_seconds=args.timeout,
            temperature=WORKER_TEMPERATURE,
            max_output_tokens=args.max_output_tokens,
        )
    except ProviderRequestError as error:
        return _annotate_row(
            _base_row(case, attempt_index, request, started, "PLANNER_FAILURE", error=error),
            case=case,
            stage=stage,
        )
    except Exception as error:
        return _annotate_row(
            _base_row(case, attempt_index, request, started, "PLANNER_FAILURE", error=error),
            case=case,
            stage=stage,
        )

    try:
        enriched = build_fixture_enricher(case).enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except SemanticEnrichmentError as error:
        return _annotate_row(
            _base_row(case, attempt_index, request, started, "ENRICHMENT_FAILURE", error=error),
            case=case,
            stage=stage,
        )

    section_rows: list[dict[str, object]] = []
    expected_sections = list(case.get("expected_sections", ()))
    for index, (task, section_context) in enumerate(
        zip(plan.section_tasks, enriched.sections, strict=False)
    ):
        expected = expected_sections[index] if index < len(expected_sections) else {}
        worker_input = build_typed_section_input(
            task,
            section_context=section_context,
            registry=typed.registry,
        )
        serialized = serialize_typed_section_input(worker_input)
        audit = audit_input_sufficiency(
            case,
            task=task,
            section_context=section_context,
            serialized_input=serialized,
        )
        if not audit.sufficient:
            section_rows.append(
                _context_row(
                    case,
                    attempt_index,
                    request,
                    section_index=index,
                    audit=audit,
                    serialized=serialized,
                    classification="INPUT_INSUFFICIENT",
                    started=started,
                )
            )
            continue
        try:
            result = await typed.compile(
                task=task,
                section_context=section_context,
                document=document,
                section_id_hint=f"cm56-post-r4-{case['case_id']}-{index}",
                timeout_seconds=args.timeout,
                temperature=WORKER_TEMPERATURE,
                max_output_tokens=args.max_output_tokens,
            )
            evaluation = evaluate_semantic_draft(result.draft, expected=expected)
            section_rows.append(
                _success_row(
                    case,
                    attempt_index,
                    request,
                    plan,
                    enriched,
                    index,
                    audit,
                    result,
                    evaluation,
                    started,
                )
            )
        except TypedSectionRepresentabilityError as error:
            section_rows.append(
                _section_failure_row(
                    case,
                    attempt_index,
                    request,
                    index,
                    started,
                    "REPRESENTABILITY_GAP",
                    error,
                )
            )
        except ProviderRequestError as error:
            category = _provider_category(error)
            classification = (
                "SCHEMA_COMPATIBILITY_FAILURE"
                if category in {"invalid_response", "validation"}
                else "PROVIDER_INFRA_FAILURE"
            )
            section_rows.append(
                _section_failure_row(
                    case,
                    attempt_index,
                    request,
                    index,
                    started,
                    classification,
                    error,
                )
            )
        except SectionSemanticValidationError as error:
            section_rows.append(
                _section_failure_row(
                    case,
                    attempt_index,
                    request,
                    index,
                    started,
                    "TYPED_CONTEXT_GROUNDING_FAILURE",
                    error,
                )
            )
        except (SectionSemanticCompilationError, TypedSectionWorkerError) as error:
            section_rows.append(
                _section_failure_row(
                    case,
                    attempt_index,
                    request,
                    index,
                    started,
                    "DETERMINISTIC_COMPILER_FAILURE",
                    error,
                )
            )

    if not section_rows:
        row = _base_row(case, attempt_index, request, started, "PLANNER_FAILURE", error=None)
    else:
        row = {"case_id": case["case_id"], "attempt_index": attempt_index, "sections": section_rows}
    return _annotate_row(row, case=case, stage=stage)


def _section_failure_row(
    case: Mapping[str, object],
    attempt_index: int,
    request: str,
    section_index: int,
    started: float,
    classification: str,
    error: BaseException,
) -> dict[str, object]:
    """Record bounded section failure evidence without exception text."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "section_index": section_index,
        "natural_request_sha256": _sha256(request),
        "classification": classification,
        "error_type": type(error).__name__,
        "provider_category": _provider_category(error),
        "typed_structured_valid": False,
        "typed_context_valid": False,
        "typed_compiler_valid": False,
        "typed_semantic_acceptance": False,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def _annotate_row(
    row: dict[str, object],
    *,
    case: Mapping[str, object],
    stage: str,
) -> dict[str, object]:
    """Add experiment provenance recursively without adding host paths."""
    summary = production_source_summary(case)
    metadata = {
        "experiment_version": EXPERIMENT_VERSION,
        "stage": stage,
        "planner_temperature": PLANNER_TEMPERATURE,
        "worker_temperature": WORKER_TEMPERATURE,
        "source_summary_sha256": _sha256_json(summary),
        "response_schema_sha256": response_schema_sha256(),
        "system_prompt_sha256": _sha256(TYPED_SECTION_SYSTEM_PROMPT),
        "case_corpus_sha256": case_corpus_sha256(),
    }
    annotated = {**row, **metadata}
    if isinstance(row.get("sections"), list):
        annotated["sections"] = [
            _annotate_row(section, case=case, stage=stage) for section in row["sections"]
        ]
    return annotated


def _sha256(value: str) -> str:
    """Hash UTF-8 text deterministically."""
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Mapping[str, object]) -> str:
    """Hash one JSON-shaped value deterministically."""
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _flatten_rows(rows: list[dict[str, object]], stage: str) -> list[dict[str, object]]:
    """Flatten top-level attempts into section evidence for gate evaluation."""
    flattened: list[dict[str, object]] = []
    for row in rows:
        if row.get("stage") != stage:
            continue
        sections = row.get("sections")
        if isinstance(sections, list):
            flattened.extend(section for section in sections if isinstance(section, dict))
        else:
            flattened.append(row)
    return flattened


def summarize_jsonl(path: Path, *, stage: str) -> dict[str, object]:
    """Summarize one stage without interpreting incomplete rows as successes."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    stage_rows = [row for row in rows if row.get("stage") == stage]
    flattened = _flatten_rows(rows, stage)
    counts = Counter(str(row.get("classification")) for row in flattened)
    root_planner_failures = sum(
        row.get("classification") == "PLANNER_FAILURE"
        for row in stage_rows
        if not isinstance(row.get("sections"), list)
    )
    root_enrichment_failures = sum(
        row.get("classification") == "ENRICHMENT_FAILURE"
        for row in stage_rows
        if not isinstance(row.get("sections"), list)
    )
    decision = _gate_decision(
        counts,
        planner_failures=root_planner_failures,
        enrichment_failures=root_enrichment_failures,
    )
    return {
        "experiment": "CM-56 post-R4 typed shadow",
        "experiment_version": EXPERIMENT_VERSION,
        "stage": stage,
        "case_corpus_sha256": case_corpus_sha256(),
        "planner_temperature": PLANNER_TEMPERATURE,
        "worker_temperature": WORKER_TEMPERATURE,
        "top_level_attempts": len(stage_rows),
        "section_attempts": len(flattened),
        "classification_counts": dict(sorted(counts.items())),
        "planner_failures": root_planner_failures,
        "enrichment_failures": root_enrichment_failures,
        "decision": decision,
    }


def _gate_decision(
    counts: Counter[str],
    *,
    planner_failures: int,
    enrichment_failures: int,
) -> str:
    """Apply the post-R4 gate ordering."""
    if planner_failures:
        return "STOP_PLANNER_RELIABILITY"
    if enrichment_failures or counts.get("INPUT_INSUFFICIENT", 0):
        return "STOP_INPUT_CONTRACT"
    if counts.get("SCHEMA_COMPATIBILITY_FAILURE", 0):
        return "STOP_SCHEMA_COMPATIBILITY"
    if counts.get("PROVIDER_INFRA_FAILURE", 0):
        return "STOP_PROVIDER_RELIABILITY"
    if counts.get("TYPED_CONTEXT_GROUNDING_FAILURE", 0):
        return "STOP_TYPED_CONTEXT_GROUNDING"
    if counts.get("DETERMINISTIC_COMPILER_FAILURE", 0) or counts.get("REPRESENTABILITY_GAP", 0):
        return "STOP_DETERMINISTIC_BOUNDARY"
    if counts.get("TYPED_WORKER_SEMANTIC_FAILURE", 0):
        return "STOP_TYPED_WORKER_SEMANTICS"
    return "PROCEED_STAGE_2"


async def run_matrix(args: argparse.Namespace) -> dict[str, object]:
    """Run one frozen post-R4 stage and flush every completed attempt."""
    from scripts.cm56_typed_section_shadow import CountingBackend, _provider_configuration

    backend = CountingBackend(_provider_configuration(args))
    registry = create_builtin_registry()
    typed = TypedSectionCompiler(backend=backend, registry=registry)
    cases = load_case_definitions()
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            planner = ProductionPlannerBoundary(
                planner=SemanticPlanner(backend=backend, registry=registry),
                source_summary=production_source_summary(case),
            )
            for attempt_index in attempt_range(str(case["case_id"]), args.stage):
                row = await run_case_attempt(
                    case,
                    planner=planner,
                    typed=typed,
                    args=args,
                    attempt_index=attempt_index,
                    stage=args.stage,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
    summary = summarize_jsonl(args.output_jsonl, stage=args.stage)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    """Build the post-R4 gate CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("stage1", "stage2"), required=True)
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
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    return parser


def main() -> None:
    """Run one post-R4 stage."""
    summary = asyncio.run(run_matrix(_parser().parse_args()))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()

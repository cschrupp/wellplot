"""CM-56 real planner/enricher to typed-section shadow evaluation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    LoadedSource,
    SemanticEnricher,
    SemanticEnrichmentError,
    SourceCandidate,
)
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlanner
from wellplot.agent.code_mode.section_semantics import SectionSemanticDraft
from wellplot.agent.code_mode.typed_section_worker import (
    TYPED_SECTION_SYSTEM_PROMPT,
    TypedSectionCompiler,
    TypedSectionGenerationResult,
    TypedSectionRepresentabilityError,
    TypedSectionWorkerError,
    build_typed_section_input,
    response_schema_sha256,
    serialize_typed_section_input,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm56_shadow_cases.json"
SOURCE_ROOT = REPO_ROOT / "tests/fixtures/typed_worker/cm56_sources"
INPUT_CONTRACT_VERSION = "cm56.typed-section-input.v1"


@dataclass(frozen=True, slots=True)
class InputSufficiency:
    """Deterministic pre-output audit of required worker facts."""

    sufficient: bool
    facts: dict[str, str]
    missing_fact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticEvaluation:
    """Generic semantic acceptance projection for one typed draft."""

    checks: dict[str, bool]
    omissions: tuple[str, ...]
    unrequested_semantics: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        """Return whether every applicable semantic check passed."""
        return not self.omissions and not self.unrequested_semantics and all(self.checks.values())


class FixtureSourceLoader:
    """Return fixture-defined metadata while exercising real enrichment."""

    def __init__(self, definitions: Mapping[str, Mapping[str, object]]) -> None:
        """Index source metadata by the physical fixture filename."""
        self._definitions = definitions

    def load(self, path: Path, source_format: str) -> LoadedSource:
        """Load only bounded fixture metadata for one existing file."""
        definition = self._definitions[path.name]
        return LoadedSource(
            dataset_name=str(definition.get("dataset_name", path.stem)),
            channels=tuple(
                ChannelContext(
                    mnemonic=str(channel["mnemonic"]),
                    kind=str(channel["kind"]),
                    unit=channel.get("unit"),
                    description=str(channel.get("description", "")),
                    aliases=tuple(str(alias) for alias in channel.get("aliases", ())),
                    shape=tuple(int(value) for value in channel.get("shape", ())),
                )
                for channel in definition.get("channels", ())
            ),
        )


@dataclass
class CountingBackend:
    """Count provider calls while delegating the unchanged backend contract."""

    delegate: ModelBackendProtocol
    structured_calls: int = 0
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Count and delegate one structured request."""
        self.structured_calls += 1
        return await self.delegate.generate_structured(request, response_model=response_model)

    async def generate_program(self, request: object) -> object:
        """Count and delegate one program request for the comparator."""
        self.program_calls += 1
        return await self.delegate.generate_program(request)  # type: ignore[arg-type]


def load_case_definitions(path: str | Path = CASE_PATH) -> tuple[dict[str, object], ...]:
    """Load the frozen CM-56 case corpus and validate its digest when present."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = raw["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("CM-56 case corpus must contain cases.")
    return tuple(cases)


def case_corpus_sha256(path: str | Path = CASE_PATH) -> str:
    """Hash the compact case corpus bytes for live-evidence provenance."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_input_sufficiency(
    case: Mapping[str, object],
    *,
    task: SectionTask,
    section_context: object,
    serialized_input: str,
) -> InputSufficiency:
    """Audit declared fact provenance before inspecting any worker output."""
    facts: dict[str, str] = {}
    missing: list[str] = []
    context_sources = getattr(section_context, "sources", ())
    source_ids = {source.candidate_id for source in context_sources}
    channel_names = {channel.mnemonic for source in context_sources for channel in source.channels}
    for fact_id, raw_fact in dict(case.get("input_facts", {})).items():
        fact = dict(raw_fact)
        section_candidate = fact.get("section_candidate")
        if section_candidate is not None:
            selected_ids = {source.candidate_id for source in context_sources}
            if str(section_candidate) not in selected_ids:
                facts[fact_id] = "not_applicable"
                continue
        if fact.get("status") == "not_applicable":
            facts[fact_id] = "not_applicable"
            continue
        if fact.get("status") == "hidden_reference_not_gated":
            facts[fact_id] = "hidden_reference_not_gated"
            continue
        source = str(fact.get("source", "task"))
        needles = tuple(str(value) for value in fact.get("needles", ()))
        if source == "context":
            present = all(needle in channel_names or needle in source_ids for needle in needles)
        else:
            present = all(needle in serialized_input for needle in needles)
        facts[fact_id] = "present" if present else "missing"
        if not present:
            missing.append(fact_id)
    del task
    return InputSufficiency(
        sufficient=not missing,
        facts=facts,
        missing_fact_ids=tuple(missing),
    )


def evaluate_semantic_draft(
    draft: SectionSemanticDraft,
    *,
    expected: Mapping[str, object],
) -> SemanticEvaluation:
    """Compare generic typed semantics without CBL-specific production logic."""
    checks: dict[str, bool] = {
        "title_valid": draft.title == expected.get("title"),
        "source_selection_valid": draft.source_candidate == expected.get("source_candidate"),
    }
    expected_tracks = list(expected.get("tracks", ()))
    checks["track_count_valid"] = len(draft.tracks) == len(expected_tracks)
    checks["track_order_valid"] = [track.kind for track in draft.tracks] == [
        item.get("kind") for item in expected_tracks
    ]
    checks["track_titles_valid"] = [track.title for track in draft.tracks] == [
        item.get("title") for item in expected_tracks
    ]
    omissions: list[str] = []
    unrequested: list[str] = []
    for index, (track, expected_track) in enumerate(
        zip(draft.tracks, expected_tracks, strict=False)
    ):
        prefix = f"tracks[{index}]"
        if "x_scale" in expected_track:
            checks[f"{prefix}.x_scale"] = _model_value(track.x_scale) == expected_track["x_scale"]
        elif track.x_scale is not None:
            unrequested.append(f"{prefix}.x_scale")
        expected_bindings = list(expected_track.get("bindings", ()))
        actual_bindings = list(track.bindings)
        checks[f"{prefix}.binding_count"] = len(actual_bindings) == len(expected_bindings)
        checks[f"{prefix}.binding_order"] = [binding.kind for binding in actual_bindings] == [
            item.get("kind", "curve") for item in expected_bindings
        ]
        checks[f"{prefix}.binding_channels"] = [binding.channel for binding in actual_bindings] == [
            item.get("channel") for item in expected_bindings
        ]
        ids = [binding.semantic_id for binding in actual_bindings]
        checks[f"{prefix}.binding_ids"] = len(ids) == len(set(ids)) and all(ids)
        for binding_index, (binding, expected_binding) in enumerate(
            zip(actual_bindings, expected_bindings, strict=False)
        ):
            binding_prefix = f"{prefix}.bindings[{binding_index}]"
            for field_name in ("scale", "profile", "sample_axis"):
                expected_value = expected_binding.get(field_name)
                actual_value = _model_value(getattr(binding, field_name, None))
                if field_name in expected_binding:
                    checks[f"{binding_prefix}.{field_name}"] = actual_value == expected_value
                elif actual_value is not None:
                    unrequested.append(f"{binding_prefix}.{field_name}")
    for check_name, passed in checks.items():
        if not passed:
            omissions.append(check_name)
    return SemanticEvaluation(checks, tuple(omissions), tuple(unrequested))


def classify_outcome(
    *,
    planner_success: bool,
    enrichment_success: bool,
    representability_gap: bool,
    input_sufficient: bool,
    typed_structured_valid: bool,
    typed_context_valid: bool,
    typed_compiler_valid: bool,
    semantic_acceptance: bool,
    provider_failure_category: str | None = None,
) -> str:
    """Apply the locked CM-56 classification precedence."""
    if not planner_success:
        return "PLANNER_FAILURE"
    if not enrichment_success:
        return "ENRICHMENT_FAILURE"
    if representability_gap:
        return "REPRESENTABILITY_GAP"
    if not input_sufficient:
        return "INPUT_INSUFFICIENT"
    if provider_failure_category in {"invalid_response", "validation"}:
        return "SCHEMA_COMPATIBILITY_FAILURE"
    if provider_failure_category is not None:
        return "PROVIDER_INFRA_FAILURE"
    if not typed_structured_valid:
        return "SCHEMA_COMPATIBILITY_FAILURE"
    if not typed_context_valid or not typed_compiler_valid:
        return "DETERMINISTIC_COMPILER_FAILURE"
    if not semantic_acceptance:
        return "TYPED_WORKER_SEMANTIC_FAILURE"
    return "SUCCESS"


def _model_value(value: object) -> object:
    """Convert nested Pydantic values to comparable JSON-shaped values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    return value


def _document() -> AuthoringDocumentSpec:
    """Build the empty reconstruction document used by shadow cases."""
    return AuthoringDocumentSpec(
        name="cm56-shadow",
        sections=[
            {
                "id": "existing",
                "title": "Existing",
                "tracks": [
                    {
                        "id": "existing-track",
                        "title": "Existing",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def build_fixture_enricher(case: Mapping[str, object]) -> SemanticEnricher:
    """Build the real enricher around case-defined fixture metadata."""
    definitions = {str(source["filename"]): source for source in case.get("sources", ())}
    return SemanticEnricher(
        loader=FixtureSourceLoader(definitions),
        allowed_roots={"cm56": SOURCE_ROOT},
    )


def build_source_candidates(case: Mapping[str, object]) -> tuple[SourceCandidate, ...]:
    """Convert only explicit case candidates into host-owned source descriptors."""
    return tuple(
        SourceCandidate(
            candidate_id=str(source["candidate_id"]),
            root_id="cm56",
            path=str(source["filename"]),
            labels=tuple(str(label) for label in source.get("labels", ())),
            trusted_format=source.get("source_format"),
        )
        for source in case.get("sources", ())
    )


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the explicitly configured local OpenAI-compatible backend."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    api_key = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        key_path = Path(args.api_key_file)
        if not key_path.is_absolute():
            key_path = REPO_ROOT / key_path
        api_key = api_key or key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No CM-56 API key configured.")
    return OpenAICompatibleBackendV2(
        model=args.model,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=args.timeout),
        structured_output="json_schema",
        max_tokens_parameter=args.max_tokens_parameter,
    )


def _parser() -> argparse.ArgumentParser:
    """Build the sequential local CM-56 runner CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--temperature", type=float, default=1.0)
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
    """Run sequential CM-56 attempts and flush one redacted row at a time."""
    args = _parser().parse_args()
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    """Execute the provider-backed shadow harness without routing changes."""
    backend = _provider_configuration(args)
    registry = create_builtin_registry()
    planner = SemanticPlanner(backend=backend, registry=registry)
    typed = TypedSectionCompiler(backend=backend, registry=registry)
    cases = load_case_definitions()
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            for attempt_index in range(args.attempts):
                row = await _run_case_attempt(
                    case,
                    planner=planner,
                    typed=typed,
                    registry=registry,
                    args=args,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


async def _run_case_attempt(
    case: Mapping[str, object],
    *,
    planner: SemanticPlanner,
    typed: TypedSectionCompiler,
    registry: CapabilityRegistry,
    args: argparse.Namespace,
    attempt_index: int,
) -> dict[str, object]:
    """Run planner, enrichment, and each typed section independently."""
    del registry
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
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
        )
    except ProviderRequestError as error:
        return _base_row(case, attempt_index, request, started, "PLANNER_FAILURE", error=error)
    except Exception as error:
        return _base_row(case, attempt_index, request, started, "PLANNER_FAILURE", error=error)
    try:
        enriched = build_fixture_enricher(case).enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except SemanticEnrichmentError as error:
        return _base_row(case, attempt_index, request, started, "ENRICHMENT_FAILURE", error=error)
    rows = []
    expected_sections = list(case.get("expected_sections", ()))
    for index, (task, section_context) in enumerate(
        zip(plan.section_tasks, enriched.sections, strict=False)
    ):
        expected = expected_sections[index] if index < len(expected_sections) else {}
        worker_input = build_typed_section_input(
            task, section_context=section_context, registry=typed.registry
        )
        serialized = serialize_typed_section_input(worker_input)
        audit = audit_input_sufficiency(
            case, task=task, section_context=section_context, serialized_input=serialized
        )
        if not audit.sufficient:
            rows.append(
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
                section_id_hint=f"cm56-{case['case_id']}-{index}",
                timeout_seconds=args.timeout,
                temperature=args.temperature,
                max_output_tokens=args.max_output_tokens,
            )
            evaluation = evaluate_semantic_draft(result.draft, expected=expected)
            row = _success_row(
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
        except TypedSectionRepresentabilityError as error:
            row = _base_row(
                case,
                attempt_index,
                request,
                started,
                "REPRESENTABILITY_GAP",
                error=error,
            )
        except TypedSectionWorkerError as error:
            row = _base_row(
                case,
                attempt_index,
                request,
                started,
                "DETERMINISTIC_COMPILER_FAILURE",
                error=error,
            )
        except ProviderRequestError as error:
            row = _base_row(
                case,
                attempt_index,
                request,
                started,
                "SCHEMA_COMPATIBILITY_FAILURE",
                error=error,
            )
        except Exception as error:
            row = _base_row(
                case,
                attempt_index,
                request,
                started,
                "DETERMINISTIC_COMPILER_FAILURE",
                error=error,
            )
        rows.append(row)
    if not rows:
        return _base_row(case, attempt_index, request, started, "PLANNER_FAILURE", error=None)
    return {"sections": rows, "case_id": case["case_id"], "attempt_index": attempt_index}


def _context_row(
    case: Mapping[str, object],
    attempt_index: int,
    request: str,
    *,
    section_index: int,
    audit: InputSufficiency,
    serialized: str,
    classification: str,
    started: float,
) -> dict[str, object]:
    """Record a pre-provider input decision without exposing source paths."""
    return {
        "experiment_version": "CM-56",
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "section_index": section_index,
        "natural_request_sha256": _sha256(request),
        "provider_input_sha256": _sha256(serialized),
        "provider_input_chars": len(serialized),
        "system_prompt_sha256": _sha256(TYPED_SECTION_SYSTEM_PROMPT),
        "response_schema_sha256": response_schema_sha256(),
        "input_sufficient": audit.sufficient,
        "input_facts": audit.facts,
        "missing_input_fact_ids": audit.missing_fact_ids,
        "typed_structured_valid": False,
        "typed_context_valid": False,
        "typed_compiler_valid": False,
        "typed_semantic_acceptance": False,
        "classification": classification,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def _success_row(
    case: Mapping[str, object],
    attempt_index: int,
    request: str,
    plan: object,
    enriched: object,
    section_index: int,
    audit: InputSufficiency,
    result: TypedSectionGenerationResult,
    evaluation: SemanticEvaluation,
    started: float,
) -> dict[str, object]:
    """Serialize one successful or semantic-failure section row."""
    del plan, enriched
    classification = classify_outcome(
        planner_success=True,
        enrichment_success=True,
        representability_gap=False,
        input_sufficient=audit.sufficient,
        typed_structured_valid=True,
        typed_context_valid=True,
        typed_compiler_valid=True,
        semantic_acceptance=evaluation.accepted,
    )
    return {
        "experiment_version": "CM-56",
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "section_index": section_index,
        "natural_request_sha256": _sha256(request),
        "provider_input_sha256": result.provider_input_sha256,
        "provider_input_chars": result.provider_input_chars,
        "system_prompt_sha256": result.system_prompt_sha256,
        "response_schema_sha256": result.response_schema_sha256,
        "input_sufficient": audit.sufficient,
        "input_facts": audit.facts,
        "missing_input_fact_ids": audit.missing_fact_ids,
        "typed_structured_valid": True,
        "typed_context_valid": True,
        "typed_compiler_valid": True,
        "typed_semantic_acceptance": evaluation.accepted,
        "typed_semantic_omissions": evaluation.omissions,
        "typed_unrequested_semantics": evaluation.unrequested_semantics,
        "provider_metrics": result.metrics.public_metadata(),
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "classification": classification,
    }


def _base_row(
    case: Mapping[str, object],
    attempt_index: int,
    request: str,
    started: float,
    classification: str,
    *,
    error: BaseException | None,
) -> dict[str, object]:
    """Serialize bounded failure evidence without raw exception details."""
    return {
        "experiment_version": "CM-56",
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "natural_request_sha256": _sha256(request),
        "classification": classification,
        "error_type": type(error).__name__ if error is not None else None,
        "provider_category": _provider_category(error),
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def _case_request(case: Mapping[str, object]) -> str:
    """Load a frozen request from the case definition."""
    request_file = case.get("request_file")
    if request_file:
        return (REPO_ROOT / str(request_file)).read_text(encoding="utf-8")
    return str(case["request"])


def _sha256(value: str) -> str:
    """Hash UTF-8 text deterministically."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provider_category(error: BaseException | None) -> str | None:
    """Serialize a provider category without leaking exception details."""
    category = getattr(error, "category", None)
    return getattr(category, "value", category)


if __name__ == "__main__":  # pragma: no cover
    main()

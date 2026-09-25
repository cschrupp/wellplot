"""CM-57C pre-live audit and future production typed-worker shadow runner."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from scripts.cm56_post_r4_typed_shadow import production_source_summary
from scripts.cm56_typed_section_shadow import (
    _document,
    build_fixture_enricher,
    build_source_candidates,
)
from scripts.cm56_typed_section_shadow import (
    load_case_definitions as load_cm56_cases,
)
from scripts.cm56r8r_semantic_contract_correction import (
    _scientific_family,
    evaluate_semantic_draft_r8r,
    evaluator_source_sha256,
)
from wellplot.agent.code_mode.enrichment import SemanticEnrichmentError
from wellplot.agent.code_mode.planner import (
    PlannerSemanticFailure,
    SemanticPlan,
    SemanticPlanner,
)
from wellplot.agent.code_mode.section_semantics import (
    SectionSemanticDraft,
    SectionSemanticValidationError,
    SemanticScale,
)
from wellplot.agent.code_mode.semantic_section_compiler import SectionSemanticCompilationError
from wellplot.agent.code_mode.typed_section_worker import (
    RESPONSE_SCHEMA_SHA256,
    TYPED_SECTION_PROVIDER_INPUT_VERSION,
    TYPED_SECTION_SYSTEM_PROMPT,
    TypedSectionCompiler,
    TypedSectionRepresentabilityError,
    TypedSectionWorkerError,
    build_typed_section_provider_input,
    build_typed_section_system_prompt,
    response_schema_sha256,
    serialize_typed_section_provider_input,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57c_shadow_cases.json"
OLD_CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm56_shadow_cases.json"
SOURCE_ROOT = REPO_ROOT / "tests/fixtures/typed_worker/cm56_sources"
OUTPUT_PATH = Path("/tmp/cm57c-live-qwen.jsonl")
DESIGN_BASELINE_SHA = "639332ddb4258569fedd65155eafaf5c220eb6b2"
EXPERIMENT_VERSION = "CM-57C"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
WORKER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
EVALUATOR_VERSION = "cm56r8r.corrected-evaluator.v1"
EXPECTED_EVALUATOR_SHA256 = "4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49"
EXPECTED_METADATA_SHA256 = "67aa2d6f579343e60f9261eb654fd62bde21605b1c8c68f080b5b74ff01c3f46"
EXPECTED_PROMPT_SHA256 = {
    False: "7e519241911d3fbd61d8de4134c71ae69b98646a6b4e5a4ea61ba0a7a0318f69",
    True: "10ed56fc716165dca783f6d92805b7541f63b4044dcbcd4ac0207191f0771a80",
}
EXPECTED_BASE_PROMPT_SHA256 = "19b0e289d2fa8ea362840aa94d90ad43cdea5b2ebdc866363df1ef28a38f2d49"
EXPECTED_CASE_FAMILIES = {
    "generic_curve",
    "reference_track",
    "repeated_channel",
    "source_selection",
    "generic_raster",
    "waveform_raster",
    "vdl_raster",
    "partial_sample_axis",
    "independent_sample_bounds",
    "negative_no_profile",
    "multi_raster",
    "mixed_curve_raster",
}
PROTECTED_GENERIC_CATEGORIES = {
    "generic_curve",
    "reference_track",
    "repeated_channel",
    "source_selection",
}
RASTER_TARGET_CATEGORIES = {
    "generic_raster",
    "waveform_raster",
    "vdl_raster",
    "partial_sample_axis",
    "independent_sample_bounds",
    "multi_raster",
    "mixed_curve_raster",
}
REGRESSION_FAMILIES = frozenset(
    {
        "source_selection",
        "topology",
        "track_scale",
        "binding_scale",
        "multiplicity",
        "scientific_extras",
    }
)
TARGET_FAMILIES = frozenset({"raster_profile", "sample_axis"})
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
GUARDED_FILES = (
    "scripts/cm57c_shadow_generalization.py",
    "tests/fixtures/typed_worker/cm57c_shadow_cases.json",
    "src/wellplot/agent/code_mode/typed_section_worker.py",
    "src/wellplot/agent/code_mode/planner.py",
    "scripts/cm56r8r_semantic_contract_correction.py",
    "tests/fixtures/typed_worker/cm56_shadow_cases.json",
)
GUARDED_DIRECTORIES = ("tests/fixtures/typed_worker/cm56_sources",)


@dataclass
class CountingBackend(ModelBackendProtocol):
    """Count calls while delegating the unchanged provider protocol."""

    delegate: ModelBackendProtocol
    structured_calls: int = 0
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Count and delegate a structured request."""
        self.structured_calls += 1
        return await self.delegate.generate_structured(request, response_model=response_model)

    async def generate_program(self, request: object) -> object:
        """Count and delegate legacy program requests for diagnostics."""
        self.program_calls += 1
        return await self.delegate.generate_program(request)  # type: ignore[arg-type]


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    """Hash exact artifact bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash UTF-8 text."""
    return sha256_bytes(value.encode("utf-8"))


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact by exact bytes."""
    return sha256_bytes(path.read_bytes())


def validate_authorized_checkpoint(value: object) -> str:
    """Require the full lowercase SHA used to authorize live execution."""
    if not isinstance(value, str) or CHECKPOINT_RE.fullmatch(value) is None:
        raise ValueError("CM-57C requires a full lowercase 40-character checkpoint SHA.")
    return value


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a local Git command."""
    return subprocess.check_output(
        ["git", *arguments],
        cwd=REPO_ROOT,
        stderr=subprocess.STDOUT,
    )


def current_checkout_sha() -> str:
    """Return the current checkout's full commit SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _guarded_paths_at_commit(checkpoint: str) -> tuple[str, ...]:
    """Return all tracked files covered by the reviewed artifact guard."""
    paths = list(GUARDED_FILES)
    for directory in GUARDED_DIRECTORIES:
        output = _git_output("ls-tree", "-r", "--name-only", checkpoint, "--", directory)
        paths.extend(line for line in output.decode().splitlines() if line)
    return tuple(sorted(set(paths)))


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Reject a live run unless checkout and guarded artifacts match the review SHA."""
    checkpoint = validate_authorized_checkpoint(checkpoint)
    if current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57C checkout does not match the authorized checkpoint.")
    guarded_paths = _guarded_paths_at_commit(checkpoint)
    for relative_path in guarded_paths:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            raise RuntimeError(f"CM-57C guarded artifact is missing: {relative_path}")
        expected = _git_output("show", f"{checkpoint}:{relative_path}")
        if path.read_bytes() != expected:
            raise RuntimeError(f"CM-57C guarded artifact drifted: {relative_path}")
    for directory in GUARDED_DIRECTORIES:
        root = REPO_ROOT / directory
        current_paths = tuple(
            sorted(str(path.relative_to(REPO_ROOT)) for path in root.rglob("*") if path.is_file())
        )
        expected_paths = tuple(path for path in guarded_paths if path.startswith(f"{directory}/"))
        if current_paths != expected_paths:
            raise RuntimeError(f"CM-57C guarded directory drifted: {directory}")


def load_case_definitions(path: Path = CASE_PATH) -> tuple[dict[str, object], ...]:
    """Load and structurally validate the CM-57C corpus."""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("version") != "cm57c.shadow.v1":
        raise ValueError("Unexpected CM-57C corpus version.")
    cases = artifact.get("cases")
    if not isinstance(cases, list):
        raise ValueError("CM-57C corpus must contain a cases list.")
    return tuple(cases)


def _source_for_case(case: Mapping[str, object], candidate_id: str) -> Mapping[str, object]:
    """Return one declared source definition by opaque candidate ID."""
    for source in case.get("sources", ()):
        if source.get("candidate_id") == candidate_id:
            return source
    raise ValueError(f"Unknown expected source candidate {candidate_id!r}.")


def _gold_model(case: Mapping[str, object]) -> SectionSemanticDraft:
    """Validate one expected section through the production semantic models."""
    expected_sections = case.get("expected_sections", ())
    if not isinstance(expected_sections, list) or len(expected_sections) != 1:
        raise ValueError(f"Case {case.get('case_id')!r} must contain one expected section.")
    raw = json.loads(json.dumps(expected_sections[0]))
    raw["tracks"] = list(raw.get("tracks", ()))
    for track_index, track in enumerate(raw["tracks"]):
        track["semantic_id"] = f"gold-track-{track_index}"
        track["bindings"] = list(track.get("bindings", ()))
        for binding_index, binding in enumerate(track["bindings"]):
            binding["semantic_id"] = f"gold-binding-{track_index}-{binding_index}"
            if track["kind"] in {"normal", "reference"}:
                binding.setdefault("kind", "curve")
            else:
                binding.setdefault("kind", "raster")
    return SectionSemanticDraft.model_validate(raw)


def _number_text(value: object) -> str:
    """Format a gold number for request provenance checks."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _semantic_tuples(case: Mapping[str, object]) -> set[str]:
    """Extract normalized semantic tuples for old-corpus overlap auditing."""
    tuples: set[str] = set()
    for track in case["expected_sections"][0]["tracks"]:
        if "x_scale" in track:
            tuples.add(canonical_json({"x_scale": track["x_scale"]}))
        for binding in track["bindings"]:
            for field in ("scale", "sample_axis"):
                if field in binding:
                    tuples.add(canonical_json({field: binding[field]}))
    return tuples


def _audit_request_gold_consistency(case: Mapping[str, object]) -> None:
    """Require each scored scientific fact to be explicit in the request/context."""
    request = str(case["request"])
    request_lower = request.casefold()
    expected = _gold_model(case)
    source = _source_for_case(case, expected.source_candidate)
    source_labels = [str(label).casefold() for label in source.get("labels", ())]
    if not any(label and label in request_lower for label in source_labels):
        raise ValueError(f"Case {case['case_id']!r} does not identify its expected source.")
    channels = {str(channel["mnemonic"]) for channel in source.get("channels", ())}
    for track in expected.tracks:
        for binding in track.bindings:
            if binding.channel not in request:
                raise ValueError(f"Case {case['case_id']!r} hides channel {binding.channel!r}.")
            if binding.channel not in channels:
                raise ValueError(f"Case {case['case_id']!r} uses an undeclared channel.")
            if getattr(binding, "profile", None) is not None:
                profile = str(binding.profile.value)
                if profile not in request_lower:
                    raise ValueError(f"Case {case['case_id']!r} hides raster profile {profile!r}.")
            for value in _binding_numeric_values(binding):
                if _number_text(value) not in request:
                    raise ValueError(f"Case {case['case_id']!r} hides numeric semantic {value!r}.")
        if track.x_scale is not None:
            for value in (track.x_scale.minimum, track.x_scale.maximum):
                if _number_text(value) not in request:
                    raise ValueError(f"Case {case['case_id']!r} hides x-scale value {value!r}.")
    if "log" in _gold_scale_kinds(case) and "log" not in request_lower:
        raise ValueError(f"Case {case['case_id']!r} hides logarithmic scale semantics.")
    if "tangential" in _gold_scale_kinds(case) and "tangential" not in request_lower:
        raise ValueError(f"Case {case['case_id']!r} hides tangential scale semantics.")
    if any(scale.reverse for scale in _gold_scales(case)) and "reverse" not in request_lower:
        raise ValueError(f"Case {case['case_id']!r} hides reverse scale semantics.")
    if case["category"] == "negative_no_profile":
        if "do not choose a raster profile" not in request_lower:
            raise ValueError("The negative profile case must explicitly omit profile choice.")
        if "do not add sample-axis settings" not in request_lower:
            raise ValueError("The negative profile case must explicitly omit sample-axis settings.")


def _binding_numeric_values(binding: object) -> tuple[object, ...]:
    """Return numeric values from one validated binding."""
    values: list[object] = []
    scale = getattr(binding, "scale", None)
    if scale is not None:
        values.extend((scale.minimum, scale.maximum))
    axis = getattr(binding, "sample_axis", None)
    if axis is not None:
        values.extend(
            value
            for value in (
                axis.source_origin,
                axis.source_step,
                axis.minimum,
                axis.maximum,
                axis.tick_count,
            )
            if value is not None
        )
    return tuple(values)


def _gold_scales(case: Mapping[str, object]) -> tuple[SemanticScale, ...]:
    """Return all validated scale objects in one expected section."""
    expected = _gold_model(case)
    scales: list[SemanticScale] = []
    for track in expected.tracks:
        if track.x_scale is not None:
            scales.append(track.x_scale)
        for binding in track.bindings:
            scale = getattr(binding, "scale", None)
            if scale is not None:
                scales.append(scale)
    return tuple(scales)


def _gold_scale_kinds(case: Mapping[str, object]) -> set[str]:
    """Return the explicit scale kinds in one expected section."""
    return {scale.kind.value for scale in _gold_scales(case)}


def audit_corpus(
    cases: Sequence[Mapping[str, object]],
    *,
    registry: CapabilityRegistry | None = None,
) -> dict[str, object]:
    """Run all deterministic corpus, gold, provenance, and anti-leakage audits."""
    registry = registry or create_builtin_registry()
    old_cases = load_cm56_cases(OLD_CASE_PATH)
    old_ids = {str(case["case_id"]) for case in old_cases}
    old_requests = {str(case["request"]) for case in old_cases}
    ids = [str(case["case_id"]) for case in cases]
    requests = [str(case["request"]) for case in cases]
    if len(cases) != 16:
        raise ValueError("CM-57C requires exactly 16 cases.")
    if len(set(ids)) != len(ids) or len(set(requests)) != len(requests):
        raise ValueError("CM-57C case IDs and requests must be unique.")
    if set(ids) & old_ids or set(requests) & old_requests:
        raise ValueError("CM-57C reuses a closed CM-56 case ID or request.")
    if {str(case["category"]) for case in cases} != EXPECTED_CASE_FAMILIES:
        raise ValueError("CM-57C case-family coverage is incomplete or unexpected.")
    old_tuples = set().union(*(_semantic_tuples(case) for case in old_cases))
    tuple_overlaps: dict[str, int] = {}
    for case in cases:
        for source in case.get("sources", ()):
            if not (SOURCE_ROOT / str(source["filename"])).is_file():
                raise ValueError(f"Missing CM-57C source fixture {source['filename']!r}.")
        candidate_ids = [str(source["candidate_id"]) for source in case.get("sources", ())]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError(f"Case {case['case_id']!r} repeats a source candidate ID.")
        capabilities = tuple(str(value) for value in case["expected_capabilities"])
        if len(set(capabilities)) != len(capabilities):
            raise ValueError(f"Case {case['case_id']!r} repeats a capability ID.")
        for capability_id in capabilities:
            registry.get(capability_id)
        _gold_model(case)
        _audit_request_gold_consistency(case)
        overlaps = _semantic_tuples(case) & old_tuples
        if overlaps:
            tuple_overlaps[str(case["case_id"])] = len(overlaps)
    if tuple_overlaps:
        raise ValueError(f"CM-57C reuses old semantic tuples: {tuple_overlaps!r}.")
    return {
        "case_count": len(cases),
        "case_ids": ids,
        "request_count": len(requests),
        "old_case_id_overlap": False,
        "old_request_overlap": False,
        "semantic_tuple_overlap_count": 0,
        "case_families": sorted(EXPECTED_CASE_FAMILIES),
    }


def audit_input_sufficiency(
    case: Mapping[str, object],
    *,
    serialized_input: str,
) -> dict[str, object]:
    """Check declared fact provenance against the actual production payload."""
    facts: dict[str, str] = {}
    missing: list[str] = []
    request = str(case["request"])
    for fact_id, raw_fact in dict(case.get("input_facts", {})).items():
        fact = dict(raw_fact)
        source = str(fact.get("source", "request"))
        haystack = request if source == "request" else serialized_input
        needles = tuple(str(value) for value in fact.get("needles", ()))
        present = all(needle in haystack for needle in needles)
        facts[str(fact_id)] = "present" if present else "missing"
        if not present:
            missing.append(str(fact_id))
    return {
        "sufficient": not missing,
        "facts": facts,
        "missing_fact_ids": sorted(missing),
    }


def _strip_semantic_ids(value: object) -> object:
    """Remove only local semantic IDs for repeatability comparison."""
    if isinstance(value, dict):
        return {
            key: _strip_semantic_ids(item) for key, item in value.items() if key != "semantic_id"
        }
    if isinstance(value, list):
        return [_strip_semantic_ids(item) for item in value]
    return value


def evaluate_draft(
    draft: SectionSemanticDraft,
    *,
    expected: Mapping[str, object],
) -> dict[str, object]:
    """Wrap the corrected generic evaluator with CM-57C primary gates."""
    evaluation = evaluate_semantic_draft_r8r(draft, expected=expected)
    title_paths = {"title_valid", "track_titles_valid"}
    title_statuses = {
        path: "PASS" if passed else "WRONG_VALUE"
        for path, passed in evaluation.checks.items()
        if path in title_paths
    }
    scientific_statuses = {
        path: "PASS" if passed else "WRONG_VALUE"
        for path, passed in evaluation.checks.items()
        if path not in title_paths
    }
    scientific_statuses.update(
        {
            path: status
            for path, status in evaluation.leaf_statuses.items()
            if path not in title_paths
        }
    )
    family_counts: dict[str, dict[str, int]] = {}
    for path, status in scientific_statuses.items():
        family = _family_for_path(path)
        counts = family_counts.setdefault(family, {"pass": 0, "fail": 0})
        counts["pass" if status == "PASS" else "fail"] += 1
    if evaluation.unrequested_semantics:
        counts = family_counts.setdefault("scientific_extras", {"pass": 0, "fail": 0})
        counts["fail"] += len(evaluation.unrequested_semantics)
    scientific_acceptance = (
        all(status == "PASS" for status in scientific_statuses.values())
        and not evaluation.unrequested_semantics
    )
    return {
        "leaf_statuses": evaluation.leaf_statuses,
        "scientific_family_counts": family_counts,
        "scientific_acceptance": scientific_acceptance,
        "full_semantic_acceptance": evaluation.accepted and all(evaluation.checks.values()),
        "title_fidelity": all(status == "PASS" for status in title_statuses.values()),
        "title_statuses": title_statuses,
        "unrequested_scientific_semantics": evaluation.unrequested_semantics,
        "semantic_projection": _strip_semantic_ids(draft.model_dump(mode="json")),
    }


def _family_for_path(path: str) -> str:
    """Classify corrected evaluator leaves into CM-57C reporting families."""
    if path == "source_selection_valid":
        return "source_selection"
    if path in {
        "track_count_valid",
        "track_order_valid",
        "binding_count_valid",
        "binding_order_valid",
    }:
        return "topology"
    family = _scientific_family(path)
    if family is not None:
        return family
    if "binding_channels" in path or "binding_ids" in path:
        return "multiplicity"
    return "topology"


def _provider_category(error: BaseException | None) -> str | None:
    """Project only a bounded provider category into evidence."""
    category = getattr(error, "category", None)
    return getattr(category, "value", category)


def _pipeline_class(error: BaseException | None) -> str:
    """Map known failures to the locked CM-57C pipeline stages."""
    if isinstance(error, ProviderRequestError):
        if error.category in {
            ProviderFailureCategory.INVALID_RESPONSE,
            ProviderFailureCategory.VALIDATION,
        }:
            return "SCHEMA_COMPATIBILITY_FAILURE"
        return "PROVIDER_INFRA_FAILURE"
    if isinstance(error, ValidationError):
        return "SCHEMA_COMPATIBILITY_FAILURE"
    if isinstance(error, SemanticEnrichmentError):
        return "ENRICHMENT_FAILURE"
    if isinstance(error, SectionSemanticValidationError):
        return "CONTEXT_VALIDATION_FAILURE"
    if isinstance(error, SectionSemanticCompilationError):
        return "SEMANTIC_COMPILER_FAILURE"
    if isinstance(error, (TypedSectionWorkerError, TypedSectionRepresentabilityError)):
        return "SEMANTIC_COMPILER_FAILURE"
    if isinstance(error, (PlannerSemanticFailure, ValueError)):
        return "PLANNER_FAILURE"
    return "SEMANTIC_COMPILER_FAILURE"


def _base_row(
    case: Mapping[str, object],
    *,
    attempt_index: int,
    planner_calls: int,
    pipeline_class: str,
    authorized_checkpoint: str = DESIGN_BASELINE_SHA,
    error: BaseException | None = None,
    plan: SemanticPlan | None = None,
    enriched: object | None = None,
) -> dict[str, object]:
    """Build bounded failure evidence without raw requests or paths."""
    selected = ()
    channels = ()
    if enriched is not None and getattr(enriched, "sections", ()):
        context = enriched.sections[0]
        selected = tuple(source.candidate_id for source in context.sources)
        channels = tuple(
            channel.mnemonic for source in context.sources for channel in source.channels
        )
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": DESIGN_BASELINE_SHA,
        "authorized_checkpoint": authorized_checkpoint,
        "case_id": case["case_id"],
        "category": case["category"],
        "attempt_index": attempt_index,
        "planner_success": plan is not None,
        "planner_provider_calls": planner_calls,
        "planner_correction_used": planner_calls > 1,
        "planner_capabilities": (
            list(plan.section_tasks[0].capability_ids)
            if plan is not None and len(plan.section_tasks) == 1
            else []
        ),
        "planner_capability_match": False,
        "enrichment_success": enriched is not None,
        "selected_source_candidates": list(selected),
        "available_channels": list(channels),
        "pipeline_class": pipeline_class,
        "error_type": type(error).__name__ if error else None,
        "provider_category": _provider_category(error),
        "scientific_acceptance": False,
        "full_semantic_acceptance": False,
    }


async def run_case_attempt(
    case: Mapping[str, object],
    *,
    planner: SemanticPlanner,
    typed: TypedSectionCompiler,
    registry: CapabilityRegistry,
    attempt_index: int,
    authorized_checkpoint: str = DESIGN_BASELINE_SHA,
    enricher_factory: object = build_fixture_enricher,
) -> dict[str, object]:
    """Run one real planner/enricher/provider-input/typed-worker attempt."""
    started = time.perf_counter()
    request = str(case["request"])
    backend = getattr(planner, "backend", None)
    planner_before = int(getattr(backend, "structured_calls", 0))
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
    except Exception as error:
        planner_calls = int(getattr(backend, "structured_calls", 0)) - planner_before
        row = _base_row(
            case,
            attempt_index=attempt_index,
            planner_calls=planner_calls,
            pipeline_class=_pipeline_class(error),
            authorized_checkpoint=authorized_checkpoint,
            error=error,
        )
        row["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return row

    planner_calls = int(getattr(backend, "structured_calls", 0)) - planner_before
    expected_capabilities = tuple(str(value) for value in case["expected_capabilities"])
    planner_capabilities = (
        tuple(plan.section_tasks[0].capability_ids) if len(plan.section_tasks) == 1 else ()
    )
    if plan.report_task is not None or len(plan.section_tasks) != 1 or plan.unresolved_requirements:
        row = _base_row(
            case,
            attempt_index=attempt_index,
            planner_calls=planner_calls,
            pipeline_class="PLANNER_FAILURE",
            authorized_checkpoint=authorized_checkpoint,
            plan=plan,
        )
        row["planner_capabilities"] = list(planner_capabilities)
        row["planner_capability_match"] = False
        row["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return row
    planner_capability_match = set(planner_capabilities) == set(expected_capabilities) and len(
        planner_capabilities
    ) == len(set(planner_capabilities))
    if not planner_capability_match:
        row = _base_row(
            case,
            attempt_index=attempt_index,
            planner_calls=planner_calls,
            pipeline_class="PLANNER_FAILURE",
            authorized_checkpoint=authorized_checkpoint,
            plan=plan,
        )
        row["planner_capabilities"] = list(planner_capabilities)
        row["planner_capability_match"] = False
        row["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return row

    try:
        enricher = enricher_factory(case)
        enriched = enricher.enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except Exception as error:
        row = _base_row(
            case,
            attempt_index=attempt_index,
            planner_calls=planner_calls,
            pipeline_class="ENRICHMENT_FAILURE",
            authorized_checkpoint=authorized_checkpoint,
            error=error,
            plan=plan,
        )
        row["planner_capabilities"] = list(planner_capabilities)
        row["planner_capability_match"] = True
        row["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return row
    if len(enriched.sections) != 1 or enriched.sections[0].section_id is not None:
        row = _base_row(
            case,
            attempt_index=attempt_index,
            planner_calls=planner_calls,
            pipeline_class="ENRICHMENT_FAILURE",
            authorized_checkpoint=authorized_checkpoint,
            plan=plan,
            enriched=enriched,
        )
        row["planner_capabilities"] = list(planner_capabilities)
        row["planner_capability_match"] = True
        row["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return row

    task = plan.section_tasks[0]
    context = enriched.sections[0]
    expected = case["expected_sections"][0]
    base = _base_row(
        case,
        attempt_index=attempt_index,
        planner_calls=planner_calls,
        pipeline_class="SUCCESS",
        authorized_checkpoint=authorized_checkpoint,
        plan=plan,
        enriched=enriched,
    )
    base.update(
        {
            "planner_capabilities": list(planner_capabilities),
            "planner_capability_match": True,
            "typed_structured_valid": False,
            "typed_context_valid": False,
            "typed_compiler_valid": False,
        }
    )
    try:
        provider_input = build_typed_section_provider_input(
            task,
            authoritative_request=request,
            section_context=context,
            registry=registry,
        )
        serialized = serialize_typed_section_provider_input(provider_input)
        input_audit = audit_input_sufficiency(case, serialized_input=serialized)
    except Exception as error:
        base["pipeline_class"] = _pipeline_class(error)
        base["error_type"] = type(error).__name__
        base["provider_category"] = _provider_category(error)
        base["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return base
    base.update(
        {
            "input_sufficiency": input_audit,
            "missing_input_facts": input_audit["missing_fact_ids"],
            "provider_input_version": TYPED_SECTION_PROVIDER_INPUT_VERSION,
            "provider_input_sha256": sha256_text(serialized),
            "provider_input_chars": len(serialized),
            "system_prompt_sha256": sha256_text(
                build_typed_section_system_prompt(
                    has_semantic_contracts=bool(provider_input.semantic_contracts)
                )
            ),
            "response_schema_sha256": response_schema_sha256(),
            "semantic_metadata_applicable": bool(provider_input.semantic_contracts),
        }
    )
    if not input_audit["sufficient"]:
        base["pipeline_class"] = "INPUT_INSUFFICIENT"
        base["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return base

    worker_before = int(getattr(backend, "structured_calls", 0))
    try:
        result = await typed.compile(
            task=task,
            section_context=context,
            document=document,
            section_id_hint=f"cm57c-{case['case_id']}",
            authoritative_request=request,
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=WORKER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except Exception as error:
        base["pipeline_class"] = _pipeline_class(error)
        base["worker_provider_calls"] = int(getattr(backend, "structured_calls", 0)) - worker_before
        base["error_type"] = type(error).__name__
        base["provider_category"] = _provider_category(error)
        base["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return base
    evaluation = evaluate_draft(result.draft, expected=expected)
    base.update(
        {
            "worker_provider_calls": int(getattr(backend, "structured_calls", 0)) - worker_before,
            "typed_structured_valid": True,
            "typed_context_valid": True,
            "typed_compiler_valid": True,
            "provider_input_sha256": result.provider_input_sha256,
            "provider_input_chars": result.provider_input_chars,
            "system_prompt_sha256": result.system_prompt_sha256,
            "response_schema_sha256": result.response_schema_sha256,
            "provider_metrics": result.metrics.public_metadata(),
            "draft": result.draft.model_dump(mode="json"),
            **{key: value for key, value in evaluation.items() if key != "semantic_projection"},
            "semantic_projection": evaluation["semantic_projection"],
        }
    )
    base["pipeline_class"] = "SUCCESS"
    base["elapsed_ms"] = (time.perf_counter() - started) * 1000
    return base


def _population_integrity(
    rows: Sequence[Mapping[str, object]],
    cases: Sequence[Mapping[str, object]],
    *,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Require exactly two complete rows for each of the 16 cases."""
    expected = {(case["case_id"], attempt) for case in cases for attempt in range(ATTEMPTS)}
    actual = {(row.get("case_id"), row.get("attempt_index")) for row in rows}
    reasons: list[str] = []
    if len(rows) != 32:
        reasons.append("row_count")
    if len(actual) != len(rows):
        reasons.append("duplicate_case_attempt")
    if actual != expected:
        reasons.append("missing_or_unexpected_case_attempt")
    for row in rows:
        if row.get("authorized_checkpoint") != authorized_checkpoint:
            reasons.append("checkpoint_mismatch")
    return {
        "complete": not reasons,
        "reasons": sorted(set(reasons)),
        "actual_rows": len(rows),
        "expected_checkpoint": authorized_checkpoint,
    }


def _failed_scientific_families(row: Mapping[str, object]) -> set[str]:
    """Return families with at least one failed scientific leaf."""
    counts = row.get("scientific_family_counts")
    if not isinstance(counts, Mapping):
        return set()
    failed: set[str] = set()
    for family, value in counts.items():
        if isinstance(value, Mapping) and int(value.get("fail", 0)) > 0:
            failed.add(str(family))
    return failed


def _repeatability_summary(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Compare the two semantic projections for each case without statistics."""
    by_case: dict[str, list[Mapping[str, object]]] = {}
    for row in rows:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    cases: dict[str, dict[str, object]] = {}
    stable: list[str] = []
    unstable: list[str] = []
    unavailable: list[str] = []
    for case_id, case_rows in sorted(by_case.items()):
        projections = [row.get("semantic_projection") for row in case_rows]
        if len(projections) != ATTEMPTS or any(projection is None for projection in projections):
            same: bool | None = None
            unavailable.append(case_id)
        else:
            same = projections[0] == projections[1]
            (stable if same else unstable).append(case_id)
        cases[case_id] = {
            "attempt_count": len(case_rows),
            "same_semantic_projection": same,
        }
    return {
        "cases": cases,
        "stable_cases": stable,
        "unstable_cases": unstable,
        "unavailable_cases": unavailable,
    }


def _final_decision(
    rows: Sequence[Mapping[str, object]],
    cases: Sequence[Mapping[str, object]],
    *,
    authorized_checkpoint: str,
) -> str:
    """Apply CM-57C decision precedence without aggregate thresholds."""
    population = _population_integrity(
        rows,
        cases,
        authorized_checkpoint=authorized_checkpoint,
    )
    if not population["complete"]:
        return "INCONCLUSIVE_GENERALIZATION"
    if any(row.get("pipeline_class") == "PROVIDER_INFRA_FAILURE" for row in rows):
        return "INCONCLUSIVE_GENERALIZATION"
    pipeline_failures = {
        "PLANNER_FAILURE",
        "ENRICHMENT_FAILURE",
        "INPUT_INSUFFICIENT",
        "SCHEMA_COMPATIBILITY_FAILURE",
        "CONTEXT_VALIDATION_FAILURE",
        "SEMANTIC_COMPILER_FAILURE",
    }
    if any(row.get("pipeline_class") in pipeline_failures for row in rows):
        return "GENERALIZATION_PIPELINE_FAILURE"
    successful_rows = [row for row in rows if row.get("pipeline_class") == "SUCCESS"]
    for row in successful_rows:
        failed_families = _failed_scientific_families(row)
        if failed_families & REGRESSION_FAMILIES:
            return "GENERALIZATION_REGRESSION"
        if not row.get("scientific_acceptance", False) and not failed_families:
            return "GENERALIZATION_REGRESSION"
        if failed_families - TARGET_FAMILIES:
            return "GENERALIZATION_REGRESSION"
    if any(_failed_scientific_families(row) & TARGET_FAMILIES for row in successful_rows):
        return "GENERALIZATION_TARGET_GAP"
    return "GENERALIZATION_VALIDATED"


def summarize_population(
    rows: Sequence[Mapping[str, object]],
    cases: Sequence[Mapping[str, object]],
    *,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Summarize immutable raw rows after a complete future population."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": DESIGN_BASELINE_SHA,
        "authorized_checkpoint": authorized_checkpoint,
        "population_integrity": _population_integrity(
            rows,
            cases,
            authorized_checkpoint=authorized_checkpoint,
        ),
        "repeatability": _repeatability_summary(rows),
        "decision": _final_decision(
            rows,
            cases,
            authorized_checkpoint=authorized_checkpoint,
        ),
    }


def _self_test_decisions(cases: Sequence[Mapping[str, object]]) -> None:
    """Exercise all final labels with synthetic evidence populations."""
    checkpoint = "a" * 40
    complete = [
        {
            "case_id": case["case_id"],
            "category": case["category"],
            "attempt_index": attempt,
            "authorized_checkpoint": checkpoint,
            "input_sufficiency": {"sufficient": True},
            "pipeline_class": "SUCCESS",
            "scientific_acceptance": True,
            "unrequested_scientific_semantics": (),
            "scientific_family_counts": {},
        }
        for case in cases
        for attempt in range(ATTEMPTS)
    ]
    assert _final_decision(complete, cases, authorized_checkpoint=checkpoint) == (
        "GENERALIZATION_VALIDATED"
    )
    target_gap = [dict(row) for row in complete]
    for row in target_gap:
        if row["category"] == "generic_raster":
            row["scientific_acceptance"] = False
            row["scientific_family_counts"] = {"raster_profile": {"pass": 0, "fail": 1}}
    assert (
        _final_decision(
            target_gap,
            cases,
            authorized_checkpoint=checkpoint,
        )
        == "GENERALIZATION_TARGET_GAP"
    )
    regression = [dict(row) for row in complete]
    regression[0]["scientific_acceptance"] = False
    regression[0]["scientific_family_counts"] = {"binding_scale": {"pass": 0, "fail": 1}}
    assert (
        _final_decision(
            regression,
            cases,
            authorized_checkpoint=checkpoint,
        )
        == "GENERALIZATION_REGRESSION"
    )
    pipeline = [dict(row) for row in complete]
    pipeline[0]["pipeline_class"] = "SCHEMA_COMPATIBILITY_FAILURE"
    assert (
        _final_decision(
            pipeline,
            cases,
            authorized_checkpoint=checkpoint,
        )
        == "GENERALIZATION_PIPELINE_FAILURE"
    )
    infra = [dict(row) for row in complete]
    infra[0]["pipeline_class"] = "PROVIDER_INFRA_FAILURE"
    assert (
        _final_decision(
            infra,
            cases,
            authorized_checkpoint=checkpoint,
        )
        == "INCONCLUSIVE_GENERALIZATION"
    )


def prelive_report() -> dict[str, object]:
    """Run all no-provider CM-57C audits and return frozen provenance."""
    cases = load_case_definitions()
    corpus_audit = audit_corpus(cases)
    _self_test_decisions(cases)
    metadata_registry = create_builtin_registry()
    raster_spec = metadata_registry.get("binding.raster")
    if raster_spec.semantic_metadata is None:
        raise ValueError("binding.raster semantic metadata is missing.")
    metadata_projection = canonical_json(
        {
            "capability_id": raster_spec.capability_id,
            "purpose": raster_spec.semantic_metadata.purpose,
            "mappings": [
                {
                    "concept": mapping.concept,
                    "language_patterns": list(mapping.language_patterns),
                    "targets": [{"path": path, "value_cue": cue} for path, cue in mapping.targets],
                }
                for mapping in raster_spec.semantic_metadata.mappings
            ],
            "distinctions": list(raster_spec.semantic_metadata.distinctions),
        }
    )
    if sha256_text(f"[{metadata_projection}]") != EXPECTED_METADATA_SHA256:
        raise ValueError("CM-57A raster metadata projection drifted.")
    if response_schema_sha256() != RESPONSE_SCHEMA_SHA256:
        raise ValueError("Typed response schema drifted before CM-57C live authorization.")
    prompt_hashes = {
        "base": sha256_text(TYPED_SECTION_SYSTEM_PROMPT),
        "request_only": sha256_text(
            build_typed_section_system_prompt(has_semantic_contracts=False)
        ),
        "request_plus_metadata": sha256_text(
            build_typed_section_system_prompt(has_semantic_contracts=True)
        ),
    }
    if prompt_hashes != {
        "base": EXPECTED_BASE_PROMPT_SHA256,
        "request_only": EXPECTED_PROMPT_SHA256[False],
        "request_plus_metadata": EXPECTED_PROMPT_SHA256[True],
    }:
        raise ValueError("CM-57B production prompt hashes drifted.")
    evaluator_sha = evaluator_source_sha256()
    if evaluator_sha != EXPECTED_EVALUATOR_SHA256:
        raise ValueError("Corrected evaluator source drifted before CM-57C live authorization.")
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": DESIGN_BASELINE_SHA,
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "harness_source_sha256": artifact_sha256(Path(__file__).resolve()),
        "typed_worker_source_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/typed_section_worker.py"
        ),
        "planner_source_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/planner.py"
        ),
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_source_sha256": evaluator_sha,
        "provider_calls": 0,
        "corpus_audit": corpus_audit,
        "response_schema_sha256": response_schema_sha256(),
        "prompt_hashes": prompt_hashes,
        "metadata_projection_sha256": EXPECTED_METADATA_SHA256,
        "future_controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "worker_temperature": WORKER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
            "attempts": ATTEMPTS,
        },
        "decision_self_tests": "PASS",
        "live_inference": "NOT_STARTED",
        "live_authorization": "REQUIRES_EXPLICIT_CHECKOUT_SHA",
    }


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the frozen local OpenAI-compatible provider only in live mode."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    api_key = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        key_path = Path(args.api_key_file)
        if not key_path.is_absolute():
            key_path = REPO_ROOT / key_path
        api_key = api_key or key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No CM-57C API key configured.")
    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def _run_live(args: argparse.Namespace, *, authorized_checkpoint: str) -> None:
    """Run the frozen 32-row live population and flush rows incrementally."""
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    authorized_checkpoint = validate_authorized_checkpoint(authorized_checkpoint)
    verify_reviewed_checkout(authorized_checkpoint)
    cases = load_case_definitions()
    registry = create_builtin_registry()
    backend = CountingBackend(_provider_configuration(args))
    planner = SemanticPlanner(backend=backend, registry=registry)
    typed = TypedSectionCompiler(backend=backend, registry=registry)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        for case in cases:
            for attempt_index in range(ATTEMPTS):
                row = await run_case_attempt(
                    case,
                    planner=planner,
                    typed=typed,
                    registry=registry,
                    attempt_index=attempt_index,
                    authorized_checkpoint=authorized_checkpoint,
                )
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
    print(
        json.dumps(
            summarize_population(
                rows,
                cases,
                authorized_checkpoint=authorized_checkpoint,
            ),
            indent=2,
            sort_keys=True,
        )
    )


def _parser() -> argparse.ArgumentParser:
    """Build a CLI with frozen live controls and a provider-free default."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    return parser


def main() -> None:
    """Run the pre-live audit, or the explicitly authorized future live matrix."""
    args = _parser().parse_args()
    report = prelive_report()
    if not args.live_authorized:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    try:
        authorized_checkpoint = validate_authorized_checkpoint(args.authorized_checkpoint)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if not args.base_url:
        raise SystemExit("CM-57C live mode requires an explicitly configured base URL.")
    asyncio.run(_run_live(args, authorized_checkpoint=authorized_checkpoint))


if __name__ == "__main__":  # pragma: no cover
    main()

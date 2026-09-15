"""Fair section-level A/B evidence for the frozen CBL experiment."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    EnrichedSemanticContext,
    ReportContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.program_worker import ProgramSectionCompiler
from wellplot.agent.graph.executor import execute_document_intent
from wellplot.agent.graph.merge import merge_compiled_artifacts
from wellplot.agent.graph.models import SectionPlan
from wellplot.agent.graph.provider_adapter import StructuredModelProtocol
from wellplot.agent.graph.section_worker import SectionCompiler
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderRequestError,
)
from wellplot.authoring import load_authoring_document
from wellplot.authoring_context import AuthoringChannelCandidate
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent

try:
    from scripts.agent_eval_support import NOT_AVAILABLE, redact
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from agent_eval_support import NOT_AVAILABLE, redact  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
CBL_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "agentic_cbl"
FROZEN_PROMPT_SHA256 = "e2092b2f6c2404c13c542731304e10377404ca967b4082eb75d9bad78b76f9fc"
FROZEN_STARTER_SHA256 = "5dbbdb82dc5cc2616797dddaea8625def73db94a5798e0bf479ee487a817f057"
FROZEN_CONTRACT_SHA256 = "e9ca3c12d38c04ccae84d912523ab63491653b85c225501e780ad54844b4150b"

ExperimentDecision = Literal["PROCEED", "STOP_SDK_CONTEXT_GAP", "STOP_V2_REGRESSION"]


class SectionModelFactory(Protocol):
    """Create one fresh legacy structured model for an isolated run."""

    def __call__(self) -> StructuredModelProtocol:
        """Return a provider-backed structured model."""


class BackendFactory(Protocol):
    """Create one fresh v2 backend for an isolated run."""

    def __call__(self) -> ModelBackendProtocol:
        """Return a provider-backed v2 backend."""


@dataclass(frozen=True, slots=True)
class CBLExperimentCase:
    """One immutable semantic section case shared by both engines."""

    frozen_prompt: str
    starter_document: AuthoringDocumentSpec
    source_manifest: dict[str, object]
    section_plan: SectionPlan
    section_task: SectionTask
    section_context: EnrichedSemanticContext
    source_path: str
    source_format: str
    provider: str
    model: str
    temperature: float | None
    max_output_tokens: int | None
    timeout_seconds: float
    run_count: int

    @classmethod
    def load(
        cls,
        *,
        fixture_root: Path = CBL_FIXTURE_ROOT,
        section_id: str = "main_pass",
        provider: str = "unspecified",
        model: str = "unspecified",
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: float = 1800.0,
        run_count: int = 3,
    ) -> CBLExperimentCase:
        """Load the frozen CBL corpus and derive both worker contracts."""
        prompt_path = fixture_root / "frozen_prompt.txt"
        starter_path = fixture_root / "cased_hole_starter.log.yaml"
        contract_path = fixture_root / "compile_contract.json"
        prompt = prompt_path.read_text(encoding="utf-8")
        contract_text = contract_path.read_text(encoding="utf-8")
        if _sha256(prompt.encode("utf-8")) != FROZEN_PROMPT_SHA256:
            raise ValueError("Frozen CBL prompt hash changed; do not run CM-43.")
        if _sha256(starter_path.read_bytes()) != FROZEN_STARTER_SHA256:
            raise ValueError("Frozen CBL starter hash changed; do not run CM-43.")
        if _sha256(contract_text.encode("utf-8")) != FROZEN_CONTRACT_SHA256:
            raise ValueError("Frozen CBL contract hash changed; do not run CM-43.")

        contract = json.loads(contract_text)
        raw_sections = contract["reconstruction_plan"]["sections"]
        raw_plan = next(item for item in raw_sections if item["section_id"] == section_id)
        section_plan = SectionPlan.model_validate(raw_plan)
        source = section_plan.data_source
        if source is None:
            raise ValueError(f"Frozen section {section_id!r} has no data source.")
        source_manifest = dict(contract["source_manifest"])
        section_task = _section_task(section_plan)
        section_context = _section_context(
            section_task,
            section_id=section_id,
            source_path=source.source_path,
            source_format=source.source_format,
            source_manifest=source_manifest,
        )
        return cls(
            frozen_prompt=prompt,
            starter_document=load_authoring_document(starter_path),
            source_manifest=source_manifest,
            section_plan=section_plan,
            section_task=section_task,
            section_context=section_context,
            source_path=source.source_path,
            source_format=source.source_format,
            provider=provider,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            run_count=run_count,
        )


@dataclass(frozen=True, slots=True)
class CBLAcceptance:
    """Common host-side acceptance result for either engine's section intent."""

    success: bool
    semantic_omissions: tuple[str, ...] = ()
    unrequested_mutations: tuple[str, ...] = ()
    canonical_intent_valid: bool = False
    private_application_valid: bool = False
    legacy_target_id_match: bool = False

    @property
    def errors(self) -> tuple[str, ...]:
        """Return all common-contract failures in stable order."""
        return self.semantic_omissions + self.unrequested_mutations


@dataclass(frozen=True, slots=True)
class _RunMeasurements:
    """Metrics collected at one engine adapter boundary."""

    worker_invocations: int = 1
    provider_generation_calls: int | str = NOT_AVAILABLE
    repair_count: int | str = NOT_AVAILABLE
    input_tokens: int | str = NOT_AVAILABLE
    output_tokens: int | str = NOT_AVAILABLE
    total_tokens: int | str = NOT_AVAILABLE
    prompt_chars: int | str = NOT_AVAILABLE
    schema_chars: int | str = NOT_AVAILABLE
    dynamic_schema_chars: int | str = NOT_AVAILABLE
    program_chars: int | str = NOT_AVAILABLE
    program_ast_nodes: int | str = NOT_AVAILABLE
    program_calls: int | str = NOT_AVAILABLE
    program_hash: str | None = None
    provider_latency_ms: float | str = NOT_AVAILABLE


@dataclass(frozen=True, slots=True)
class CBLRunEvidence:
    """One redaction-safe, JSONL-ready result row."""

    experiment_version: str
    engine: Literal["v1", "v2"]
    run_index: int
    live: bool
    provider: str
    model: str
    engine_success: bool
    acceptance_success: bool
    semantic_omissions: tuple[str, ...]
    unrequested_mutations: tuple[str, ...]
    representability_status: str
    worker_invocations: int
    provider_generation_calls: int | str
    repair_count: int | str
    input_tokens: int | str
    output_tokens: int | str
    total_tokens: int | str
    worker_latency_ms: float | str
    provider_latency_ms: float | str
    prompt_chars: int | str
    schema_chars: int | str
    dynamic_schema_chars: int | str
    program_chars: int | str
    program_ast_nodes: int | str
    program_calls: int | str
    program_hash: str | None
    legacy_core_reached: bool
    canonical_intent_valid: bool
    private_application_valid: bool
    legacy_target_id_match: bool
    failure_stage: str | None = None
    failure_code: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a redaction-safe JSON-compatible row."""
        return redact({key: value for key, value in asdict(self).items() if value is not None})


@dataclass
class _StructuredRecorder:
    """Measure the actual legacy section request without changing it."""

    delegate: StructuredModelProtocol
    invocations: int = 0
    provider_generation_calls: int | str = NOT_AVAILABLE
    prompt_chars: int = 0
    schema_chars: int = 0

    async def generate(self, **kwargs: object) -> BaseModel:
        """Record request/schema sizes and delegate unchanged generation."""
        self.invocations += 1
        self.prompt_chars += len(str(kwargs["instructions"])) + len(str(kwargs["user_message"]))
        response_model = kwargs["response_model"]
        schema = response_model.model_json_schema()
        self.schema_chars += len(json.dumps(schema, separators=(",", ":"), default=str))
        result = await self.delegate.generate(**kwargs)  # type: ignore[arg-type]
        reported = getattr(self.delegate, "provider_generation_calls", NOT_AVAILABLE)
        if reported is NOT_AVAILABLE:
            backend = getattr(self.delegate, "backend", None)
            reported = getattr(backend, "provider_generation_calls", NOT_AVAILABLE)
        if isinstance(reported, int) and reported >= 0:
            self.provider_generation_calls = reported
        return result


@dataclass
class _ProgramRecorder:
    """Measure every v2 program generation and sum provider-reported metrics."""

    delegate: ModelBackendProtocol
    calls: int = 0
    prompt_chars: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    provider_latency_ms: float = 0.0
    have_token_metrics: bool = False
    have_latency_metrics: bool = False

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        """Record one request and delegate it without modification."""
        self.calls += 1
        self.prompt_chars += len(request.system_prompt) + len(request.user_prompt)
        result = await self.delegate.generate_program(request)
        metrics = result.metrics
        if metrics.input_tokens is not None:
            self.input_tokens += metrics.input_tokens
            self.have_token_metrics = True
        if metrics.output_tokens is not None:
            self.output_tokens += metrics.output_tokens
            self.have_token_metrics = True
        if metrics.total_tokens is not None:
            self.total_tokens += metrics.total_tokens
            self.have_token_metrics = True
        if metrics.latency_ms is not None:
            self.provider_latency_ms += metrics.latency_ms
            self.have_latency_metrics = True
        return result

    async def generate_structured(self, *args: object, **kwargs: object) -> object:
        """Delegate the unused protocol operation for protocol completeness."""
        return await self.delegate.generate_structured(*args, **kwargs)  # type: ignore[arg-type]


async def run_v1_once(
    case: CBLExperimentCase,
    *,
    model_factory: SectionModelFactory,
    registry: CapabilityRegistry | None = None,
    run_index: int = 1,
    live: bool = True,
) -> CBLRunEvidence:
    """Run the unchanged v1 section worker against the frozen main-pass case."""
    registry = registry or create_builtin_registry()
    before_modules = set(sys.modules)
    recorder = _StructuredRecorder(model_factory())
    compiler = SectionCompiler(model=recorder, registry=registry)
    started = time.perf_counter()
    try:
        artifact = await compiler.compile(
            request=case.frozen_prompt,
            plan=case.section_plan,
            current_document=case.starter_document.model_dump(mode="json"),
            source_manifest=case.source_manifest,
            mode="reconstruct",
        )
        intent = merge_compiled_artifacts([artifact], registry=registry)
        acceptance = _evaluate_intent(intent, case)
        measurements = _v1_measurements(recorder)
        failure_stage = None
        failure_code = None
        engine_success = True
    except ProviderRequestError as error:
        acceptance = CBLAcceptance(False, semantic_omissions=("provider failure",))
        measurements = _v1_measurements(recorder)
        failure_stage = "provider"
        failure_code = error.category.value
        engine_success = False
    except Exception:
        acceptance = CBLAcceptance(False, semantic_omissions=("engine failure",))
        measurements = _v1_measurements(recorder)
        failure_stage = "worker"
        failure_code = "worker_failure"
        engine_success = False
    return _evidence(
        case,
        engine="v1",
        run_index=run_index,
        live=live,
        engine_success=engine_success,
        acceptance=acceptance,
        measurements=measurements,
        worker_latency_ms=(time.perf_counter() - started) * 1000,
        legacy_core_reached=_new_legacy_core_import(before_modules),
        failure_stage=failure_stage,
        failure_code=failure_code,
    )


async def run_v2_once(
    case: CBLExperimentCase,
    *,
    backend_factory: BackendFactory,
    registry: CapabilityRegistry | None = None,
    run_index: int = 1,
    live: bool = True,
) -> CBLRunEvidence:
    """Run the unchanged v2 section worker against the same semantic case."""
    registry = registry or create_builtin_registry()
    before_modules = set(sys.modules)
    recorder = _ProgramRecorder(backend_factory())
    compiler = ProgramSectionCompiler(backend=recorder, registry=registry)
    started = time.perf_counter()
    source_text: str | None = None
    try:
        result = await compiler.compile(
            task_index=0,
            context=case.section_context,
            document=case.starter_document,
            timeout_seconds=case.timeout_seconds,
            temperature=case.temperature,
            max_output_tokens=case.max_output_tokens,
        )
        engine_success = result.success
        intent = result.artifact.intent_fragment if result.artifact is not None else None
        acceptance = (
            _evaluate_intent(intent, case)
            if intent is not None
            else CBLAcceptance(
                False,
                semantic_omissions=_diagnostics(result),
            )
        )
        source_text = result.program.source.text
        measurements = _v2_measurements(recorder, result.metrics.model_dump(mode="json"))
        failure_stage = None if result.success else "worker"
        failure_code = None if result.success else "program_execution_failed"
    except ProviderRequestError as error:
        acceptance = CBLAcceptance(False, semantic_omissions=("provider failure",))
        measurements = _v2_measurements(recorder, {})
        failure_stage = "provider"
        failure_code = error.category.value
        engine_success = False
    except Exception:
        acceptance = CBLAcceptance(False, semantic_omissions=("engine failure",))
        measurements = _v2_measurements(recorder, {})
        failure_stage = "worker"
        failure_code = "worker_failure"
        engine_success = False
    return _evidence(
        case,
        engine="v2",
        run_index=run_index,
        live=live,
        engine_success=engine_success,
        acceptance=acceptance,
        measurements=_with_program_hash(measurements, source_text),
        worker_latency_ms=(time.perf_counter() - started) * 1000,
        legacy_core_reached=_new_legacy_core_import(before_modules),
        failure_stage=failure_stage,
        failure_code=failure_code,
    )


async def run_ab(
    case: CBLExperimentCase,
    *,
    v1_model_factory: SectionModelFactory,
    v2_backend_factory: BackendFactory,
    live: bool = True,
) -> list[dict[str, object]]:
    """Run the requested number of isolated A/B pairs and return JSON rows."""
    rows: list[dict[str, object]] = []
    for run_index in range(1, case.run_count + 1):
        v1 = await run_v1_once(
            case,
            model_factory=v1_model_factory,
            run_index=run_index,
            live=live,
        )
        v2 = await run_v2_once(
            case,
            backend_factory=v2_backend_factory,
            run_index=run_index,
            live=live,
        )
        rows.extend((v1.as_dict(), v2.as_dict()))
    return rows


def evaluate_gate(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Evaluate the CM-43 gate without treating incomplete evidence as success."""
    grouped = {
        engine: [row for row in rows if row.get("engine") == engine] for engine in ("v1", "v2")
    }
    live_gate = all(
        len(grouped[engine]) >= 3 and all(row.get("live") is True for row in grouped[engine])
        for engine in ("v1", "v2")
    )
    if not live_gate:
        return {
            "ready": False,
            "decision": None,
            "reason": "CM-43 requires at least three live runs for each engine.",
        }
    v2_gap = any(
        row.get("representability_status") == "sdk_prompt_contract_insufficient"
        for row in grouped["v2"]
    )
    if v2_gap:
        decision: ExperimentDecision = "STOP_SDK_CONTEXT_GAP"
        reason = "The v2 SDK/context contract cannot represent the frozen CBL section."
    else:
        v1_acceptance = sum(row.get("acceptance_success") is True for row in grouped["v1"])
        v2_acceptance = sum(row.get("acceptance_success") is True for row in grouped["v2"])
        v2_simpler = _v2_complexity_advantage(grouped["v1"], grouped["v2"])
        if v2_acceptance < v1_acceptance and not v2_simpler:
            decision = "STOP_V2_REGRESSION"
            reason = "v2 is less reliable without a measured complexity advantage."
        else:
            decision = "PROCEED"
            reason = "v2 is competitive on acceptance and materially simpler."
    return {"ready": True, "decision": decision, "reason": reason}


def write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write independently parseable redacted A/B evidence rows."""
    path.write_text(
        "".join(json.dumps(redact(dict(row)), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def evaluate_section_intent(
    intent: AuthoringDocumentIntent,
    case: CBLExperimentCase,
) -> CBLAcceptance:
    """Expose the common evaluator for deterministic tests and review tools."""
    return _evaluate_intent(intent, case)


def _evaluate_intent(
    intent: AuthoringDocumentIntent | None,
    case: CBLExperimentCase,
) -> CBLAcceptance:
    if intent is None:
        return CBLAcceptance(False, semantic_omissions=("no canonical section intent",))

    semantic: list[str] = []
    mutations: list[str] = []
    payload = intent.model_dump(mode="json", exclude_unset=True)
    unexpected_root = sorted(set(payload) - {"sections", "removals"})
    mutations.extend(f"report-wide field: {field}" for field in unexpected_root)
    sections = intent.sections if isinstance(intent.sections, list) else []
    if len(sections) != 1:
        semantic.append("expected one section fragment")
        return CBLAcceptance(False, tuple(semantic), tuple(mutations), True, False, False)
    section = sections[0]
    if section.data_source is None:
        semantic.append("missing expected source association")
    elif (
        section.data_source.source_format != case.source_format
        or Path(section.data_source.source_path).name != Path(case.source_path).name
    ):
        semantic.append("unexpected source association")

    tracks = section.tracks if isinstance(section.tracks, list) else []
    role_tracks: dict[str, object] = {}
    for track in tracks:
        curve_channels = {
            binding.channel
            for binding in track.bindings or []
            if getattr(binding, "kind", None) == "curve" and binding.channel
        }
        raster_channels = {
            binding.channel
            for binding in track.bindings or []
            if getattr(binding, "kind", None) == "raster" and binding.channel
        }
        if track.kind == "normal" and {"ECGR_STGC", "TT", "TENS", "MTEM"} <= curve_channels:
            role_tracks.setdefault("combo", track)
        if track.kind == "reference" and {"STIT", "TDSP", "VSEC"} <= curve_channels:
            role_tracks.setdefault("depth", track)
        if track.kind == "normal" and "CBL" in curve_channels:
            role_tracks.setdefault("cbl", track)
        if track.kind == "array" and "VDL" in raster_channels:
            role_tracks.setdefault("vdl", track)

    for role, kind in (
        ("combo", "normal combo track"),
        ("depth", "reference/depth track"),
        ("cbl", "normal CBL track"),
        ("vdl", "array VDL track"),
    ):
        if role not in role_tracks:
            semantic.append(f"missing {kind}")

    if len(tracks) > 4:
        mutations.append("unrequested track")
    canonical = True
    private = _private_application(case, intent)
    legacy_ids = _legacy_target_ids(case)
    actual_ids = {
        binding.binding_id
        for track in tracks
        for binding in track.bindings or []
        if binding.binding_id
    }
    return CBLAcceptance(
        success=not semantic and not mutations and private,
        semantic_omissions=tuple(semantic),
        unrequested_mutations=tuple(mutations),
        canonical_intent_valid=canonical,
        private_application_valid=private,
        legacy_target_id_match=actual_ids == legacy_ids,
    )


def _private_application(case: CBLExperimentCase, intent: AuthoringDocumentIntent) -> bool:
    """Apply the fragment to a private document through the canonical executor."""
    sections = intent.sections or []
    if len(sections) != 1:
        return False
    section_id = sections[0].section_id
    available = {
        section_id: _available_channels(case),
        case.section_plan.section_id: _available_channels(case),
    }
    service = AuthoringService(case.starter_document.model_copy(deep=True))
    result = execute_document_intent(service, intent, available_channels=available)
    return result.success


def _available_channels(case: CBLExperimentCase) -> list[AuthoringChannelCandidate]:
    raw = case.source_manifest.get(case.section_plan.section_id, {})
    channels = raw.get("channels", []) if isinstance(raw, Mapping) else []
    return [
        AuthoringChannelCandidate(
            mnemonic=str(channel["mnemonic"]),
            kind=str(channel.get("kind", "scalar")),
            source_path=case.source_path,
        )
        for channel in channels
        if isinstance(channel, Mapping) and channel.get("mnemonic")
    ]


def _section_task(plan: SectionPlan) -> SectionTask:
    """Derive a static v2 task from the frozen v1 section plan."""
    capability_ids = {plan.capability_id, *(item.capability_id for item in plan.components)}
    requirements = tuple(item.goal for item in plan.components)
    source_hints = (plan.data_source.source_path,) if plan.data_source is not None else ()
    return SectionTask(
        goal=plan.goal,
        capability_ids=tuple(sorted(capability_ids)),
        source_hints=source_hints,
        requirements=requirements,
        constraints=tuple(plan.constraints),
    )


def _section_context(
    task: SectionTask,
    *,
    section_id: str,
    source_path: str,
    source_format: str,
    source_manifest: Mapping[str, object],
) -> EnrichedSemanticContext:
    """Build bounded v2 enrichment without invoking the semantic planner."""
    raw = source_manifest.get(section_id, {})
    raw_channels = raw.get("channels", []) if isinstance(raw, Mapping) else []
    channels = tuple(
        ChannelContext(
            mnemonic=str(channel["mnemonic"]),
            kind=str(channel.get("kind", "scalar")),
        )
        for channel in raw_channels
        if isinstance(channel, Mapping) and channel.get("mnemonic")
    )
    source = SourceContext(
        candidate_id="frozen-main-pass",
        canonical_path=source_path,
        source_format=source_format,  # type: ignore[arg-type]
        dataset_name="frozen-cbl-main-pass",
        channels=channels,
    )
    resolved = ResolvedSectionContext(
        task_index=0,
        section_id=None,
        sources=(source,),
        channels=(),
    )
    return EnrichedSemanticContext(
        plan=SemanticPlan(
            summary="Frozen CM-43 CBL section case",
            section_tasks=(task,),
        ),
        sections=(resolved,),
        report=ReportContext(),
    )


def _v1_measurements(recorder: _StructuredRecorder) -> _RunMeasurements:
    """Map measured legacy request/schema sizes into common evidence fields."""
    return _RunMeasurements(
        worker_invocations=recorder.invocations,
        provider_generation_calls=recorder.provider_generation_calls,
        prompt_chars=recorder.prompt_chars,
        schema_chars=recorder.schema_chars,
        dynamic_schema_chars=recorder.schema_chars,
    )


def _v2_measurements(recorder: _ProgramRecorder, metrics: Mapping[str, object]) -> _RunMeasurements:
    """Map v2 program and provider measurements without inventing zeros."""
    tokens = (
        recorder.input_tokens if recorder.have_token_metrics else NOT_AVAILABLE,
        recorder.output_tokens if recorder.have_token_metrics else NOT_AVAILABLE,
        recorder.total_tokens if recorder.have_token_metrics else NOT_AVAILABLE,
    )
    return _RunMeasurements(
        provider_generation_calls=recorder.calls,
        repair_count=metrics.get("program_repairs", NOT_AVAILABLE),
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        total_tokens=tokens[2],
        prompt_chars=recorder.prompt_chars,
        schema_chars=0,
        dynamic_schema_chars=0,
        program_chars=metrics.get("program_chars", NOT_AVAILABLE),
        program_ast_nodes=metrics.get("program_ast_nodes", NOT_AVAILABLE),
        program_calls=metrics.get("program_calls", NOT_AVAILABLE),
        provider_latency_ms=(
            recorder.provider_latency_ms if recorder.have_latency_metrics else NOT_AVAILABLE
        ),
    )


def _with_program_hash(measurements: _RunMeasurements, source: str | None) -> _RunMeasurements:
    """Retain only a hash and length for generated source evidence."""
    if source is None:
        return measurements
    return measurements.__class__(
        **{
            **asdict(measurements),
            "program_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "program_chars": len(source),
        }
    )


def _evidence(
    case: CBLExperimentCase,
    *,
    engine: Literal["v1", "v2"],
    run_index: int,
    live: bool,
    engine_success: bool,
    acceptance: CBLAcceptance,
    measurements: _RunMeasurements,
    worker_latency_ms: float,
    legacy_core_reached: bool,
    failure_stage: str | None,
    failure_code: str | None,
) -> CBLRunEvidence:
    """Build the stable evidence row shared by both engine adapters."""
    representability = "complete"
    if engine == "v2" and any(
        item in {"missing array VDL track", "missing normal CBL track"}
        for item in acceptance.semantic_omissions
    ):
        representability = "sdk_prompt_contract_insufficient"
    elif not acceptance.success:
        representability = "incomplete"
    return CBLRunEvidence(
        experiment_version="cm43-v1",
        engine=engine,
        run_index=run_index,
        live=live,
        provider=case.provider,
        model=case.model,
        engine_success=engine_success,
        acceptance_success=acceptance.success,
        semantic_omissions=acceptance.semantic_omissions,
        unrequested_mutations=acceptance.unrequested_mutations,
        representability_status=representability,
        worker_invocations=measurements.worker_invocations,
        provider_generation_calls=measurements.provider_generation_calls,
        repair_count=measurements.repair_count,
        input_tokens=measurements.input_tokens,
        output_tokens=measurements.output_tokens,
        total_tokens=measurements.total_tokens,
        worker_latency_ms=round(worker_latency_ms, 2),
        provider_latency_ms=measurements.provider_latency_ms,
        prompt_chars=measurements.prompt_chars,
        schema_chars=measurements.schema_chars,
        dynamic_schema_chars=measurements.dynamic_schema_chars,
        program_chars=measurements.program_chars,
        program_ast_nodes=measurements.program_ast_nodes,
        program_calls=measurements.program_calls,
        program_hash=measurements.program_hash,
        legacy_core_reached=legacy_core_reached,
        canonical_intent_valid=acceptance.canonical_intent_valid,
        private_application_valid=acceptance.private_application_valid,
        legacy_target_id_match=acceptance.legacy_target_id_match,
        failure_stage=failure_stage,
        failure_code=failure_code,
    )


def _diagnostics(result: object) -> tuple[str, ...]:
    diagnostics = getattr(result, "diagnostics", ())
    messages = tuple(
        str(getattr(item, "message", "program execution failed")) for item in diagnostics
    )
    return messages or ("program execution failed",)


def _legacy_target_ids(case: CBLExperimentCase) -> set[str]:
    return {
        component.target_id
        for component in case.section_plan.components
        if "." in component.target_id
    }


def _new_legacy_core_import(before_modules: set[str]) -> bool:
    """Measure whether this adapter newly loaded the legacy core module."""
    return any(
        name == "wellplot.agent.core" or name.startswith("wellplot.agent.core.")
        for name in set(sys.modules) - before_modules
    )


def _v2_complexity_advantage(
    v1_rows: Sequence[Mapping[str, object]],
    v2_rows: Sequence[Mapping[str, object]],
) -> bool:
    v1_schema = _numeric_average(v1_rows, "dynamic_schema_chars")
    v2_schema = _numeric_average(v2_rows, "dynamic_schema_chars")
    v1_calls = _numeric_average(v1_rows, "provider_generation_calls")
    v2_calls = _numeric_average(v2_rows, "provider_generation_calls")
    return (v2_schema is not None and v1_schema is not None and v2_schema < v1_schema) or (
        v2_calls is not None and v1_calls is not None and v2_calls < v1_calls
    )


def _numeric_average(rows: Sequence[Mapping[str, object]], field: str) -> float | None:
    values = [row[field] for row in rows if isinstance(row.get(field), (int, float))]
    return sum(values) / len(values) if values else None


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "CBLAcceptance",
    "CBLExperimentCase",
    "CBLRunEvidence",
    "evaluate_gate",
    "evaluate_section_intent",
    "run_ab",
    "run_v1_once",
    "run_v2_once",
    "write_jsonl",
]

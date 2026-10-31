"""Canonical provider-facing section worker and deterministic lowering path."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from ...model.intent import AuthoringStyleIntent
from ..providers.base import (
    ModelBackendProtocol,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from ..semantic_runtime import SemanticDiagnostic, SemanticMetrics, SemanticStageEvidence
from .canonical_workers import SectionSemanticActionResponse
from .enrichment import ResolvedSectionContext
from .obligations import (
    ObligationKind,
    ObligationState,
    OwnerKind,
    RepairContract,
    RepairOperation,
    RequestObligation,
    SectionObjectBindings,
    ValidationIssue,
    ValidationIssueSet,
    validate_section_obligations,
    verify_lowered_existing_curve_obligations,
)
from .planner import SectionTask
from .section_semantics import (
    SemanticGrid,
    SemanticSampleAxis,
    SemanticScale,
    TrackSemanticDraft,
)
from .semantic_actions import (
    AddFillAction,
    AddTrackAction,
    ReconstructSectionAction,
    SectionSemanticAction,
    SemanticActionError,
    UpdateCurveScaleAction,
    lower_section_action,
)
from .worker_contracts import (
    CanonicalWorkerResult,
    SectionWorkContract,
    SectionWorkContractError,
    validate_section_action_contract,
)

_ACTION_RESPONSE_MODELS = {
    "reconstruct": ReconstructSectionAction,
    "add_track": AddTrackAction,
    "update_curve_scale": UpdateCurveScaleAction,
    "add_fill": AddFillAction,
}

_SECTION_ACTION_EXAMPLE_VERSION = "wellplot.section-action-examples.v1"
_SECTION_ACTION_EXAMPLES: dict[str, dict[str, object]] = {
    "reconstruct": {
        "action": "reconstruct",
        "section": {
            "title": "Example Section",
            "source_candidate": "source-1",
            "tracks": [
                {
                    "semantic_id": "example_track_a",
                    "kind": "normal",
                    "title": "Example Track A",
                    "bindings": [
                        {
                            "semantic_id": "example_track_a.binding.1",
                            "channel": "EXAMPLE_A",
                        }
                    ],
                },
                {
                    "semantic_id": "example_track_b",
                    "kind": "normal",
                    "title": "Example Track B",
                    "bindings": [
                        {
                            "semantic_id": "example_track_b.binding.1",
                            "channel": "EXAMPLE_B",
                        }
                    ],
                },
            ],
        },
    },
    "add_track": {
        "action": "add_track",
        "track": {
            "semantic_id": "example_track",
            "kind": "normal",
            "title": "Example Track",
            "bindings": [{"semantic_id": "example_track.binding.1", "channel": "EXAMPLE_A"}],
        },
    },
    "update_curve_scale": {
        "action": "update_curve_scale",
        "target": {"handle": "curve-1"},
        "scale": {"kind": "linear", "minimum": 1, "maximum": 10},
    },
    "add_fill": {
        "action": "add_fill",
        "target": {"handle": "curve-1"},
        "fill": {
            "kind": "to_lower_limit",
            "semantic_id": "example_fill",
            "target_binding": "example_track.binding.1",
            "color": "#777777",
            "alpha": 0.25,
        },
    },
}


def _section_action_example(action: str) -> dict[str, object]:
    """Return one static versioned example and its stable content digest."""
    example = _SECTION_ACTION_EXAMPLES[action]
    serialized = json.dumps(example, sort_keys=True, separators=(",", ":"))
    return {
        "version": _SECTION_ACTION_EXAMPLE_VERSION,
        "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "payload": example,
    }


_TRACK_DIMENSION_RE = re.compile(
    r"^\s*Track\s+(?P<number>\d+)\s+\((?P<semantic_id>[^)]+)\):\s*"
    r"(?P<kind>normal|reference|array)(?:\s+track)?\s*,?\s*"
    r"(?:width\s*)?(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class _RequestTrackBlock:
    """One request-owned track presentation block used by canonical normalization."""

    track: str
    body: str


_NAMED_TRACK_DIMENSION_RE = re.compile(
    r"^\s*(?P<semantic_id>[A-Za-z][A-Za-z0-9 _-]*?)\s*(?:=|:)\s*"
    r"(?P<kind>normal|reference|array)(?:\s+track)?\s*,?\s*"
    r"(?:width\s*)?(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE | re.MULTILINE,
)
_INLINE_NAMED_TRACK_DIMENSION_RE = re.compile(
    r"(?:^|[;\n])\s*(?P<semantic_id>[A-Za-z][A-Za-z0-9 _-]*?)\s*(?:=|:)\s*"
    r"(?P<kind>normal|reference|array)(?:\s+track)?\s*,?\s*"
    r"(?:width\s*)?(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE | re.MULTILINE,
)
_PHRASED_TRACK_DIMENSION_RE = re.compile(
    r"^\s*(?P<semantic_id>[A-Za-z][A-Za-z0-9_-]*)\s+"
    r"(?P<kind>normal|reference|array)\s+track\s*,?\s*"
    r"(?:width\s*)?(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE | re.MULTILINE,
)
_ANONYMOUS_TRACK_DIMENSION_RE = re.compile(
    r"(?<![A-Za-z])(?P<kind>normal|reference|array)\s+track\s*,\s*"
    r"(?:width\s*)?(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\b",
    re.IGNORECASE,
)
_TRACK_CHANNEL_LINE_RE = re.compile(
    r"^\s*Track\s+(?P<number>\d+)(?:\s+\([^)]*\))?\s*:\s*(?P<body>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_TRACK_BLOCK_RE = re.compile(
    r"^\s*On\s+(?P<track>[^:,\n]+?)\s*(?P<delimiter>:|,)",
    re.IGNORECASE | re.MULTILINE,
)
_TASK_TRACK_BLOCK_RE = re.compile(
    r"^\s*(?P<track>[^:\n]+?)\s+bindings?:\s*(?P<body>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_CURVE_REQUIREMENT_RE = re.compile(
    r"(?P<channel>[A-Z][A-Z0-9_]*)\s*(?:→|->)\s*"
    r"(?:\"(?P<label_quoted>[^\"]+)\"|(?P<label_plain>.*?))\s*,\s*"
    r"(?P<kind>linear|log)\s+(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\.\."
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)(?P<reverse>\s+reversed)?\s*,\s*"
    r"(?P<color>#[0-9A-Fa-f]{6})(?:\s+(?P<line_style>dashed|dotted))?\s*,\s*"
    r"width\s+(?P<line_width>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_MULTI_BINDING_LABEL_RE = re.compile(
    r"\b(?:both|all)\s+labels?\s+are\s+"
    r"(?:\"(?P<label_quoted>[^\"]+)\"|'(?P<label_single>[^']+)'|(?P<label_plain>[^.,\n]+))",
    re.IGNORECASE,
)
_RASTER_LABEL_RE = re.compile(
    r"\braster\s+label(?:led|ed)\s+"
    r"(?:\"(?P<label_quoted>[^\"]+)\"|'(?P<label_single>[^']+)'|(?P<label_plain>[^.,\n]+))",
    re.IGNORECASE,
)
_ORDINAL_CURVE_REQUIREMENT_RE = re.compile(
    r"The\s+(?P<ordinal>first|second|third|fourth)\s+is\s+"
    r"(?P<kind>linear|log)\s+(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\.\."
    r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)(?P<reverse>\s+reversed)?\s*,\s*"
    r"(?P<color>#[0-9A-Fa-f]{6})(?:\s+(?P<line_style>dashed|dotted))?\s*,\s*"
    r"width\s+(?P<line_width>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)


class SectionActionEvidenceError(RuntimeError):
    """An explicitly requested diagnostic observation could not be retained."""

    def __init__(self, original: SectionWorkContractError | None = None) -> None:
        self.original = original
        super().__init__("Section action evidence could not be retained.")


@dataclass(frozen=True, slots=True)
class CanonicalSectionWorker:
    """Generate and lower the one canonical section action contract."""

    backend: ModelBackendProtocol
    action_observer: Callable[[Mapping[str, object]], None] | None = None
    action_capture_mode: Literal["off", "diagnostics", "validated_dto"] = "off"

    def _observe_action(
        self,
        action: SectionSemanticAction,
        attempt: int,
        *,
        common: Mapping[str, object] | None = None,
    ) -> None:
        """Expose an opt-in copy of a schema-validated proposal for diagnostics."""
        if self.action_observer is None:
            return
        if self.action_capture_mode == "off":
            self.action_observer(
                {
                    "event": "SECTION_ACTION_VALIDATED",
                    "attempt": attempt,
                    "action": action.model_dump(mode="json", exclude_unset=True),
                }
            )
        else:
            self.action_observer({**(common or {}), "event": "SECTION_ACTION_VALIDATED"})

    def _validate_observed_action(
        self,
        action: SectionSemanticAction,
        contract: SectionWorkContract,
        *,
        task_index: int,
        attempt: int,
        logical_call_index: int | None,
    ) -> SectionWorkContractError | None:
        """Observe schema-valid actions before applying the unchanged contract check."""
        enabled = self.action_capture_mode != "off"
        if self.action_capture_mode not in {"off", "diagnostics", "validated_dto"}:
            raise SectionActionEvidenceError()
        common: dict[str, object] = {}
        if enabled:
            if self.action_observer is None or logical_call_index is None:
                raise SectionActionEvidenceError()
            dto = action.model_dump(mode="json", exclude_unset=True)
            encoded = json.dumps(
                dto, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()
            common = {
                "event_version": "wellplot.section-action-observation.v1",
                "worker_role": "section_worker",
                "task_index": task_index,
                "attempt": attempt,
                "logical_call_index": logical_call_index,
                "response_schema": type(action).__name__,
                "dto_sha256": hashlib.sha256(encoded).hexdigest(),
                "dto_size_bytes": len(encoded),
            }
            event = {
                **common,
                "event": "SECTION_ACTION_SCHEMA_VALIDATED",
                "capture_state": "complete"
                if self.action_capture_mode == "validated_dto"
                else "metadata_only",
                "contract_outcome": "NOT_EVALUATED",
            }
            if self.action_capture_mode == "validated_dto":
                event["action"] = dto
            try:
                self.action_observer(event)
            except Exception:
                raise SectionActionEvidenceError() from None
        error: SectionWorkContractError | None = None
        try:
            validate_section_action_contract(action, contract)
        except SectionWorkContractError as caught:
            error = caught
        if enabled:
            assert self.action_observer is not None
            try:
                self.action_observer(
                    {
                        **common,
                        "event": "SECTION_ACTION_CONTRACT_RESULT",
                        "contract_outcome": "FAIL" if error is not None else "PASS",
                        "diagnostic_code": error.code if error is not None else None,
                        "mismatch": error.details if error is not None else None,
                    }
                )
            except Exception:
                raise SectionActionEvidenceError(error) from None
        if error is None:
            try:
                self._observe_action(action, attempt, common=common)
            except Exception:
                if enabled:
                    raise SectionActionEvidenceError() from None
                raise
        return error

    async def compile(
        self,
        *,
        task_index: int,
        context: object,
        document: object,
        authoritative_request: str,
        work_contract: SectionWorkContract,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> CanonicalWorkerResult:
        """Generate exactly one action and lower it without document mutation."""
        section_context = ResolvedSectionContext.model_validate(context.sections[task_index])
        task = SectionTask.model_validate(context.plan.section_tasks[task_index])
        payload = {
            "section_work_contract": work_contract.model_dump(mode="json"),
            "section_task": _provider_section_task(task),
            "section_context": _canonical_section_context(section_context, work_contract),
            "authoritative_request": authoritative_request,
            "authority_rules": {
                "section_work_contract": "authoritative task-local requirements and action",
                "section_context": "host-grounded source and existing-object facts",
                "authoritative_request": "supporting context only",
                "section_task": "supporting scoped decomposition only",
            },
            "action_example": _section_action_example(work_contract.required_action),
        }
        request = StructuredGenerationRequest(
            system_prompt=(
                "You are the WellPlot section semantic serialization worker. The host has "
                "already interpreted the request and resolved authoritative requirements. "
                "The supplied SectionWorkContract is authoritative. Construct exactly one "
                "JSON object satisfying the supplied action-specific response schema. "
                "Represent every required object exactly once and copy request-local handles "
                "exactly. Preserve required values and use only supplied source/channel facts. "
                "Do not omit or invent objects. The example demonstrates structure only; its "
                "values are not authoritative. Never emit canonical host IDs, filesystem paths, "
                "programs, SDK calls, renderer state, or unrelated document state."
            ),
            user_prompt=_json_payload(payload),
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            generated = await self.backend.generate_structured(
                request,
                response_model=_ACTION_RESPONSE_MODELS[work_contract.required_action],
            )
        except ProviderRequestError:
            raise
        except ValidationError:
            return _canonical_failure(
                "structured_schema_validation_failure",
                "Section output did not match the canonical semantic action schema.",
            )
        raw_action: SectionSemanticAction = TypeAdapter(SectionSemanticAction).validate_python(
            generated.value
        )
        try:
            error = self._validate_observed_action(
                raw_action,
                work_contract,
                task_index=task_index,
                attempt=1,
                logical_call_index=getattr(generated, "logical_call_index", None),
            )
        except SectionActionEvidenceError as evidence_error:
            return _action_evidence_failure(evidence_error)
        if error is not None:
            return _canonical_failure(
                error.code,
                "Section response did not satisfy the deterministic work contract.",
                normalization="PASS",
                worker_obligation="FAIL",
            )
        correction_contract: RepairContract | None = None
        correction_baseline: SectionSemanticAction | None = None
        object_bindings: SectionObjectBindings | None = None
        for attempt in range(2):
            try:
                if attempt:
                    if (
                        correction_baseline is None
                        or correction_contract is None
                        or object_bindings is None
                    ):
                        return _canonical_failure(
                            "worker_repair_contract_missing",
                            "Section correction lacks a frozen repair contract.",
                            correction="FAIL",
                        )
                    _verify_repair_candidate(
                        correction_baseline,
                        raw_action,
                        correction_contract,
                        object_bindings=object_bindings,
                    )
                action = _bind_compiled_source(
                    raw_action,
                    section_context,
                    work_contract=work_contract,
                )
                if not attempt:
                    object_bindings = resolve_section_object_bindings(action, task.obligations)
                assert object_bindings is not None
                action = apply_compiled_requirements(
                    action, task.obligations, object_bindings=object_bindings
                )
                issues = _collect_validation_issues(
                    action,
                    task.obligations,
                    section_context=section_context,
                    section_title=task.existing_section_hint,
                    object_bindings=object_bindings,
                )
                if issues.issues:
                    raise SemanticActionError(
                        "semantic_contract_incomplete",
                        "Compiled request requirements remain unsatisfied.",
                    )
                validate_section_obligations(
                    action,
                    task.obligations,
                    section_context=section_context,
                    section_title=task.existing_section_hint,
                    object_bindings=object_bindings,
                )
                try:
                    intent = lower_section_action(
                        action,
                        context=section_context,
                        document=document,
                    )
                except SemanticActionError as error:
                    return _canonical_failure(
                        error.code,
                        "Section semantics could not be lowered safely.",
                        normalization="PASS",
                        worker_obligation="PASS",
                        semantic_lowering="FAIL",
                    )
                verify_lowered_existing_curve_obligations(
                    action,
                    intent,
                    task.obligations,
                    section_context=section_context,
                )
                return CanonicalWorkerResult(
                    True,
                    intent,
                    (),
                    SemanticMetrics(),
                    SemanticStageEvidence(
                        provider_wire="PASS",
                        python_validation="PASS",
                        normalization="PASS",
                        worker_obligation="PASS",
                        semantic_lowering="PASS",
                        correction="PASS" if attempt else "NOT_REACHED",
                    ),
                )
            except ValidationError:
                return _canonical_failure(
                    "semantic_context_validation_failure",
                    "Section semantics failed canonical validation.",
                    normalization="FAIL",
                )
            except SemanticActionError as error:
                if error.code.startswith("worker_grounding_"):
                    return _canonical_failure(
                        error.code,
                        "Section proposal identity could not be grounded safely.",
                        normalization="FAIL",
                    )
                if error.code == "worker_correction_scope_violation":
                    return _canonical_failure(
                        error.code,
                        "Section correction changed fields outside its frozen repair contract.",
                        normalization="PASS",
                        worker_obligation="FAIL",
                        correction="FAIL",
                    )
                if attempt or error.code != "semantic_contract_incomplete":
                    return _canonical_failure(
                        error.code,
                        "Section semantics could not be validated safely.",
                        normalization="PASS",
                        worker_obligation="FAIL",
                        correction="FAIL" if attempt else "NOT_REACHED",
                    )
                issues = _collect_validation_issues(
                    action,
                    task.obligations,
                    section_context=section_context,
                    section_title=task.existing_section_hint,
                    object_bindings=object_bindings,
                )
                if not issues.issues:
                    return _canonical_failure(
                        error.code,
                        "Section completeness could not be grounded to a compiled requirement.",
                        normalization="PASS",
                        worker_obligation="FAIL",
                    )
                correction_baseline = action
                try:
                    correction_contract = _build_repair_contract(
                        correction_baseline, issues, object_bindings=object_bindings
                    )
                except SemanticActionError as repair_error:
                    if repair_error.code not in {
                        "worker_grounding_unresolved",
                        "worker_grounding_ambiguous",
                        "worker_repair_target_unresolved",
                        "worker_repair_target_ambiguous",
                    }:
                        raise
                    return _canonical_failure(
                        repair_error.code,
                        "A safe section repair target could not be grounded.",
                        normalization="PASS",
                        worker_obligation="FAIL",
                    )
                correction_payload = {
                    **payload,
                    "correction": {
                        "host_applied_candidate": correction_baseline.model_dump(
                            mode="json", exclude_unset=True
                        ),
                        "issues": issues.model_dump(mode="json"),
                        "repair_contract": correction_contract.model_dump(mode="json"),
                    },
                }
                try:
                    corrected = await self.backend.generate_structured(
                        StructuredGenerationRequest(
                            system_prompt=(
                                "Return the complete corrected semantic action. Preserve all "
                                "existing identity, order, and sibling values. Apply only the "
                                "listed repair operations."
                            ),
                            user_prompt=_json_payload(correction_payload),
                            timeout_seconds=timeout_seconds,
                            temperature=temperature,
                            max_output_tokens=max_output_tokens,
                        ),
                        response_model=_ACTION_RESPONSE_MODELS[work_contract.required_action],
                    )
                except ProviderRequestError:
                    raise
                except ValidationError:
                    return _canonical_failure(
                        "structured_schema_validation_failure",
                        "Section correction did not match the canonical semantic schema.",
                        correction="FAIL",
                    )
                raw_action = TypeAdapter(SectionSemanticAction).validate_python(corrected.value)
                try:
                    error = self._validate_observed_action(
                        raw_action,
                        work_contract,
                        task_index=task_index,
                        attempt=2,
                        logical_call_index=getattr(corrected, "logical_call_index", None),
                    )
                except SectionActionEvidenceError as evidence_error:
                    return _action_evidence_failure(evidence_error, correction="FAIL")
                if error is not None:
                    return _canonical_failure(
                        error.code,
                        "Corrected response did not satisfy the deterministic work contract.",
                        normalization="PASS",
                        worker_obligation="FAIL",
                        correction="FAIL",
                    )
                continue
            except ValueError:
                return _canonical_failure(
                    "worker_obligation_unsatisfied",
                    "Section semantics failed a compiled request requirement.",
                    normalization="PASS",
                    worker_obligation="FAIL",
                    correction="FAIL" if attempt else "NOT_REACHED",
                )
            except Exception:
                return _canonical_failure(
                    "semantic_lowering_failure",
                    "Section semantics could not be lowered safely.",
                    normalization="PASS",
                    worker_obligation="PASS",
                    semantic_lowering="FAIL",
                )
        return _canonical_failure(
            "semantic_context_validation_failure",
            "Section semantics could not be validated safely.",
        )


def _canonical_section_context(
    context: ResolvedSectionContext,
    work_contract: SectionWorkContract,
) -> dict[str, object]:
    """Expose safe source facts and opaque existing-object handles only."""
    return {
        "target": {"kind": "existing" if context.section_id else "new"},
        "sources": [source.model_dump(mode="json") for source in work_contract.source_facts],
        "existing_curves": [
            {
                "handle": f"curve-{index}",
                "track_title": curve.track_title,
                "track_kind": curve.track_kind,
                "channel": curve.channel,
                "label": curve.label,
                "scale_kind": curve.scale_kind,
                "scale_minimum": curve.scale_minimum,
                "scale_maximum": curve.scale_maximum,
                "reverse": curve.reverse,
            }
            for index, curve in enumerate(context.existing_curves, start=1)
        ],
    }


def _normalize_reconstruct_track_dimensions(
    action: SectionSemanticAction,
    task: SectionTask,
    *,
    authoritative_request: str = "",
) -> SectionSemanticAction:
    """Apply explicit track identity and width without relying on response order."""
    if action.action != "reconstruct":
        return action
    dimensions: list[tuple[str | None, str, float, int | None]] = []
    channel_signatures: dict[int, tuple[str, ...]] = {}

    def collect(text: str) -> list[tuple[str | None, str, float, int | None]]:
        collected: list[tuple[str | None, str, float, int | None]] = []
        for match in _TRACK_DIMENSION_RE.finditer(text):
            collected.append(
                (
                    match.group("semantic_id").strip(),
                    match.group("kind").casefold(),
                    float(match.group("width")),
                    int(match.group("number")),
                )
            )
        for match in _INLINE_NAMED_TRACK_DIMENSION_RE.finditer(text):
            collected.append(
                (
                    match.group("semantic_id").strip(),
                    match.group("kind").casefold(),
                    float(match.group("width")),
                    None,
                )
            )
        for match in _NAMED_TRACK_DIMENSION_RE.finditer(text):
            collected.append(
                (
                    match.group("semantic_id").strip(),
                    match.group("kind").casefold(),
                    float(match.group("width")),
                    None,
                )
            )
        for match in _PHRASED_TRACK_DIMENSION_RE.finditer(text):
            collected.append(
                (
                    match.group("semantic_id").strip(),
                    match.group("kind").casefold(),
                    float(match.group("width")),
                    None,
                )
            )
        for match in _ANONYMOUS_TRACK_DIMENSION_RE.finditer(text):
            collected.append(
                (
                    None,
                    match.group("kind").casefold(),
                    float(match.group("width")),
                    None,
                )
            )
        return collected

    authoritative_dimensions = collect(authoritative_request)
    dimensions.extend(authoritative_dimensions)
    for requirement in task.requirements:
        dimensions.extend(collect(requirement))
        for channel_match in _TRACK_CHANNEL_LINE_RE.finditer(requirement):
            signature = _channel_signature(channel_match.group("body"))
            if signature:
                channel_signatures[int(channel_match.group("number"))] = signature
    if not dimensions:
        return action
    tracks = list(action.section.tracks)
    used_indices: set[int] = set()
    seen_dimensions: set[str] = set()
    authoritative_by_shape: dict[tuple[str, float], set[str]] = {}
    for semantic_id, kind, width_mm, _ in authoritative_dimensions:
        if semantic_id is not None:
            authoritative_by_shape.setdefault((kind, width_mm), set()).add(semantic_id)
    for semantic_id, kind, width_mm, track_number in dimensions:
        if semantic_id is None:
            candidates = authoritative_by_shape.get((kind, width_mm), set()) - seen_dimensions
            if len(candidates) != 1:
                continue
            semantic_id = next(iter(candidates))
        dimension_key = _normalize_track_identifier(semantic_id)
        if dimension_key in seen_dimensions:
            continue
        seen_dimensions.add(dimension_key)
        signature = channel_signatures.get(track_number, ()) if track_number else ()
        index = _find_track_index(
            tracks,
            identifiers=(semantic_id,),
            channel_signature=signature,
            used_indices=used_indices,
        )
        track = tracks[index]
        actual_kind = str(getattr(track, "kind", "")).casefold()
        if actual_kind != kind:
            raise SemanticActionError(
                "semantic_contract_incomplete",
                f"Track '{semantic_id}' requested kind '{kind}', received '{actual_kind}'.",
            )
        tracks[index] = track.model_copy(update={"semantic_id": semantic_id, "width_mm": width_mm})
        used_indices.add(index)
    return action.model_copy(
        update={"section": action.section.model_copy(update={"tracks": tuple(tracks)})}
    )


def _normalize_reconstruct_request_semantics(
    action: SectionSemanticAction,
    *,
    task: SectionTask,
    authoritative_request: str,
) -> SectionSemanticAction:
    """Apply explicit track and binding presentation clauses from the request."""
    if action.action != "reconstruct":
        return action
    requirement_text = "\n".join(task.requirements)
    request_blocks = _extract_request_track_blocks(authoritative_request)
    task_blocks = tuple(
        _RequestTrackBlock(
            track=block.group("track").strip(),
            body=block.group("body").strip(),
        )
        for block in _TASK_TRACK_BLOCK_RE.finditer(requirement_text)
    )
    seen_block_names = {block.track.casefold() for block in request_blocks}
    blocks = request_blocks + tuple(
        block for block in task_blocks if block.track.strip().casefold() not in seen_block_names
    )
    section = action.section
    if task.existing_section_hint:
        section = section.model_copy(update={"title": task.existing_section_hint})
    if not blocks:
        return action.model_copy(update={"section": section})
    tracks = list(action.section.tracks)
    matched_blocks: set[int] = set()
    for index, track in enumerate(tracks):
        block = _matching_track_block(track, blocks)
        if block is None:
            continue
        matched_blocks.add(id(block))
        tracks[index] = _normalize_track_request_semantics(track, block.body)
    if len(matched_blocks) != len(blocks):
        unmatched = tuple(
            block.track.strip() for block in blocks if id(block) not in matched_blocks
        )
        raise SemanticActionError(
            "semantic_contract_incomplete",
            "Explicit track semantics could not be matched by identity: " + ", ".join(unmatched),
        )
    return action.model_copy(
        update={"section": section.model_copy(update={"tracks": tuple(tracks)})}
    )


def _extract_request_track_blocks(request: str) -> tuple[_RequestTrackBlock, ...]:
    """Extract colon and inline-comma track clauses from an authoritative request."""
    headers = tuple(_TRACK_BLOCK_RE.finditer(request))
    blocks: list[_RequestTrackBlock] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(request)
        body = request[header.end() : end]
        body = re.split(r"^\s*Use only channels\b", body, maxsplit=1, flags=re.I | re.M)[0]
        blocks.append(
            _RequestTrackBlock(
                track=header.group("track").strip(),
                body=body.strip(),
            )
        )
    return tuple(blocks)


def _matching_track_block(
    track: object,
    blocks: tuple[_RequestTrackBlock, ...],
) -> _RequestTrackBlock | None:
    """Match a request block by semantic identity or channel signature only."""
    identifiers = (
        str(getattr(track, "semantic_id", "")),
        str(getattr(track, "title", "")),
    )
    identity_matches = [block for block in blocks if _identifiers_match(identifiers, block.track)]
    if len(identity_matches) == 1:
        return identity_matches[0]
    if len(identity_matches) > 1:
        raise SemanticActionError(
            "semantic_contract_incomplete",
            f"Track identity is ambiguous for '{getattr(track, 'semantic_id', '')}'.",
        )
    track_signature = _track_binding_signature(track)
    if not track_signature:
        return None
    signature_matches = [
        block for block in blocks if _channel_signature(block.body) == track_signature
    ]
    if len(signature_matches) == 1:
        return signature_matches[0]
    if len(signature_matches) > 1:
        raise SemanticActionError(
            "semantic_contract_incomplete",
            f"Track channel signature is ambiguous for '{getattr(track, 'semantic_id', '')}'.",
        )
    return None


def _normalize_track_identifier(value: str) -> str:
    """Normalize human track labels for exact identity comparison."""
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _identifiers_match(identifiers: tuple[str, ...], requested: str) -> bool:
    """Return whether a requested track label matches one known identity."""
    normalized_requested = _normalize_track_identifier(requested)
    return bool(normalized_requested) and normalized_requested in {
        _normalize_track_identifier(identifier) for identifier in identifiers if identifier
    }


def _channel_signature(value: str) -> tuple[str, ...]:
    """Build an order-independent signature from explicit channel clauses."""
    channels = re.findall(
        r"\b[A-Z][A-Z0-9_]*\b(?=\s*(?:→|->))",
        value,
    )
    return tuple(sorted(item.casefold() for item in channels))


def _track_binding_signature(track: object) -> tuple[str, ...]:
    """Build the same signature from a generated track's binding channels."""
    return tuple(
        sorted(
            str(getattr(binding, "channel", "")).casefold()
            for binding in getattr(track, "bindings", ())
        )
    )


def _find_track_index(
    tracks: list[object],
    *,
    identifiers: tuple[str, ...],
    channel_signature: tuple[str, ...],
    used_indices: set[int],
) -> int:
    """Find one unused response track by identity, then by channel signature."""
    identity_matches = [
        index
        for index, track in enumerate(tracks)
        if index not in used_indices
        and _identifiers_match(
            identifiers,
            str(getattr(track, "semantic_id", "")),
        )
    ]
    if not identity_matches:
        identity_matches = [
            index
            for index, track in enumerate(tracks)
            if index not in used_indices
            and _identifiers_match(
                identifiers,
                str(getattr(track, "title", "")),
            )
        ]
    if not identity_matches and channel_signature:
        identity_matches = [
            index
            for index, track in enumerate(tracks)
            if index not in used_indices and _track_binding_signature(track) == channel_signature
        ]
    if len(identity_matches) != 1:
        raise SemanticActionError(
            "semantic_contract_incomplete",
            f"Track identity could not be resolved uniquely for '{identifiers[0]}'.",
        )
    return identity_matches[0]


def _normalize_track_request_semantics(track: object, body: str) -> object:
    """Normalize only presentation fields explicitly present in one track clause."""
    curve_specs = list(_CURVE_REQUIREMENT_RE.finditer(body))
    ordinal_specs = list(_ORDINAL_CURVE_REQUIREMENT_RE.finditer(body))
    bindings = list(getattr(track, "bindings", ()))
    used_specs: set[int] = set()
    shared_label = _MULTI_BINDING_LABEL_RE.search(body)
    for binding_index, binding in enumerate(bindings):
        if getattr(binding, "kind", None) == "raster":
            bindings[binding_index] = _normalize_raster_request_semantics(binding, body)
            continue
        matching = _match_curve_requirement(binding, curve_specs, used_specs)
        if matching is None and binding_index < len(ordinal_specs):
            matching = ordinal_specs[binding_index]
        if matching is None:
            continue
        if matching in curve_specs:
            used_specs.add(curve_specs.index(matching))
        if matching is not None:
            bindings[binding_index] = _normalize_curve_request_semantics(binding, matching)
        if shared_label is not None:
            label = _match_group_value(shared_label, "label")
            if label:
                bindings[binding_index] = bindings[binding_index].model_copy(
                    update={"label": label}
                )
    updates: dict[str, object] = {}
    if bindings:
        updates["bindings"] = tuple(bindings)
    if getattr(track, "kind", None) == "array":
        updates.update(_normalize_array_track_request_semantics(body))
    return track.model_copy(update=updates) if updates else track


def _match_curve_requirement(
    binding: object,
    specs: list[re.Match[str]],
    used_specs: set[int],
) -> re.Match[str] | None:
    """Select a request curve clause by exact channel and occurrence order."""
    channel = str(getattr(binding, "channel", "")).casefold()
    for index, spec in enumerate(specs):
        if index not in used_specs and spec.group("channel").casefold() == channel:
            return spec
    return None


def _normalize_curve_request_semantics(binding: object, spec: re.Match[str]) -> object:
    """Normalize one curve scale/style from an explicit request clause."""
    scale = SemanticScale(
        kind=spec.group("kind").casefold(),
        minimum=float(spec.group("minimum")),
        maximum=float(spec.group("maximum")),
        reverse=spec.group("reverse") is not None,
    )
    style_values: dict[str, object] = {
        "color": spec.group("color"),
        "line_width": float(spec.group("line_width")),
        "line_style": spec.group("line_style") or "solid",
    }
    style = AuthoringStyleIntent(**style_values)
    updates: dict[str, object] = {"scale": scale, "style": style}
    label = _match_group_value(spec, "label")
    if label:
        updates["label"] = label
    return binding.model_copy(update=updates)


def _match_group_value(match: re.Match[str], name: str) -> str | None:
    """Return one normalized value from a quoted-or-plain regex group."""
    value = match.groupdict().get(f"{name}_quoted")
    if value is None:
        value = match.groupdict().get(f"{name}_single")
    if value is None:
        value = match.groupdict().get(f"{name}_plain")
    return value.strip() if value and value.strip() else None


def _normalize_array_track_request_semantics(body: str) -> dict[str, object]:
    """Normalize explicit raster scale, grid, colorbar, and sample-axis clauses."""
    updates: dict[str, object] = {}
    scale_match = re.search(
        r"linear\s+track\s+scale\s+(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\.\."
        r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)",
        body,
        flags=re.IGNORECASE,
    )
    if scale_match:
        updates["x_scale"] = SemanticScale(
            kind="linear",
            minimum=float(scale_match.group("minimum")),
            maximum=float(scale_match.group("maximum")),
        )
    if re.search(r"hide\s+both\s+vertical\s+main\s+and\s+secondary\s+grid", body, re.I):
        updates["grid"] = SemanticGrid(
            vertical_main_visible=False,
            vertical_secondary_visible=False,
        )
    return updates


def _normalize_raster_request_semantics(binding: object, body: str) -> object:
    """Normalize explicit raster profile, colorbar, and sample-axis clauses."""
    updates: dict[str, object] = {}
    label_match = _RASTER_LABEL_RE.search(body)
    label = _match_group_value(label_match, "label") if label_match else None
    if label:
        updates["label"] = label
    profile_match = re.search(r"profile\s+(?P<profile>[a-z_]+)", body, re.I)
    if profile_match:
        updates["profile"] = profile_match.group("profile").casefold()
    if re.search(r"gray_r", body, re.I):
        updates["colormap"] = "gray_r"
    colorbar_match = re.search(
        r"colorbar\s+enabled\s+with\s+label\s+(?P<label>[A-Za-z][A-Za-z ]*?)\s+"
        r"in\s+the\s+(?P<position>header|right)",
        body,
        re.I,
    )
    if colorbar_match:
        updates.update(
            {
                "colorbar_enabled": True,
                "colorbar_label": colorbar_match.group("label").strip(),
                "colorbar_position": colorbar_match.group("position").casefold(),
            }
        )
    axis_match = re.search(
        r"sample\s+axis\s+enabled\s+in\s+(?P<unit>[A-Za-z]+)\s+from\s+"
        r"(?P<minimum>-?[0-9]+(?:\.[0-9]+)?)\s+to\s+"
        r"(?P<maximum>-?[0-9]+(?:\.[0-9]+)?)\s+with\s+(?P<ticks>[0-9]+)\s+ticks,\s+"
        r"source\s+origin\s+(?P<origin>-?[0-9]+(?:\.[0-9]+)?)\s+and\s+step\s+"
        r"(?P<step>-?[0-9]+(?:\.[0-9]+)?)",
        body,
        re.I,
    )
    if axis_match:
        updates["sample_axis"] = SemanticSampleAxis(
            unit=axis_match.group("unit").casefold(),
            minimum=float(axis_match.group("minimum")),
            maximum=float(axis_match.group("maximum")),
            tick_count=int(axis_match.group("ticks")),
            source_origin=float(axis_match.group("origin")),
            source_step=float(axis_match.group("step")),
        )
    return binding.model_copy(update=updates) if updates else binding


def _validate_reconstruct_completeness(
    action: SectionSemanticAction,
    task: SectionTask,
    context: ResolvedSectionContext,
) -> None:
    """Require explicit reconstruction channels and tracks from the scoped task."""
    if action.action != "reconstruct":
        return
    available = {channel.mnemonic for source in context.sources for channel in source.channels}
    required_channels: dict[str, int] = {}
    required_track_numbers: set[str] = set()
    for requirement in task.requirements:
        for channel in re.findall(r"\b[A-Z][A-Z0-9_]+\b(?=\s*->)", requirement):
            if channel in available:
                required_channels[channel] = required_channels.get(channel, 0) + 1
        required_track_numbers.update(re.findall(r"\bTrack\s+(\d+)\b", requirement))

    actual_channels: dict[str, int] = {}
    for track in action.section.tracks:
        for binding in track.bindings:
            actual_channels[binding.channel] = actual_channels.get(binding.channel, 0) + 1
    missing_channels = {
        channel: count - actual_channels.get(channel, 0)
        for channel, count in required_channels.items()
        if actual_channels.get(channel, 0) < count
    }
    expected_tracks = len(required_track_numbers)
    if missing_channels or (expected_tracks and len(action.section.tracks) != expected_tracks):
        details: list[str] = []
        if expected_tracks and len(action.section.tracks) != expected_tracks:
            details.append(
                f"expected {expected_tracks} tracks, received {len(action.section.tracks)}"
            )
        if missing_channels:
            details.append(f"missing channel occurrences: {missing_channels}")
        raise SemanticActionError(
            "semantic_contract_incomplete",
            "The section reconstruction is incomplete: " + "; ".join(details),
        )


def _canonical_failure(
    code: str,
    message: str,
    *,
    normalization: str = "NOT_REACHED",
    worker_obligation: str = "NOT_REACHED",
    semantic_lowering: str = "NOT_REACHED",
    correction: str = "NOT_REACHED",
) -> CanonicalWorkerResult:
    """Create bounded canonical failure evidence without raw provider data."""
    return CanonicalWorkerResult(
        success=False,
        intent_fragment=None,
        diagnostics=(
            SemanticDiagnostic(
                stage="semantic_worker",
                code=code,
                message=message,
                remediation_hint="Return one valid canonical semantic action.",
            ),
        ),
        metrics=SemanticMetrics(),
        stage_evidence=SemanticStageEvidence(
            normalization=normalization,
            worker_obligation=worker_obligation,
            semantic_lowering=semantic_lowering,
            correction=correction,
        ),
    )


def _action_evidence_failure(
    error: SectionActionEvidenceError, *, correction: str = "NOT_REACHED"
) -> CanonicalWorkerResult:
    """Fail closed without discarding an already known contract rejection."""
    result = _canonical_failure(
        "worker_evidence_integrity_failure",
        "Section action evidence could not be retained safely.",
        correction=correction,
    )
    if error.original is None:
        return result
    return replace(
        result,
        diagnostics=result.diagnostics
        + (
            SemanticDiagnostic(
                stage="semantic_worker",
                code=error.original.code,
                message="Section response did not satisfy the deterministic work contract.",
            ),
        ),
    )


def _provider_section_task(task: SectionTask) -> dict[str, object]:
    """Project only planner-wire fields; host provenance never reaches a worker."""
    return {
        "goal": task.goal,
        "capability_ids": task.capability_ids,
        "existing_section_hint": task.existing_section_hint,
        "source_hints": task.source_hints,
        "requirements": task.requirements,
        "constraints": task.constraints,
    }


def _bind_compiled_source(
    action: SectionSemanticAction,
    context: ResolvedSectionContext,
    *,
    work_contract: SectionWorkContract,
) -> SectionSemanticAction:
    """Resolve a compiled source requirement against inspected host candidates."""
    if action.action != "reconstruct":
        return action
    source_handle = work_contract.source_handle or action.section.source_candidate
    try:
        source_index = int(source_handle.removeprefix("source-")) - 1
    except ValueError as error:
        raise SemanticActionError(
            "source_candidate_missing", "The work contract source handle is invalid."
        ) from error
    if source_index < 0 or source_index >= len(context.sources):
        raise SemanticActionError(
            "source_candidate_missing", "The work contract source handle is not grounded."
        )
    selected = context.sources[source_index]
    return action.model_copy(
        update={
            "section": action.section.model_copy(update={"source_candidate": selected.candidate_id})
        }
    )


def _section_owner_alias_map(
    obligations: tuple[RequestObligation, ...],
) -> dict[str, str]:
    """Map binding owner slugs to their exact normalized track-owner identity."""
    relevant = [
        item
        for item in obligations
        if item.state is ObligationState.SET
        and item.owner_ref != "request"
        and item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK, OwnerKind.BINDING}
    ]
    track_owners = tuple(
        dict.fromkeys(
            item.owner_ref
            for item in relevant
            if item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK}
        )
    )
    track_by_identity: dict[str, str] = {}
    for owner in track_owners:
        identity = _normalized_identity(owner)
        existing = track_by_identity.get(identity)
        if existing is not None and existing != owner:
            raise SemanticActionError(
                "worker_grounding_ambiguous",
                "Distinct request track owners share one normalized identity.",
            )
        track_by_identity[identity] = owner

    aliases = {owner: owner for owner in track_owners}
    binding_owners = tuple(
        dict.fromkeys(item.owner_ref for item in relevant if item.owner_kind is OwnerKind.BINDING)
    )
    for owner in binding_owners:
        canonical = track_by_identity.get(_normalized_identity(owner), owner)
        aliases[owner] = canonical
    return aliases


def resolve_section_object_bindings(
    action: SectionSemanticAction,
    obligations: tuple[RequestObligation, ...],
) -> SectionObjectBindings:
    """Bind request owners to proposal objects once, before presentation overlay."""
    if action.action == "reconstruct":
        tracks = [
            track.model_dump(mode="json", exclude_unset=True) for track in action.section.tracks
        ]
    elif action.action == "add_track":
        tracks = [action.track.model_dump(mode="json", exclude_unset=True)]
    else:
        return SectionObjectBindings()

    relevant = [
        item
        for item in obligations
        if item.state is ObligationState.SET
        and item.owner_ref != "request"
        and item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK, OwnerKind.BINDING}
    ]
    alias_map = _section_owner_alias_map(obligations)
    owners = tuple(
        dict.fromkeys(alias_map.get(item.owner_ref, item.owner_ref) for item in relevant)
    )
    candidates_by_owner: dict[str, tuple[int, ...]] = {}
    for owner in owners:
        owner_facts = [
            item for item in relevant if alias_map.get(item.owner_ref, item.owner_ref) == owner
        ]
        owner_identities = {
            _normalized_identity(reference)
            for reference, canonical in alias_map.items()
            if canonical == owner
        }
        owner_identities.add(_normalized_identity(owner))
        explicit = tuple(
            index
            for index, track in enumerate(tracks)
            if {
                _normalized_identity(str(track.get("semantic_id", ""))),
                _normalized_identity(str(track.get("title", ""))),
            }
            & owner_identities
        )
        structural = _structural_track_candidates(tracks, owner_facts)
        if len(explicit) > 1:
            raise SemanticActionError(
                "worker_grounding_ambiguous",
                "A request track identity matches multiple proposal tracks.",
            )
        if explicit:
            if len(structural) > 1 or (structural and structural[0] != explicit[0]):
                raise SemanticActionError(
                    "worker_grounding_ambiguous",
                    "Explicit and structural track identity evidence conflicts.",
                )
            candidates_by_owner[owner] = explicit
        elif structural:
            candidates_by_owner[owner] = structural
        else:
            raise SemanticActionError(
                "worker_grounding_unresolved",
                "A request track cannot be bound by exact identity or complete structure.",
            )

    assignments: list[dict[str, int]] = []

    def assign(position: int, selected: dict[str, int], used: set[int]) -> None:
        if len(assignments) > 1:
            return
        if position == len(owners):
            assignments.append(dict(selected))
            return
        owner = owners[position]
        for index in candidates_by_owner[owner]:
            if index in used:
                continue
            selected[owner] = index
            used.add(index)
            assign(position + 1, selected, used)
            used.remove(index)
            del selected[owner]

    assign(0, {}, set())
    if len(assignments) != 1:
        code = "worker_grounding_ambiguous" if assignments else "worker_grounding_conflict"
        raise SemanticActionError(code, "Request track owners do not have one unique assignment.")

    track_indices = assignments[0]
    request_facts = [
        item
        for item in obligations
        if item.state is ObligationState.SET
        and item.owner_ref == "request"
        and item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK, OwnerKind.BINDING}
    ]
    if request_facts:
        request_candidates = _tracks_for_request_owned_facts(tracks, request_facts)
        if len(request_candidates) == 1:
            track_indices["request"] = request_candidates[0]

    for reference, canonical in alias_map.items():
        if canonical in track_indices:
            track_indices[reference] = track_indices[canonical]

    binding_indices: list[tuple[str, str, int | None]] = []
    binding_owners = tuple(
        dict.fromkeys(
            item.owner_ref
            for item in obligations
            if item.state is ObligationState.SET and item.owner_kind is OwnerKind.BINDING
        )
    )
    if (
        any(item.owner_kind is OwnerKind.BINDING for item in request_facts)
        and "request" not in binding_owners
    ):
        binding_owners = (*binding_owners, "request")
    for owner in binding_owners:
        track_index = track_indices.get(owner)
        if track_index is None:
            continue
        facts_by_slot: dict[str, list[RequestObligation]] = {}
        for item in obligations:
            if item.state is not ObligationState.SET:
                continue
            if item.owner_ref == owner and item.owner_kind is OwnerKind.BINDING and item.slot_key:
                facts_by_slot.setdefault(item.slot_key, []).append(item)
        bindings = list(tracks[track_index].get("bindings", []))
        for slot, facts in facts_by_slot.items():
            try:
                binding_index = _resolve_binding_slot(bindings, facts, slot)
            except SemanticActionError as error:
                raise SemanticActionError(
                    "worker_grounding_unresolved",
                    "A request binding slot cannot be grounded uniquely.",
                ) from error
            if binding_index is None:
                ordinal = re.search(r"\.binding\.(\d+)$", slot)
                if ordinal is not None:
                    binding_index = int(ordinal.group(1)) - 1
            binding_indices.append((owner, slot, binding_index))

    return SectionObjectBindings(
        track_indices=tuple(track_indices.items()),
        binding_indices=tuple(binding_indices),
    )


def _structural_track_candidates(
    tracks: list[dict[str, object]], requirements: list[RequestObligation]
) -> tuple[int, ...]:
    """Find exact ordered typed signatures, preserving binding occurrences."""
    expected_kind = next(
        (str(item.value).casefold() for item in requirements if item.field == "kind"), None
    )
    if expected_kind is None and any(
        item.owner_kind is OwnerKind.ARRAY_TRACK for item in requirements
    ):
        expected_kind = "array"
    channel_facts = [
        item
        for item in requirements
        if item.owner_kind is OwnerKind.BINDING and item.field == "channel"
    ]
    if not channel_facts or any(not item.slot_key for item in channel_facts):
        return ()

    def slot_order(item: RequestObligation) -> tuple[int, str]:
        match = re.search(r"\.binding\.(\d+)$", item.slot_key or "")
        if match:
            return int(match.group(1)), item.slot_key or ""
        if item.slot_key and item.slot_key.endswith(".binding.raster"):
            return 2**31 - 1, item.slot_key
        return 2**31 - 2, item.slot_key or ""

    expected_channels = tuple(
        str(item.value).casefold() for item in sorted(channel_facts, key=slot_order)
    )
    if len({item.slot_key for item in channel_facts}) != len(channel_facts):
        raise SemanticActionError(
            "worker_grounding_ambiguous", "A request owner declares duplicate binding slots."
        )
    raster_fields = {
        "raster_profile",
        "raster_colormap",
        "colorbar_enabled",
        "colorbar_label",
        "colorbar_position",
        "sample_axis_enabled",
        "sample_axis_unit",
        "sample_axis_source_origin",
        "sample_axis_source_step",
    }
    expected_binding_kind = (
        "raster"
        if expected_kind == "array" or any(item.field in raster_fields for item in requirements)
        else "curve"
    )
    matches: list[int] = []
    for index, track in enumerate(tracks):
        if expected_kind and str(track.get("kind", "")).casefold() != expected_kind:
            continue
        actual_signature = tuple(
            (
                "raster" if _is_raster_binding_data(binding) else "curve",
                str(binding.get("channel", "")).casefold(),
            )
            for binding in track.get("bindings", [])
            if isinstance(binding, dict)
        )
        expected_signature = tuple(
            (expected_binding_kind, channel) for channel in expected_channels
        )
        if actual_signature == expected_signature:
            matches.append(index)
    return tuple(matches)


def apply_compiled_requirements(
    action: SectionSemanticAction,
    obligations: tuple[RequestObligation, ...],
    *,
    object_bindings: SectionObjectBindings | None = None,
) -> SectionSemanticAction:
    """Apply host-owned requirements to objects in the shared binding result."""
    if object_bindings is None:
        object_bindings = resolve_section_object_bindings(action, obligations)
    requirements = [item for item in obligations if item.state is ObligationState.SET]
    if action.action == "update_curve_scale":
        return action
    if action.action == "reconstruct":
        section_data = action.section.model_dump(mode="json", exclude_unset=True)
        tracks = list(section_data["tracks"])
        for owner_ref in dict.fromkeys(
            item.owner_ref
            for item in requirements
            if item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK, OwnerKind.BINDING}
        ):
            owned = [item for item in requirements if item.owner_ref == owner_ref]
            track_index = object_bindings.track_index(owner_ref)
            if track_index is None:
                if owner_ref == "request":
                    continue
                raise SemanticActionError(
                    "worker_grounding_unresolved", "A request track has no host binding."
                )
            if not 0 <= track_index < len(tracks):
                raise SemanticActionError(
                    "worker_grounding_unresolved", "A request track binding is out of range."
                )
            tracks[track_index] = _apply_track_requirements(
                tracks[track_index],
                owned,
                object_bindings=object_bindings,
                owner_ref=owner_ref,
            )
        for item in requirements:
            if item.owner_kind is OwnerKind.SECTION and item.field == "target":
                section_data["title"] = item.value
        section_data["tracks"] = tracks
        return SectionSemanticActionResponse.model_validate(
            {"action": "reconstruct", "section": section_data}
        ).root
    if action.action == "add_track":
        track_data = action.track.model_dump(mode="json", exclude_unset=True)
        owned = [
            item for item in requirements if item.owner_kind in {OwnerKind.TRACK, OwnerKind.BINDING}
        ]
        track_data = _apply_track_requirements(
            track_data,
            owned,
            object_bindings=object_bindings,
            owner_ref=owned[0].owner_ref if owned else "",
        )
        return SectionSemanticActionResponse.model_validate(
            {"action": "add_track", "track": track_data}
        ).root
    return action


def _apply_track_requirements(
    track: dict[str, object],
    requirements: list[RequestObligation],
    *,
    object_bindings: SectionObjectBindings,
    owner_ref: str,
) -> dict[str, object]:
    """Apply track and binding facts while retaining ordered collection identity."""
    updated = dict(track)
    scale_values: dict[str, object] = dict(updated.get("x_scale") or {})
    grid_values: dict[str, object] = dict(updated.get("grid") or {})
    bindings = [dict(binding) for binding in updated.get("bindings", [])]
    binding_requirements: dict[str, list[RequestObligation]] = {}
    for item in requirements:
        if item.owner_kind is OwnerKind.BINDING:
            if item.slot_key is not None:
                binding_requirements.setdefault(item.slot_key, []).append(item)
            continue
        field = item.field
        if field == "title":
            updated["title"] = item.value
        elif field == "width_mm":
            updated["width_mm"] = item.value
        elif field.startswith("track_scale_"):
            scale_field = {
                "track_scale_kind": "kind",
                "track_scale_minimum": "minimum",
                "track_scale_maximum": "maximum",
            }[field]
            scale_values[scale_field] = item.value
        elif field in {"vertical_main_visible", "vertical_secondary_visible"}:
            grid_values[field] = item.value

    for slot, facts in binding_requirements.items():
        binding_index = object_bindings.binding_index(owner_ref, slot)
        if binding_index is None or not 0 <= binding_index < len(bindings):
            continue
        binding = bindings[binding_index]
        expected_channel = next((item.value for item in facts if item.field == "channel"), None)
        if (
            expected_channel is not None
            and str(binding.get("channel", "")).casefold() != str(expected_channel).casefold()
        ):
            continue
        scale = dict(binding.get("scale") or {})
        style = dict(binding.get("style") or {})
        sample_axis = dict(binding.get("sample_axis") or {})
        for item in facts:
            field = item.field
            if field == "channel":
                continue
            if field == "label":
                binding["label"] = item.value
            elif field in {"scale_kind", "scale_minimum", "scale_maximum", "scale_reverse"}:
                scale_field = {
                    "scale_kind": "kind",
                    "scale_minimum": "minimum",
                    "scale_maximum": "maximum",
                    "scale_reverse": "reverse",
                }[field]
                scale[scale_field] = item.value
            elif field in {"color", "line_width", "line_style"}:
                style[field] = item.value
            elif field.startswith("sample_axis_"):
                sample_field = {
                    "sample_axis_enabled": None,
                    "sample_axis_unit": "unit",
                    "sample_axis_minimum": "minimum",
                    "sample_axis_maximum": "maximum",
                    "sample_axis_tick_count": "tick_count",
                    "sample_axis_source_origin": "source_origin",
                    "sample_axis_source_step": "source_step",
                }[field]
                if sample_field is not None:
                    sample_axis[sample_field] = item.value
            elif field == "raster_profile":
                binding["profile"] = item.value
            elif field == "raster_colormap":
                binding["colormap"] = item.value
            elif field.startswith("colorbar_"):
                binding[field] = item.value
        if scale:
            binding["scale"] = scale
        if style:
            binding["style"] = style
        if sample_axis:
            binding["sample_axis"] = sample_axis
        bindings[binding_index] = binding
    if scale_values:
        updated["x_scale"] = scale_values
    if grid_values:
        updated["grid"] = grid_values
    updated["bindings"] = bindings

    return (
        TypeAdapter(TrackSemanticDraft)
        .validate_python(updated)
        .model_dump(mode="json", exclude_unset=True)
    )


def _resolve_binding_slot(
    bindings: list[dict[str, object]],
    facts: list[RequestObligation],
    slot: str,
) -> int | None:
    """Resolve one ordered slot by explicit channel and request occurrence."""
    if slot.endswith(".binding.raster"):
        candidates = [
            index for index, binding in enumerate(bindings) if _is_raster_binding_data(binding)
        ]
        if len(candidates) == 1:
            return candidates[0]
        raise SemanticActionError(
            "semantic_contract_incomplete",
            "A compiled raster requirement has no unique semantic identity.",
        )
    ordinal_match = re.search(r"\.binding\.(\d+)$", slot)
    expected_channel = next((str(item.value) for item in facts if item.field == "channel"), None)
    if ordinal_match:
        index = int(ordinal_match.group(1)) - 1
        if index < len(bindings):
            return index
        return None
    candidates = [
        index
        for index, binding in enumerate(bindings)
        if expected_channel is None
        or str(binding.get("channel", "")).casefold() == expected_channel.casefold()
    ]
    if len(candidates) != 1:
        raise SemanticActionError(
            "semantic_contract_incomplete",
            "A compiled binding requirement has no unique semantic identity.",
        )
    return candidates[0]


def _normalized_identity(value: str) -> str:
    """Normalize display text for exact request-local identity matching."""
    return "_".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _is_raster_binding_data(binding: dict[str, object]) -> bool:
    """Recognize canonical raster bindings from their raster-only fields."""
    return any(
        binding.get(field) is not None
        for field in ("profile", "colormap", "sample_axis", "colorbar_enabled")
    )


def _tracks_for_request_owned_facts(
    tracks: list[dict[str, object]], requirements: list[RequestObligation]
) -> list[int]:
    """Find tracks uniquely compatible with owner-neutral compiled facts."""
    requested_channels = Counter(
        str(item.value).casefold()
        for item in requirements
        if item.owner_kind is OwnerKind.BINDING and item.field == "channel"
    )
    if not requested_channels:
        return list(range(len(tracks)))
    eligible: list[int] = []
    for index, track in enumerate(tracks):
        available_channels = Counter(
            str(binding.get("channel", "")).casefold()
            for binding in track.get("bindings", [])
            if isinstance(binding, dict)
        )
        has_requested_multiplicity = all(
            available_channels[channel] >= count for channel, count in requested_channels.items()
        )
        if has_requested_multiplicity:
            eligible.append(index)
    return eligible


def _collect_validation_issues(
    action: SectionSemanticAction,
    obligations: tuple[RequestObligation, ...],
    *,
    section_context: ResolvedSectionContext,
    section_title: str | None,
    object_bindings: SectionObjectBindings,
) -> ValidationIssueSet:
    """Collect each unsatisfied requirement independently in stable source order."""
    issues: list[ValidationIssue] = []
    slotted_channel_ids: set[str] = set()
    if action.action == "reconstruct":
        for item in obligations:
            if not (
                item.owner_kind is OwnerKind.BINDING
                and item.field == "channel"
                and item.slot_key
                and item.state is ObligationState.SET
            ):
                continue
            slotted_channel_ids.add(item.requirement_id)
            track_index = object_bindings.track_index(item.owner_ref)
            binding_index = object_bindings.binding_index(item.owner_ref, item.slot_key)
            try:
                track = action.section.tracks[track_index] if track_index is not None else None
                actual_channel = (
                    track.bindings[binding_index].channel
                    if track is not None
                    and binding_index is not None
                    and 0 <= binding_index < len(track.bindings)
                    else None
                )
            except (IndexError, TypeError):
                actual_channel = None
            if actual_channel != item.value:
                issues.append(
                    ValidationIssue(
                        requirement_id=item.requirement_id,
                        owner_kind=item.owner_kind,
                        owner_ref=item.owner_ref,
                        field=item.field,
                        slot_key=item.slot_key,
                        code="binding_slot_unsatisfied",
                        expected_value=item.value,
                    )
                )
    for item in obligations:
        if item.state is ObligationState.FORBIDDEN or item.kind is ObligationKind.PRESERVATION:
            continue
        if item.requirement_id in slotted_channel_ids:
            continue
        try:
            validate_section_obligations(
                action,
                (item,),
                section_context=section_context,
                section_title=section_title,
                object_bindings=object_bindings,
            )
        except (ValueError, SemanticActionError):
            issues.append(
                ValidationIssue(
                    requirement_id=item.requirement_id,
                    owner_kind=item.owner_kind,
                    owner_ref=item.owner_ref,
                    field=item.field,
                    slot_key=item.slot_key,
                    code="requirement_unsatisfied",
                    expected_value=item.value,
                )
            )
    return ValidationIssueSet(issues=tuple(issues))


def _build_repair_contract(
    baseline: SectionSemanticAction,
    issues: ValidationIssueSet,
    *,
    object_bindings: SectionObjectBindings,
) -> RepairContract:
    """Derive permitted edits from issue identity, not a broad field allowlist."""
    operation_groups: dict[tuple[str, str, str | None], list[ValidationIssue]] = {}
    if baseline.action == "reconstruct":
        tracks = baseline.section.tracks
        for issue in issues.issues:
            track_index = object_bindings.track_index(issue.owner_ref)
            if track_index is None or not 0 <= track_index < len(tracks):
                raise SemanticActionError(
                    "worker_repair_target_unresolved", "A repair issue has no bound track."
                )
            track = tracks[track_index]
            prefix = f"section.tracks[{track.semantic_id}]"
            if issue.owner_kind is OwnerKind.BINDING:
                binding_index = (
                    object_bindings.binding_index(issue.owner_ref, issue.slot_key)
                    if issue.slot_key
                    else None
                )
                binding = (
                    track.bindings[binding_index]
                    if binding_index is not None and 0 <= binding_index < len(track.bindings)
                    else None
                )
                if binding is None:
                    prefix += ".bindings"
                    operation_key = (prefix, "ADD", issue.slot_key)
                    operation_groups.setdefault(operation_key, []).append(issue)
                    continue
                prefix += f".bindings[{binding.semantic_id}].{_semantic_field(issue.field)}"
            else:
                prefix += f".{_semantic_field(issue.field)}"
            operation_key = (prefix, "REPLACE", issue.slot_key)
            operation_groups.setdefault(operation_key, []).append(issue)
    operations: list[RepairOperation] = []
    for (path_prefix, operation, slot_key), grouped_issues in operation_groups.items():
        first = grouped_issues[0]
        track_order: tuple[str, ...] = ()
        if operation == "ADD" and baseline.action == "reconstruct":
            track_index = object_bindings.track_index(first.owner_ref)
            if track_index is None or not 0 <= track_index < len(baseline.section.tracks):
                raise SemanticActionError(
                    "worker_repair_target_unresolved", "An ADD operation has no bound track."
                )
            track = baseline.section.tracks[track_index]
            track_order = tuple(binding.semantic_id for binding in track.bindings)
        expected_channel = next(
            (issue.expected_value for issue in grouped_issues if issue.field == "channel"),
            None,
        )
        operations.append(
            RepairOperation(
                requirement_id=first.requirement_id,
                requirement_refs=tuple(issue.requirement_id for issue in grouped_issues),
                path_prefix=path_prefix,
                operation=operation,  # type: ignore[arg-type]
                owner_kind=first.owner_kind,
                owner_ref=first.owner_ref,
                field=None if operation == "ADD" else first.field,
                slot_key=slot_key,
                expected_value=expected_channel if operation == "ADD" else first.expected_value,
                permitted_fields=tuple(dict.fromkeys(issue.field for issue in grouped_issues)),
                order_precondition=track_order,
                order_postcondition=(
                    (*track_order, f"<{slot_key}>") if operation == "ADD" else track_order
                ),
            )
        )
    canonical = _canonical_action_json(baseline)
    return RepairContract(
        baseline_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        operations=tuple(operations),
        postconditions=issues.issues,
    )


def _semantic_field(field: str) -> str:
    return {
        "scale_kind": "scale.kind",
        "scale_minimum": "scale.minimum",
        "scale_maximum": "scale.maximum",
        "scale_reverse": "scale.reverse",
        "track_scale_kind": "x_scale.kind",
        "track_scale_minimum": "x_scale.minimum",
        "track_scale_maximum": "x_scale.maximum",
        "color": "style.color",
        "line_width": "style.line_width",
        "line_style": "style.line_style",
        "raster_profile": "profile",
        "raster_colormap": "colormap",
        "sample_axis_enabled": "sample_axis",
        "sample_axis_unit": "sample_axis.unit",
        "sample_axis_minimum": "sample_axis.minimum",
        "sample_axis_maximum": "sample_axis.maximum",
        "sample_axis_tick_count": "sample_axis.tick_count",
        "sample_axis_source_origin": "sample_axis.source_origin",
        "sample_axis_source_step": "sample_axis.source_step",
    }.get(field, field)


def _canonical_action_json(action: SectionSemanticAction) -> str:
    return json.dumps(
        action.model_dump(mode="json", exclude_unset=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _verify_repair_candidate(
    baseline: SectionSemanticAction,
    candidate: SectionSemanticAction,
    contract: RepairContract,
    *,
    object_bindings: SectionObjectBindings,
) -> None:
    """Reject identity/order/cardinality changes outside exact repair paths."""
    if (
        hashlib.sha256(_canonical_action_json(baseline).encode()).hexdigest()
        != contract.baseline_sha256
    ):
        raise SemanticActionError("worker_repair_baseline_drift", "Repair baseline changed.")
    if baseline.action != candidate.action:
        raise SemanticActionError("worker_correction_scope_violation", "Action identity changed.")
    allowed_paths = {
        item.path_prefix for item in contract.operations if item.operation == "REPLACE"
    }
    baseline_data = baseline.model_dump(mode="json", exclude_unset=True)
    candidate_data = candidate.model_dump(mode="json", exclude_unset=True)
    changed_paths = _semantic_diff_paths(baseline_data, candidate_data)
    allowed_added_objects: set[str] = set()
    additions_by_operation: list[tuple[RepairOperation, object]] = []
    add_operations = [item for item in contract.operations if item.operation == "ADD"]
    grouped_adds: dict[str, list[RepairOperation]] = {}
    for operation in add_operations:
        grouped_adds.setdefault(operation.path_prefix, []).append(operation)
    for parent_path, operations in grouped_adds.items():
        added = _added_bindings(baseline, candidate, parent_path)
        if len(added) != len(operations):
            raise SemanticActionError(
                "worker_correction_scope_violation",
                "Correction added a different number of bindings than authorized.",
            )
        track_semantic_id = re.search(r"section\.tracks\[([^]]+)\]\.bindings", parent_path)
        if track_semantic_id is None:
            raise SemanticActionError(
                "worker_correction_scope_violation",
                "Correction target is not a grounded binding collection.",
            )
        before_track = next(
            item
            for item in baseline.section.tracks
            if item.semantic_id == track_semantic_id.group(1)
        )
        after_track = next(
            item
            for item in candidate.section.tracks
            if item.semantic_id == track_semantic_id.group(1)
        )
        before_ids = tuple(item.semantic_id for item in before_track.bindings)
        after_ids = tuple(item.semantic_id for item in after_track.bindings)
        if after_ids[: len(before_ids)] != before_ids:
            raise SemanticActionError(
                "worker_correction_scope_violation",
                "Correction changed existing binding order.",
            )
        new_ids = after_ids[len(before_ids) :]
        sorted_operations = sorted(
            operations,
            key=lambda item: _binding_slot_index(item.slot_key),
        )
        if len(new_ids) != len(sorted_operations):
            raise SemanticActionError(
                "worker_correction_scope_violation",
                "Correction changed binding cardinality outside the repair contract.",
            )
        for offset, operation in enumerate(sorted_operations):
            slot_index = _binding_slot_index(operation.slot_key)
            if slot_index != len(before_ids) + offset:
                raise SemanticActionError(
                    "worker_correction_scope_violation",
                    "Authorized binding slot does not match append order.",
                )
            binding = after_track.bindings[slot_index]
            if str(binding.channel).casefold() != str(operation.expected_value).casefold():
                raise SemanticActionError(
                    "worker_correction_scope_violation",
                    "Correction did not add the required binding channel.",
                )
            binding_path = f"{parent_path}[{binding.semantic_id}]"
            allowed_added_objects.add(binding_path)
            additions_by_operation.append((operation, binding))
    for path in changed_paths:
        if path in allowed_paths or any(
            path == prefix or path.startswith(prefix + ".") for prefix in allowed_added_objects
        ):
            continue
        raise SemanticActionError(
            "worker_correction_scope_violation",
            "Correction changed a field outside its exact repair contract.",
        )
    for operation in contract.operations:
        if operation.operation == "REPLACE":
            actual = _read_operation_value(candidate, operation, object_bindings=object_bindings)
            if actual != operation.expected_value:
                raise SemanticActionError(
                    "worker_correction_scope_violation",
                    "Correction did not apply the exact authorized value.",
                )
    for operation, binding in additions_by_operation:
        for issue in contract.postconditions:
            if issue.slot_key != operation.slot_key or issue.owner_ref != operation.owner_ref:
                continue
            actual = _read_binding_issue_value(binding, issue.field)
            if actual != issue.expected_value:
                raise SemanticActionError(
                    "worker_correction_scope_violation",
                    "Added binding does not satisfy its exact compiled postconditions.",
                )


def _binding_slot_index(slot_key: str | None) -> int:
    """Return a one-based request slot index, rejecting unindexed repair slots."""
    match = re.search(r"\.binding\.(\d+)$", slot_key or "")
    if match is None:
        raise SemanticActionError(
            "worker_repair_contract_ambiguous",
            "An added binding repair lacks an exact ordered slot.",
        )
    return int(match.group(1)) - 1


def _read_operation_value(
    action: SectionSemanticAction,
    operation: RepairOperation,
    *,
    object_bindings: SectionObjectBindings,
) -> object:
    """Read the exact owner field authorized by one REPLACE operation."""
    if operation.owner_kind is OwnerKind.BINDING:
        track_index = object_bindings.track_index(operation.owner_ref)
        binding_index = (
            object_bindings.binding_index(operation.owner_ref, operation.slot_key)
            if operation.slot_key
            else None
        )
        track = (
            action.section.tracks[track_index]
            if track_index is not None and 0 <= track_index < len(action.section.tracks)
            else None
        )
        binding = (
            track.bindings[binding_index]
            if track is not None
            and binding_index is not None
            and 0 <= binding_index < len(track.bindings)
            else None
        )
        if binding is None or operation.field is None:
            raise SemanticActionError(
                "worker_correction_scope_violation",
                "Corrected binding target could not be resolved.",
            )
        return _read_binding_issue_value(binding, operation.field)
    if action.action != "reconstruct":
        return None
    track_index = object_bindings.track_index(operation.owner_ref)
    track = (
        action.section.tracks[track_index]
        if track_index is not None and 0 <= track_index < len(action.section.tracks)
        else None
    )
    if track is None:
        raise SemanticActionError(
            "worker_correction_scope_violation", "Corrected track target could not be resolved."
        )
    if operation.field is None:
        return None
    if operation.field.startswith("track_scale_"):
        scale_field = operation.field.removeprefix("track_scale_")
        return getattr(track.x_scale, scale_field, None)
    if operation.field in {"vertical_main_visible", "vertical_secondary_visible"}:
        return getattr(track.grid, operation.field, None)
    return getattr(track, operation.field, None)


def _read_binding_issue_value(binding: object, field: str) -> object:
    """Read one canonical binding requirement from its typed object."""
    if field == "sample_axis_enabled":
        return getattr(binding, "sample_axis", None) is not None
    if field.startswith("sample_axis_"):
        sample_axis = getattr(binding, "sample_axis", None)
        return getattr(sample_axis, field.removeprefix("sample_axis_"), None)
    if field.startswith("scale_"):
        scale = getattr(binding, "scale", None)
        return getattr(scale, field.removeprefix("scale_"), None)
    if field in {"color", "line_width", "line_style"}:
        return getattr(getattr(binding, "style", None), field, None)
    mapped = {
        "raster_profile": "profile",
        "raster_colormap": "colormap",
    }.get(field, field)
    return getattr(binding, mapped, None)


def _semantic_diff_paths(left: object, right: object, path: str = "") -> set[str]:
    """Diff semantic mappings while keying ordered collections by local identity."""
    if isinstance(left, dict) and isinstance(right, dict):
        result: set[str] = set()
        for key in set(left) | set(right):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                result.add(child)
            else:
                result.update(_semantic_diff_paths(left[key], right[key], child))
        return result
    if isinstance(left, list) and isinstance(right, list):
        identity = "semantic_id"
        left_ids = [item.get(identity) for item in left if isinstance(item, dict)]
        right_ids = [item.get(identity) for item in right if isinstance(item, dict)]
        if len(left_ids) != len(left) or len(right_ids) != len(right):
            return {path}
        if right_ids[: len(left_ids)] != left_ids:
            return {f"{path}.order"}
        result: set[str] = set()
        left_by_id = {str(item[identity]): item for item in left}
        right_by_id = {str(item[identity]): item for item in right}
        for semantic_id in left_ids:
            result.update(
                _semantic_diff_paths(
                    left_by_id[str(semantic_id)],
                    right_by_id[str(semantic_id)],
                    f"{path}[{semantic_id}]",
                )
            )
        for semantic_id in right_ids[len(left_ids) :]:
            result.add(f"{path}[{semantic_id}]")
        return result
    return set() if left == right else {path}


def _added_bindings(
    baseline: SectionSemanticAction,
    candidate: SectionSemanticAction,
    path_prefix: str,
) -> list[object]:
    if baseline.action != "reconstruct" or candidate.action != "reconstruct":
        return []
    match = re.search(r"section\.tracks\[([^]]+)\]\.bindings", path_prefix)
    if match is None:
        return []
    semantic_id = match.group(1)
    before_track = next(
        (track for track in baseline.section.tracks if track.semantic_id == semantic_id), None
    )
    after_track = next(
        (track for track in candidate.section.tracks if track.semantic_id == semantic_id), None
    )
    if before_track is None or after_track is None:
        return []
    before_ids = {binding.semantic_id for binding in before_track.bindings}
    return [binding for binding in after_track.bindings if binding.semantic_id not in before_ids]


def _json_payload(value: object) -> str:
    """Serialize canonical worker input deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = ["CanonicalSectionWorker"]

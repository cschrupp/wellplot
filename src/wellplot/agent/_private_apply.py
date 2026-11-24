"""Canonical private authoring apply, without publication."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ..authoring_executor import (
    AuthoringExecutionResult,
    _document_digest,
    _order_plan_operations,
    execute_authoring_plan,
)
from ..authoring_reconciler import AuthoringReconciliationPlan, reconcile_authoring
from ..authoring_service import AuthoringService
from ..model.authoring import AuthoringDocumentSpec
from ..model.intent import AuthoringDocumentIntent
from ..semantic_catalog import (
    EMPTY_SEMANTIC_CHANNEL_CATALOG,
    SemanticCatalogTrustError,
    SemanticPublicationContract,
    SemanticResolutionEvidence,
    _document_has_semantic_binding,
    _semantic_evidence_key,
    revalidate_deployed_catalog_release,
)
from .code_mode.enrichment import (
    EnrichedSemanticContext,
    ReportContext,
    _resolved_section_id,
    bind_semantic_publication_sources,
    intent_requires_channel_context,
    reconciliation_channels,
    validate_enriched_snapshot,
)
from .code_mode.obligations import (
    DocumentPostconditionError,
    ObligationState,
    RequestCompilationResult,
    RequestObligation,
    ScopeBindingResult,
    is_c2_request,
    verify_document_obligations,
    verify_document_postconditions,
    verify_document_preservation,
    verify_obligation_spans,
)
from .code_mode.planner import _attach_compiled_requirements


def _verify_c2_receipt(
    request: str,
    compilation: RequestCompilationResult,
    scope_binding: ScopeBindingResult | None,
    obligations: tuple[RequestObligation, ...],
    inspected: EnrichedSemanticContext,
    document: AuthoringDocumentSpec,
) -> None:
    """Verify original and attached custody without granting execution authority."""
    plan = inspected.plan
    derived = _attach_compiled_requirements(plan, compilation, request=request)
    if (
        derived.requirement_compilation != plan.requirement_compilation
        or derived.scope_binding != scope_binding
        or derived.scope_binding != plan.scope_binding
        or derived.obligations != obligations
        or derived.obligations != plan.obligations
        or derived.section_tasks != plan.section_tasks
        or len(inspected.sections) != 1
        or inspected.sections[0].task_index != 0
        or sum(section.id == inspected.sections[0].section_id for section in document.sections) != 1
    ):
        raise ValueError("C2 receipt differs from original scope or attachment custody.")
    if _resolved_section_id(derived.section_tasks[0], document) != inspected.sections[0].section_id:
        raise ValueError("C2 receipt does not resolve to the inspected section.")
    validate_enriched_snapshot(inspected, document)


@dataclass(frozen=True, slots=True)
class _PrivateStepAdmission:
    """Exact effects selected by the host, not a worker success assertion."""

    step_id: str
    outcome_id: str
    request_sha256: str
    before_sha256: str
    plan: AuthoringReconciliationPlan
    obligations: tuple[RequestObligation, ...] = ()
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _PrivateStepOccurrence:
    """One successful private execution; canonical operation IDs remain local."""

    occurrence_id: str
    admission: _PrivateStepAdmission
    after_sha256: str
    execution: AuthoringExecutionResult
    report_context: ReportContext | None
    inspection: EnrichedSemanticContext | None
    semantic_contract: SemanticPublicationContract | None
    semantic_evidence: tuple[SemanticResolutionEvidence, ...]
    verified_checks: tuple[str, ...]


class _OrderedPrivateApply:
    """Provider-free host qualification over the existing private apply boundary."""

    def __init__(
        self,
        *,
        request: str,
        document: AuthoringDocumentSpec,
        step_ids: tuple[str, ...],
        obligations: tuple[RequestObligation, ...],
        semantic_contract: SemanticPublicationContract | None = None,
        semantic_evidence: tuple[SemanticResolutionEvidence, ...] = (),
        source_base_dir: Path | None = None,
        source_allowed_root: Path | None = None,
    ) -> None:
        verify_obligation_spans(request, obligations)
        ids = {item.requirement_id for item in obligations}
        if len(ids) != len(obligations) or not all(ids):
            raise ValueError("Ordered request requires unique obligation identities.")
        if not step_ids or not all(step_ids) or len(set(step_ids)) != len(step_ids):
            raise ValueError("Ordered request requires unique host step identities.")
        self._request_sha256 = hashlib.sha256(request.encode("utf-8")).hexdigest()
        self._original = document.model_copy(deep=True)
        self._candidate = self._original
        self._step_ids = step_ids
        self._restrictions = tuple(
            item for item in obligations if item.state is ObligationState.FORBIDDEN
        )
        self._pending = {
            item.requirement_id: item for item in obligations if item not in self._restrictions
        }
        self._original_semantic_contract = semantic_contract
        self._original_semantic_evidence = semantic_evidence
        self._source_base_dir = source_base_dir
        self._source_allowed_root = source_allowed_root
        self._records: list[_PrivateStepOccurrence] = []
        self._closed = False
        self._verify_retained(self._candidate)

    @property
    def candidate(self) -> AuthoringDocumentSpec:
        """Return a defensive copy of the latest verified private state."""
        return self._candidate.model_copy(deep=True)

    @property
    def occurrences(self) -> tuple[_PrivateStepOccurrence, ...]:
        """Expose copies; only the host can append verified occurrences."""
        return tuple(deepcopy(self._records))

    def _verify_retained(self, candidate: AuthoringDocumentSpec) -> None:
        verify_document_postconditions(
            candidate,
            candidate,
            self._restrictions,
            (),
            semantic_contract=self._original_semantic_contract,
            semantic_evidence=self._original_semantic_evidence,
            source_base_dir=self._source_base_dir,
            source_allowed_root=self._source_allowed_root,
        )
        for record in self._records:
            verify_document_obligations(
                candidate,
                record.admission.obligations,
                grounded_operations=record.admission.plan.operations,
                before=candidate,
                report_context=record.report_context,
            )

    def apply(
        self,
        admission: _PrivateStepAdmission,
        intent: AuthoringDocumentIntent,
        *,
        inspected: EnrichedSemanticContext | None = None,
    ) -> _PrivateStepOccurrence:
        """Advance only after the admitted plan and all retained authority verify."""
        if self._closed:
            raise ValueError("Ordered private execution is closed.")
        try:
            return self._apply(admission, intent, inspected)
        except Exception:
            self._closed = True
            raise

    def _apply(
        self,
        admission: _PrivateStepAdmission,
        intent: AuthoringDocumentIntent,
        inspected: EnrichedSemanticContext | None,
    ) -> _PrivateStepOccurrence:
        index = len(self._records)
        if (
            index >= len(self._step_ids)
            or self._step_ids[index] != admission.step_id
            or not admission.outcome_id
            or not set(admission.depends_on) <= set(self._step_ids[:index])
            or len(set(admission.depends_on)) != len(admission.depends_on)
        ):
            raise ValueError("Invalid ordered admission or dependency.")
        if admission.request_sha256 != self._request_sha256:
            raise ValueError("Admission belongs to a different original request.")
        if admission.before_sha256 != _document_digest(self._candidate):
            raise ValueError("Host admission snapshot is stale.")
        facts = {item.requirement_id: item for item in admission.obligations}
        if len(facts) != len(admission.obligations) or any(
            self._pending.get(key) != value for key, value in facts.items()
        ):
            raise ValueError("Admission claims a missing, repeated or altered obligation.")
        result = _apply_private_authoring(
            document=self._candidate,
            intent=intent,
            obligations=admission.obligations,
            inspected=inspected,
            semantic_contract=None,
            source_base_dir=self._source_base_dir,
            source_allowed_root=self._source_allowed_root,
            _admitted_plan=admission.plan,
            _retained_verifier=self._verify_retained,
        )
        if result.candidate is None or result.plan is None or result.execution is None:
            raise ValueError(f"{result.failure_status}: {', '.join(result.errors)}")
        record = _PrivateStepOccurrence(
            occurrence_id=uuid4().hex,
            admission=admission,
            after_sha256=_document_digest(result.candidate),
            execution=result.execution,
            report_context=None if inspected is None else inspected.report,
            inspection=inspected,
            semantic_contract=self._original_semantic_contract,
            semantic_evidence=self._original_semantic_evidence,
            verified_checks=tuple(key for key, value in result.stages.items() if value == "PASS"),
        )
        self._verify_operation_chain(record)
        self._records.append(deepcopy(record))
        self._candidate = result.candidate
        for key in facts:
            del self._pending[key]
        return deepcopy(record)

    @staticmethod
    def _verify_operation_chain(record: _PrivateStepOccurrence) -> None:
        ordered, errors = _order_plan_operations(record.admission.plan)
        expected = [op.operation_id for group in ordered.values() for op in group]
        actual = record.execution.outcomes
        if (
            errors
            or not record.execution.success
            or [item.operation_id for item in actual] != expected
        ):
            raise ValueError("Incomplete canonical operation evidence.")
        digest = record.admission.before_sha256
        for outcome in actual:
            if (
                not outcome.postcondition_verified
                or outcome.before_document_sha256 != digest
                or not outcome.after_document_sha256
            ):
                raise ValueError("Broken operation snapshot chain.")
            digest = outcome.after_document_sha256
        if digest != record.after_sha256 or _document_digest(record.execution.document) != digest:
            raise ValueError("Operation evidence does not match the verified readback.")

    def finish(
        self,
        occurrences: tuple[_PrivateStepOccurrence, ...],
        candidate: AuthoringDocumentSpec,
    ) -> AuthoringDocumentSpec:
        """Recheck the retained chain and final private state without replaying writes."""
        if self._closed:
            raise ValueError("Ordered private execution is closed.")
        self._closed = True
        if (
            self._pending
            or len(self._records) != len(self._step_ids)
            or tuple(self._records) != occurrences
        ):
            raise ValueError("Missing, altered or reordered private occurrence evidence.")
        if len({item.occurrence_id for item in occurrences}) != len(occurrences):
            raise ValueError("Repeated execution occurrence identity.")
        previous = self._original
        for occurrence in occurrences:
            if occurrence.admission.before_sha256 != _document_digest(previous):
                raise ValueError("Broken private step snapshot chain.")
            self._verify_operation_chain(occurrence)
            if occurrence.inspection is not None:
                validate_enriched_snapshot(occurrence.inspection, previous)
            verify_document_preservation(
                previous, occurrence.execution.document, occurrence.admission.plan.operations
            )
            previous = occurrence.execution.document
        if _document_digest(candidate) != _document_digest(previous):
            raise ValueError("Final candidate differs from the cumulative verified readback.")
        self._verify_retained(candidate)
        return candidate.model_copy(deep=True)


@dataclass(frozen=True, slots=True)
class _PrivateApplyResult:
    """Return a verified candidate or rejection, never an intermediate document."""

    candidate: AuthoringDocumentSpec | None
    stages: dict[str, str]
    failure_status: str = ""
    errors: tuple[str, ...] = ()
    rolled_back: bool = False
    changed: bool = False
    plan: AuthoringReconciliationPlan | None = None
    execution: AuthoringExecutionResult | None = None


def _apply_private_authoring(
    *,
    document: AuthoringDocumentSpec,
    intent: AuthoringDocumentIntent,
    obligations: tuple[RequestObligation, ...],
    inspected: EnrichedSemanticContext | None,
    semantic_contract: SemanticPublicationContract | None,
    request: str | None = None,
    requirement_compilation: RequestCompilationResult | None = None,
    scope_binding: ScopeBindingResult | None = None,
    source_base_dir: Path | None = None,
    source_allowed_root: Path | None = None,
    _admitted_plan: AuthoringReconciliationPlan | None = None,
    _retained_verifier: Callable[[AuthoringDocumentSpec], None] | None = None,
) -> _PrivateApplyResult:
    """Reconcile, execute on a private service, and verify the candidate."""
    stages: dict[str, str] = {}

    def rejected(status: str, *errors: str, rolled_back: bool = False) -> _PrivateApplyResult:
        return _PrivateApplyResult(
            candidate=None,
            stages=stages,
            failure_status=status,
            errors=errors,
            rolled_back=rolled_back,
        )

    retained = inspected.plan.requirement_compilation if inspected is not None else None
    if any(
        compilation is not None and compilation.requirements.dependencies
        for compilation in (requirement_compilation, retained)
    ) or (request is not None and is_c2_request(request)):
        if request is not None and requirement_compilation is not None and inspected is not None:
            try:
                _verify_c2_receipt(
                    request,
                    requirement_compilation,
                    scope_binding,
                    obligations,
                    inspected,
                    document,
                )
            except ValueError:
                return rejected("reconciliation_blocked", "dependency_execution_not_authorized")
        return rejected("reconciliation_blocked", "dependency_execution_not_authorized")

    private_service = AuthoringService(document)
    semantic_catalog = EMPTY_SEMANTIC_CHANNEL_CATALOG
    if inspected is None:
        if intent_requires_channel_context(intent):
            return rejected("reconciliation_blocked", "Source inspection snapshot is missing.")
        available_channels = {}
    else:
        try:
            validate_enriched_snapshot(inspected, private_service.document)
            available_channels = reconciliation_channels(inspected, intent)
            if semantic_contract is not None and semantic_contract.expected_bindings:
                semantic_contract = bind_semantic_publication_sources(semantic_contract, inspected)
                trusted_release = semantic_contract.trusted_release
                if trusted_release is None:
                    raise SemanticCatalogTrustError("semantic_original_release_missing")
                revalidate_deployed_catalog_release(trusted_release)
                semantic_catalog = trusted_release.catalog
                semantic_contract = semantic_contract.model_copy(
                    update={"trusted_release": trusted_release}
                )
        except SemanticCatalogTrustError as error:
            return rejected(
                "reconciliation_blocked", f"{error.code}: trusted semantic catalog unavailable."
            )
        except ValueError as error:
            return rejected(
                "stale_snapshot_conflict", f"stale_or_invalid_inspection_snapshot: {error}"
            )
    try:
        plan = reconcile_authoring(
            intent,
            existing=private_service.document,
            available_channels=available_channels,
            semantic_catalog=semantic_catalog,
            semantic_publication_contract=semantic_contract,
        )
    except SemanticCatalogTrustError as error:
        return rejected(
            "reconciliation_blocked", f"{error.code}: trusted semantic catalog unavailable."
        )
    if not plan.ready:
        return rejected(
            "reconciliation_blocked", *(f"{issue.code}: {issue.message}" for issue in plan.issues)
        )
    if _admitted_plan is not None and plan != _admitted_plan:
        return rejected(
            "reconciliation_blocked", "Canonical plan differs from host-admitted effects."
        )
    if plan.semantic_publication_contract is not None:
        semantic_contract = plan.semantic_publication_contract
    stages["reconciliation"] = "PASS"

    retained = tuple(
        item
        for item in plan.semantic_resolutions
        if _document_has_semantic_binding(
            document,
            section_id=item.section_id,
            track_id=item.track_id,
            binding_id=item.binding_id,
            channel=item.physical_mnemonic or "",
        )
    )
    if retained and semantic_contract is not None:
        keys = {_semantic_evidence_key(item) for item in retained}
        retained_contract = semantic_contract.model_copy(
            update={
                "expected_bindings": tuple(
                    item
                    for item in semantic_contract.expected_bindings
                    if _semantic_evidence_key(item) in keys
                )
            }
        )

        def verify_retained(after: AuthoringDocumentSpec) -> None:
            if _retained_verifier is not None:
                _retained_verifier(after)
            verify_document_postconditions(
                after,
                after,
                (),
                (),
                semantic_contract=retained_contract,
                semantic_evidence=retained,
                source_base_dir=source_base_dir,
                source_allowed_root=source_allowed_root,
            )

        execution = execute_authoring_plan(
            private_service, plan, _retained_postcondition=verify_retained
        )
    elif _retained_verifier is not None:
        execution = execute_authoring_plan(
            private_service, plan, _retained_postcondition=_retained_verifier
        )
    else:
        execution = execute_authoring_plan(private_service, plan)
    if not execution.success:
        return rejected(
            "execution_failed", *(str(error) for error in execution.errors), rolled_back=True
        )
    stages["private_execution"] = "PASS"

    validation = private_service.validate()
    if not validation.valid:
        return rejected("validation_failed", *validation.errors, rolled_back=True)
    stages["canonical_validation"] = "PASS"

    candidate = private_service.document
    try:
        verify_document_postconditions(
            document,
            candidate,
            obligations,
            plan.operations,
            semantic_contract=semantic_contract,
            semantic_evidence=plan.semantic_resolutions,
            **({"report_context": inspected.report} if inspected is not None else {}),
            source_base_dir=source_base_dir,
            source_allowed_root=source_allowed_root,
        )
    except DocumentPostconditionError as error:
        if error.check == "semantic":
            stages["semantic_postcondition"] = "FAIL"
            return rejected("semantic_postcondition_failed", str(error), rolled_back=True)
        if error.check == "obligations":
            stages["post_lowering_obligation"] = "FAIL"
        else:
            stages["post_lowering_obligation"] = "PASS"
            stages["preservation"] = "FAIL"
        return rejected("post_lowering_obligation_failed", str(error), rolled_back=True)
    stages["semantic_postcondition"] = "PASS"
    stages["post_lowering_obligation"] = "PASS"
    stages["preservation"] = "PASS"
    return _PrivateApplyResult(
        candidate=candidate,
        stages=stages,
        changed=document.model_dump(mode="json") != candidate.model_dump(mode="json"),
        plan=plan if _admitted_plan is not None else None,
        execution=execution if _admitted_plan is not None else None,
    )

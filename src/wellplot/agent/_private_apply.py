"""Canonical private authoring apply, without publication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..authoring_executor import execute_authoring_plan
from ..authoring_reconciler import reconcile_authoring
from ..authoring_service import AuthoringService
from ..model.authoring import AuthoringDocumentSpec
from ..model.intent import AuthoringDocumentIntent
from ..semantic_catalog import (
    EMPTY_SEMANTIC_CHANNEL_CATALOG,
    SemanticCatalogTrustError,
    SemanticPublicationContract,
    load_deployed_catalog_release,
)
from .code_mode.enrichment import (
    EnrichedSemanticContext,
    bind_semantic_publication_sources,
    intent_requires_channel_context,
    reconciliation_channels,
    validate_enriched_snapshot,
)
from .code_mode.obligations import (
    DocumentPostconditionError,
    RequestObligation,
    verify_document_postconditions,
)


@dataclass(frozen=True, slots=True)
class _PrivateApplyResult:
    """Return a verified candidate or rejection, never an intermediate document."""

    candidate: AuthoringDocumentSpec | None
    stages: dict[str, str]
    failure_status: str = ""
    errors: tuple[str, ...] = ()
    rolled_back: bool = False
    changed: bool = False


def _apply_private_authoring(
    *,
    document: AuthoringDocumentSpec,
    intent: AuthoringDocumentIntent,
    obligations: tuple[RequestObligation, ...],
    inspected: EnrichedSemanticContext | None,
    semantic_contract: SemanticPublicationContract | None,
    source_base_dir: Path | None = None,
    source_allowed_root: Path | None = None,
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
                trusted_release = (
                    semantic_contract.trusted_release or load_deployed_catalog_release()
                )
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
    if plan.semantic_publication_contract is not None:
        semantic_contract = plan.semantic_publication_contract
    stages["reconciliation"] = "PASS"

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
    )

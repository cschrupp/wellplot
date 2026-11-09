"""Provider-free transaction tests for the canonical notebook adapter."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent.code_mode.obligations import (
    DocumentPostconditionError,
    RequestObligation,
    verify_document_postconditions,
)
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.direct_notebook import (
    DirectNotebookSession,
    _apply_result,
    _load_document_context,
)
from wellplot.agent.session import AgentMetrics, AgentSessionResult, AgentWorkerEvidence
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_reconciler import (
    AuthoringReconciliationIssue,
    AuthoringReconciliationPlan,
)
from wellplot.authoring_service import AuthoringService, CreateTrackRequest
from wellplot.errors import AuthoringPublicationRecoveryError
from wellplot.mcp import service as mcp_service
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec
from wellplot.semantic_catalog import ExpectedSemanticBinding, SemanticPublicationContract


def _successful_result(
    intent: AuthoringDocumentIntent | None = None,
    *,
    obligations: tuple[RequestObligation, ...] = (),
    semantic_publication_contract: SemanticPublicationContract | None = None,
) -> AgentSessionResult:
    """Build a minimal successful worker result for one supplied intent."""
    return AgentSessionResult(
        mode="revise",
        success=True,
        intent=intent or AuthoringDocumentIntent(title="Updated transaction title"),
        workers=(AgentWorkerEvidence(kind="report", plan_order=0, success=True),),
        obligations=obligations,
        semantic_publication_contract=semantic_publication_contract,
        metrics=AgentMetrics(
            worker_count=1,
            successful_workers=1,
            failed_workers=0,
            total_program_chars=0,
            total_ast_nodes=0,
            total_statements=0,
            total_calls=0,
            total_repairs=0,
            total_loop_iterations=0,
            total_created_objects=0,
            max_nesting_depth=0,
        ),
    )


def _title_obligation(value: str) -> RequestObligation:
    request = f"Set the report title to {value}."
    start = request.index(value)
    end = start + len(value)
    return RequestObligation(
        kind="explicit_field",
        owner_kind="report",
        owner_ref="report",
        field="title",
        value=value,
        request_sha256=hashlib.sha256(request.encode()).hexdigest(),
        start_byte=start,
        end_byte=end,
        span_sha256=hashlib.sha256(request[start:end].encode()).hexdigest(),
    )


def test_notebook_apply_rejects_unsatisfied_obligation_before_persist() -> None:
    """A schema-valid private candidate cannot publish an unsatisfied request."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-postcondition-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        result = _successful_result(
            AuthoringDocumentIntent(title="Actual title"),
            obligations=(_title_obligation("Required title"),),
        )

        with patch(
            "wellplot.agent.direct_notebook.mcp_service.persist_authoring_document"
        ) as persist:
            applied = _apply_result(context=context, result=result, root=REPO_ROOT)

        success, changed, rolled_back, errors, status, stages = applied
        assert success is False
        assert changed is False
        assert rolled_back is True
        assert status == "post_lowering_obligation_failed"
        assert stages["canonical_validation"] == "PASS"
        assert stages["post_lowering_obligation"] == "FAIL"
        assert "report title" in errors[0]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_notebook_semantic_stage_not_reached_before_verifier() -> None:
    """A reconciliation activation guard stops before execution and persistence."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-catalog-block-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        blocked_plan = AuthoringReconciliationPlan(
            ready=False,
            issues=[
                AuthoringReconciliationIssue(
                    path="semantic_catalog",
                    code="semantic_catalog_activation_disabled",
                    message="Catalog verification is not enabled at publication.",
                )
            ],
        )

        with (
            patch("wellplot.agent.direct_notebook.reconcile_authoring", return_value=blocked_plan),
            patch("wellplot.agent.direct_notebook.execute_authoring_plan") as execute,
            patch("wellplot.agent.direct_notebook.verify_document_postconditions") as verify,
            patch(
                "wellplot.agent.direct_notebook.mcp_service.persist_authoring_document"
            ) as persist,
        ):
            applied = _apply_result(
                context=context,
                result=_successful_result(AuthoringDocumentIntent(title="Updated title")),
                root=REPO_ROOT,
            )

        success, changed, rolled_back, errors, status, stages = applied
        assert success is False
        assert changed is False
        assert rolled_back is False
        assert status == "reconciliation_blocked"
        assert "semantic_catalog_activation_disabled" in errors[0]
        assert stages["private_execution"] == "NOT_REACHED"
        assert stages["semantic_postcondition"] == "NOT_REACHED"
        execute.assert_not_called()
        verify.assert_not_called()
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_notebook_semantic_postcondition_fails_without_persistence() -> None:
    """A semantic host expectation fails closed at shared postconditions."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-semantic-pin-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        expected = ExpectedSemanticBinding(
            request_kind="SEMANTIC_FAMILY",
            requirement_id="requirement-1",
            request_sha256="a" * 64,
            scope_key="existing:main",
            track_scope="curves",
            binding_slot="curves.binding.1",
            requested_term="Gamma Ray",
            source_candidate_id="candidate-1",
            source_handle="source-1",
            inspection_snapshot_id="snapshot-1",
            source_revision="revision-1",
            task_index=0,
            section_id="main",
            track_id="track-1",
            binding_id="binding-1",
        )
        result = _successful_result(
            AuthoringDocumentIntent(title="Updated semantic title"),
            semantic_publication_contract=SemanticPublicationContract(
                expected_bindings=(expected,),
            ),
        )

        verifier_events: list[str] = []
        real_verify = verify_document_postconditions

        def record_semantic_rejection(*args: object, **kwargs: object) -> None:
            verifier_events.append("verifier_enter")
            try:
                real_verify(*args, **kwargs)
            except DocumentPostconditionError as error:
                if error.check == "semantic":
                    verifier_events.append("verifier_rejected_semantic")
                raise

        with (
            patch(
                "wellplot.agent.direct_notebook.verify_document_postconditions",
                side_effect=record_semantic_rejection,
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.persist_authoring_document"
            ) as persist,
        ):
            applied = _apply_result(context=context, result=result, root=REPO_ROOT)

        success, changed, rolled_back, errors, status, stages = applied
        assert success is False
        assert changed is False
        assert rolled_back is True
        assert status == "semantic_postcondition_failed"
        assert stages["semantic_postcondition"] == "FAIL"
        assert "semantic_evidence_set_mismatch" in errors[0]
        assert verifier_events == ["verifier_enter", "verifier_rejected_semantic"]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_notebook_apply_rejects_unapproved_candidate_change_before_persist() -> None:
    """The adapter rejects valid-but-out-of-envelope changes before publication."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-preservation-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        result = _successful_result(
            AuthoringDocumentIntent(title="Verified title"),
            obligations=(_title_obligation("Verified title"),),
        )
        real_execute = execute_authoring_plan

        def execute_with_unrequested_section_change(
            service: AuthoringService, plan: object
        ) -> object:
            execution = real_execute(service, plan)
            candidate = service.document.model_dump(mode="python")
            candidate["sections"][0]["title"] = "Unauthorized section title"
            service.replace_document(AuthoringDocumentSpec.model_validate(candidate))
            assert service.validate().valid
            return execution

        with (
            patch(
                "wellplot.agent.direct_notebook.execute_authoring_plan",
                side_effect=execute_with_unrequested_section_change,
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.persist_authoring_document"
            ) as persist,
        ):
            success, changed, rolled_back, errors, status, stages = _apply_result(
                context=context,
                result=result,
                root=REPO_ROOT,
            )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert status == "post_lowering_obligation_failed"
        assert stages["post_lowering_obligation"] == "PASS"
        assert stages["preservation"] == "FAIL"
        assert "outside the authorized reconciliation envelope" in errors[0]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_notebook_semantic_postcondition_passes_before_persistence() -> None:
    """Verified candidates continue to the existing canonical persistence path."""
    with tempfile.TemporaryDirectory(
        dir=REPO_ROOT, prefix="notebook-postcondition-pass-"
    ) as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        result = _successful_result(
            AuthoringDocumentIntent(title="Verified title"),
            obligations=(_title_obligation("Verified title"),),
        )
        real_persist = mcp_service.persist_authoring_document
        events: list[str] = []
        real_verify = verify_document_postconditions

        def record_verify(*args: object, **kwargs: object) -> None:
            events.append("verifier_enter")
            real_verify(*args, **kwargs)
            events.append("verifier_pass")

        def record_persist(*args: object, **kwargs: object) -> object:
            events.append("persistence_enter")
            result = real_persist(*args, **kwargs)
            events.append("persistence_pass")
            return result

        with (
            patch(
                "wellplot.agent.direct_notebook.verify_document_postconditions",
                side_effect=record_verify,
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.persist_authoring_document",
                side_effect=record_persist,
            ) as persist,
        ):
            success, changed, rolled_back, errors, status, stages = _apply_result(
                context=context,
                result=result,
                root=REPO_ROOT,
            )

        assert success is True
        assert changed is True
        assert rolled_back is False
        assert errors == []
        assert status == "persisted"
        assert stages["post_lowering_obligation"] == "PASS"
        assert stages["preservation"] == "PASS"
        assert stages["semantic_postcondition"] == "PASS"
        assert events == [
            "verifier_enter",
            "verifier_pass",
            "persistence_enter",
            "persistence_pass",
        ]
        persist.assert_called_once()
        assert fixture_paths.single_logfile.read_bytes() != original_bytes


def test_notebook_apply_rejects_yaml_changed_after_snapshot() -> None:
    """A concurrent YAML edit is preserved and reported instead of overwritten."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-transaction-") as temp_dir:
        root = Path(temp_dir)
        fixture_paths = create_mcp_fixture_paths(root / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        concurrent_bytes = b"# external change\n" + fixture_paths.single_logfile.read_bytes()
        fixture_paths.single_logfile.write_bytes(concurrent_bytes)

        success, changed, rolled_back, errors, status, stages = _apply_result(
            context=context,
            result=_successful_result(),
            root=REPO_ROOT,
        )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert status == "stale_snapshot_conflict"
        assert stages["persistence"] == "FAIL"
        assert "changed after" in errors[0]
        assert fixture_paths.single_logfile.read_bytes() == concurrent_bytes


def test_notebook_context_does_not_eagerly_parse_declared_sources() -> None:
    """Notebook setup defers parsing until an authoring task needs channels."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-lazy-inspection-") as temp_dir:
        root = Path(temp_dir)
        fixture_paths = create_mcp_fixture_paths(root / "fixture")
        with patch.object(
            LogfileSourceLoader,
            "load",
            side_effect=AssertionError("source parser invoked during notebook setup"),
        ):
            context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)

    assert context.source_candidates
    assert all(
        candidate.inspection_state == "not_inspected" for candidate in context.source_candidates
    )
    assert all(candidate.expected_revision_token for candidate in context.source_candidates)


def test_notebook_apply_rejects_source_changed_after_snapshot() -> None:
    """A changed inspected LAS source blocks publication of its stale intent."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-transaction-") as temp_dir:
        root = Path(temp_dir)
        fixture_paths = create_mcp_fixture_paths(root / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_logfile_bytes = fixture_paths.single_logfile.read_bytes()
        with fixture_paths.las_path.open("a", encoding="utf-8") as source_file:
            source_file.write("\n")

        success, changed, rolled_back, errors, status, stages = _apply_result(
            context=context,
            result=_successful_result(),
            root=REPO_ROOT,
        )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert status == "stale_snapshot_conflict"
        assert stages["persistence"] == "FAIL"
        assert "dependency changed" in errors[0]
        assert fixture_paths.single_logfile.read_bytes() == original_logfile_bytes


def test_notebook_apply_rejects_template_changed_after_snapshot() -> None:
    """A template dependency changing after load blocks stale publication."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-transaction-") as temp_dir:
        root = Path(temp_dir)
        fixture_paths = create_mcp_fixture_paths(root / "fixture")
        template_path = fixture_paths.fixture_dir / "base.template.yaml"
        shutil.copy2(REPO_ROOT / "templates" / "wireline_base.template.yaml", template_path)
        logfile_mapping = yaml.safe_load(fixture_paths.single_logfile.read_text(encoding="utf-8"))
        logfile_mapping["template"]["path"] = "./base.template.yaml"
        fixture_paths.single_logfile.write_text(
            yaml.safe_dump(logfile_mapping, sort_keys=False),
            encoding="utf-8",
        )
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_logfile_bytes = fixture_paths.single_logfile.read_bytes()
        with template_path.open("a", encoding="utf-8") as template_file:
            template_file.write("\n# concurrent template edit\n")

        success, changed, rolled_back, errors, status, stages = _apply_result(
            context=context,
            result=_successful_result(),
            root=REPO_ROOT,
        )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert status == "stale_snapshot_conflict"
        assert stages["persistence"] == "FAIL"
        assert "dependency changed" in errors[0]
        assert fixture_paths.single_logfile.read_bytes() == original_logfile_bytes


def test_notebook_apply_does_not_publish_partial_private_execution() -> None:
    """A later CRUD failure discards earlier mutations to the private candidate."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-transaction-") as temp_dir:
        root = Path(temp_dir)
        fixture_paths = create_mcp_fixture_paths(root / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        original_logfile_bytes = fixture_paths.single_logfile.read_bytes()
        intent = AuthoringDocumentIntent(
            sections=[
                {
                    "section_id": "main",
                    "tracks": [
                        {
                            "track_id": "new-first",
                            "title": "First",
                            "kind": "normal",
                            "width_mm": 20,
                        },
                        {
                            "track_id": "new-second",
                            "title": "Second",
                            "kind": "normal",
                            "width_mm": 20,
                        },
                    ],
                }
            ]
        )
        original_create = AuthoringService.create
        create_count = 0

        def fail_second_track_create(
            authoring_service: AuthoringService,
            request: object,
        ) -> object:
            nonlocal create_count
            if isinstance(request, CreateTrackRequest):
                create_count += 1
                if create_count == 2:
                    raise ValueError("injected second-track failure")
            return original_create(authoring_service, request)

        with patch.object(AuthoringService, "create", fail_second_track_create):
            success, changed, rolled_back, errors, status, _stages = _apply_result(
                context=context,
                result=_successful_result(intent),
                root=REPO_ROOT,
            )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert status == "execution_failed"
        assert "injected second-track failure" in errors[0]
        assert create_count == 2
        assert fixture_paths.single_logfile.read_bytes() == original_logfile_bytes


def test_notebook_reports_preview_failure_after_persistence() -> None:
    """A preview failure is visible without claiming the persisted edit rolled back."""
    adapter = DirectNotebookSession(
        session=None,  # type: ignore[arg-type]
        provider="test",
        model="test-model",
        credential_source=None,
        server_root=REPO_ROOT,
    )
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-render-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        with (
            patch(
                "wellplot.agent.direct_notebook.mcp_service.validate_logfile",
                return_value=SimpleNamespace(valid=True),
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.summarize_logfile_draft",
                return_value={},
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.inspect_logfile",
                return_value=SimpleNamespace(section_ids=["main"]),
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.summarize_logfile_changes",
                return_value={},
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.preview_logfile_png",
                return_value=b"report-preview",
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.preview_section_png",
                side_effect=RuntimeError("renderer details are not exposed"),
            ),
        ):
            result = adapter._project_result(
                request="update the report",
                mode="revise",
                logfile_path=fixture_paths.single_logfile,
                baseline_text="before",
                result=_successful_result(),
                success=True,
                changed=True,
                rolled_back=False,
                errors=[],
                apply_status="persisted",
                example_id=None,
                source_logfile_path=None,
                host_stage_evidence={"persistence": "PASS"},
            )

    assert result.report_facts["success"] is False
    assert result.report_facts["changed"] is True
    assert result.report_facts["rolled_back"] is False
    assert result.report_facts["apply_status"] == "persisted_render_failed"
    evidence = result.report_facts["host_stage_evidence"]
    assert evidence["persistence"] == "PASS"
    assert evidence["reload"] == "PASS"
    assert evidence["render"] == "FAIL"
    assert result.report_preview_png == b"report-preview"
    assert result.section_preview_png == b""


def test_notebook_marks_render_pass_only_after_nonempty_previews() -> None:
    """A successful render stage requires observed preview output."""
    adapter = DirectNotebookSession(
        session=None,  # type: ignore[arg-type]
        provider="test",
        model="test-model",
        credential_source=None,
        server_root=REPO_ROOT,
    )
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-render-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        with (
            patch(
                "wellplot.agent.direct_notebook.mcp_service.validate_logfile",
                return_value=SimpleNamespace(valid=True),
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.summarize_logfile_draft",
                return_value={},
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.inspect_logfile",
                return_value=SimpleNamespace(section_ids=["main"]),
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.summarize_logfile_changes",
                return_value={},
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.preview_logfile_png",
                return_value=b"report-preview",
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.preview_section_png",
                return_value=b"section-preview",
            ),
        ):
            result = adapter._project_result(
                request="update the report",
                mode="revise",
                logfile_path=fixture_paths.single_logfile,
                baseline_text="before",
                result=_successful_result(),
                success=True,
                changed=True,
                rolled_back=False,
                errors=[],
                apply_status="persisted",
                example_id=None,
                source_logfile_path=None,
                host_stage_evidence={"persistence": "PASS"},
            )

    assert result.report_facts["success"] is True
    assert result.report_facts["host_stage_evidence"]["render"] == "PASS"
    assert result.report_preview_png == b"report-preview"
    assert result.section_preview_png == b"section-preview"


@pytest.mark.parametrize(
    ("failing_stage", "expected_render_status"),
    [
        ("validation", "FAIL"),
        ("draft_summary", "PASS"),
        ("inspection", "FAIL"),
        ("change_summary", "PASS"),
        ("report_preview", "FAIL"),
        ("draft_text", "PASS"),
    ],
)
def test_notebook_projection_failure_preserves_published_state(
    failing_stage: str,
    expected_render_status: str,
) -> None:
    """Post-publication projection errors do not hide or reverse a persisted edit."""
    adapter = DirectNotebookSession(
        session=None,  # type: ignore[arg-type]
        provider="test",
        model="test-model",
        credential_source=None,
        server_root=REPO_ROOT,
    )
    target_by_stage = {
        "validation": "wellplot.agent.direct_notebook.mcp_service.validate_logfile",
        "draft_summary": ("wellplot.agent.direct_notebook.mcp_service.summarize_logfile_draft"),
        "inspection": "wellplot.agent.direct_notebook.mcp_service.inspect_logfile",
        "change_summary": ("wellplot.agent.direct_notebook.mcp_service.summarize_logfile_changes"),
        "report_preview": "wellplot.agent.direct_notebook.mcp_service.preview_logfile_png",
        "draft_text": "pathlib.Path.read_text",
    }
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-projection-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        failing_projection = patch(
            target_by_stage[failing_stage],
            side_effect=RuntimeError("projection detail must not escape"),
        )
        with (
            patch(
                "wellplot.agent.direct_notebook.mcp_service.validate_logfile",
                return_value=SimpleNamespace(valid=True),
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.summarize_logfile_draft",
                return_value={},
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.inspect_logfile",
                return_value=SimpleNamespace(section_ids=["main"]),
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.summarize_logfile_changes",
                return_value={},
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.preview_logfile_png",
                return_value=b"report-preview",
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.preview_section_png",
                return_value=b"section-preview",
            ),
            failing_projection,
        ):
            result = adapter._project_result(
                request="update the report",
                mode="revise",
                logfile_path=fixture_paths.single_logfile,
                baseline_text="before",
                result=_successful_result(),
                success=True,
                changed=True,
                rolled_back=False,
                errors=[],
                apply_status="persisted",
                example_id=None,
                source_logfile_path=None,
                host_stage_evidence={"persistence": "PASS"},
            )

    evidence = result.report_facts["host_stage_evidence"]
    assert result.report_facts["success"] is False
    assert result.report_facts["changed"] is True
    assert result.report_facts["rolled_back"] is False
    assert result.report_facts["apply_status"] in {
        "persisted_projection_failed",
        "persisted_render_failed",
    }
    assert evidence["persistence"] == "PASS"
    assert evidence["reload"] == "PASS"
    assert evidence["result_projection"] == "FAIL"
    assert evidence["render"] == expected_render_status
    assert evidence[failing_stage] == "FAIL"
    assert "persisted" in result.final_text.lower()
    assert "no rollback was performed" in result.final_text.lower()
    assert "retrying" in result.user_report_text.lower()


def test_notebook_classifies_publication_recovery_failure() -> None:
    """A failed restore is not reported as a successful rollback."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="notebook-transaction-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _load_document_context(fixture_paths.single_logfile, root=REPO_ROOT)
        error = AuthoringPublicationRecoveryError("TemplateValidationError", "OSError")

        with patch(
            "wellplot.agent.direct_notebook.mcp_service.persist_authoring_document",
            side_effect=error,
        ):
            success, changed, rolled_back, errors, status, stages = _apply_result(
                context=context,
                result=_successful_result(),
                root=REPO_ROOT,
            )

        assert success is False
        assert changed is True
        assert rolled_back is False
        assert status == "publication_recovery_failed"
        assert stages["persistence"] == "RECOVERY_FAIL"
        assert "recovery could not restore" in errors[0]

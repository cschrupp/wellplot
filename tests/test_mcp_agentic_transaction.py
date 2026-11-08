"""Provider-free stale-snapshot tests for MCP graph authoring."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent.code_mode.obligations import RequestObligation
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.session import AgentMetrics, AgentSessionResult, AgentWorkerEvidence
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_service import AuthoringService
from wellplot.errors import AuthoringPublicationRecoveryError
from wellplot.mcp import service as mcp_service
from wellplot.mcp.agentic import (
    GraphAuthoringMcpOperations,
    _apply_failure_owner,
    _apply_session_result,
    _request_context,
)
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec
from wellplot.semantic_catalog import ExpectedSemanticBinding, SemanticPublicationContract


def test_apply_failure_owner_keeps_deterministic_boundaries_distinct() -> None:
    """Trace ownership distinguishes compile, reconcile, executor, and persistence."""
    assert _apply_failure_owner(["reconciliation_blocked"], object()) == "reconciliation"
    assert _apply_failure_owner(["execution_failed"], object()) == "executor"
    assert _apply_failure_owner(["validation_failed"], object()) == "executor"
    assert _apply_failure_owner(["post_lowering_obligation_failed"], object()) == "executor"
    assert _apply_failure_owner(["stale_snapshot_conflict"], object()) == "persistence"
    assert _apply_failure_owner(["publication_recovery_failed"], object()) == "persistence"
    assert (
        _apply_failure_owner(
            ["compile_failed"],
            SimpleNamespace(diagnostics=(SimpleNamespace(failure_owner="inspection"),)),
        )
        == "inspection"
    )


def _successful_result(
    intent: AuthoringDocumentIntent | None = None,
    *,
    obligations: tuple[RequestObligation, ...] = (),
    semantic_publication_contract: SemanticPublicationContract | None = None,
) -> AgentSessionResult:
    """Create one provider-free result that changes the report title."""
    return AgentSessionResult(
        mode="revise",
        success=True,
        intent=intent or AuthoringDocumentIntent(title="MCP transaction title"),
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


def test_mcp_apply_rejects_concurrent_yaml_edit() -> None:
    """MCP graph authoring preserves edits made after its source snapshot."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-transaction-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        concurrent_bytes = b"# concurrent MCP edit\n" + fixture_paths.single_logfile.read_bytes()
        fixture_paths.single_logfile.write_bytes(concurrent_bytes)

        success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
            context=context,
            session_result=_successful_result(),
            root=REPO_ROOT,
        )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert statuses == ["stale_snapshot_conflict"]
        assert errors[0].startswith("stale_snapshot_conflict:")
        assert fixture_paths.single_logfile.read_bytes() == concurrent_bytes


def test_mcp_request_context_does_not_eagerly_parse_declared_sources() -> None:
    """MCP records source revisions and defers metadata parsing to enrichment."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-lazy-inspection-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        with patch.object(
            LogfileSourceLoader,
            "load",
            side_effect=AssertionError("source parser invoked during request setup"),
        ):
            context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)

    assert context.source_candidates
    assert all(
        candidate.inspection_state == "not_inspected" for candidate in context.source_candidates
    )
    assert all(candidate.expected_revision_token for candidate in context.source_candidates)


def test_mcp_missing_semantic_evidence_does_not_publish() -> None:
    """MCP shares fail-closed semantic verification before YAML persistence."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-semantic-pin-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
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

        with patch("wellplot.mcp.agentic.service.persist_authoring_document") as persist:
            outcome = _apply_session_result(
                context=context,
                session_result=_successful_result(
                    AuthoringDocumentIntent(title="MCP semantic title"),
                    semantic_publication_contract=SemanticPublicationContract(
                        expected_bindings=(expected,),
                    ),
                ),
                root=REPO_ROOT,
            )

        success, changed, rolled_back, errors, statuses, _section_ids = outcome
        assert success is False
        assert changed is False
        assert rolled_back is True
        assert statuses == ["semantic_postcondition_failed"]
        assert "semantic_evidence_set_mismatch" in errors[0]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_mcp_apply_rejects_changed_inspected_source() -> None:
    """MCP graph authoring does not publish against a stale LAS inventory."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-transaction-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        original_logfile_bytes = fixture_paths.single_logfile.read_bytes()
        with fixture_paths.las_path.open("a", encoding="utf-8") as source_file:
            source_file.write("\n")

        success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
            context=context,
            session_result=_successful_result(),
            root=REPO_ROOT,
        )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert statuses == ["stale_snapshot_conflict"]
        assert "dependency changed" in errors[0]
        assert fixture_paths.single_logfile.read_bytes() == original_logfile_bytes


def test_mcp_apply_rejects_changed_template_dependency() -> None:
    """MCP graph authoring binds template inheritance to the loaded snapshot."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-transaction-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        template_path = fixture_paths.fixture_dir / "base.template.yaml"
        shutil.copy2(REPO_ROOT / "templates" / "wireline_base.template.yaml", template_path)
        mapping = yaml.safe_load(fixture_paths.single_logfile.read_text(encoding="utf-8"))
        mapping["template"]["path"] = "./base.template.yaml"
        fixture_paths.single_logfile.write_text(
            yaml.safe_dump(mapping, sort_keys=False),
            encoding="utf-8",
        )
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        original_logfile_bytes = fixture_paths.single_logfile.read_bytes()
        with template_path.open("a", encoding="utf-8") as template_file:
            template_file.write("\n# concurrent template edit\n")

        success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
            context=context,
            session_result=_successful_result(),
            root=REPO_ROOT,
        )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert statuses == ["stale_snapshot_conflict"]
        assert "dependency changed" in errors[0]
        assert fixture_paths.single_logfile.read_bytes() == original_logfile_bytes


def test_mcp_apply_classifies_publication_recovery_failure() -> None:
    """The MCP result distinguishes failed recovery from a completed rollback."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-transaction-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        recovery_error = AuthoringPublicationRecoveryError("TemplateValidationError", "OSError")

        with patch(
            "wellplot.mcp.agentic.service.persist_authoring_document",
            side_effect=recovery_error,
        ):
            success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
                context=context,
                session_result=_successful_result(),
                root=REPO_ROOT,
            )

        assert success is False
        assert changed is True
        assert rolled_back is False
        assert statuses == ["publication_recovery_failed"]
        assert errors[0].startswith("publication_recovery_failed:")


def test_mcp_apply_rejects_unsatisfied_obligation_before_persist() -> None:
    """A schema-valid private candidate cannot publish an unsatisfied request."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-postcondition-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        result = _successful_result(
            AuthoringDocumentIntent(title="Actual title"),
            obligations=(_title_obligation("Required title"),),
        )

        with patch("wellplot.mcp.agentic.service.persist_authoring_document") as persist:
            success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
                context=context,
                session_result=result,
                root=REPO_ROOT,
            )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert statuses == ["post_lowering_obligation_failed"]
        assert "report title" in errors[0]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_mcp_apply_rejects_result_missing_obligations_contract() -> None:
    """A success-shaped result without typed obligations cannot reach persistence."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-missing-obligations-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        malformed_result = SimpleNamespace(
            success=True,
            intent=AuthoringDocumentIntent(title="Unverified title"),
        )

        with patch("wellplot.mcp.agentic.service.persist_authoring_document") as persist:
            success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
                context=context,
                session_result=malformed_result,
                root=REPO_ROOT,
            )

        assert success is False
        assert changed is False
        assert rolled_back is False
        assert statuses == ["compile_failed"]
        assert errors == ["session_result_contract_invalid: expected AgentSessionResult"]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_mcp_revise_rejects_unsatisfied_obligation_before_persist() -> None:
    """The public MCP operation rejects an unmet postcondition before publication."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-public-postcondition-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        original_bytes = fixture_paths.single_logfile.read_bytes()
        result = _successful_result(
            AuthoringDocumentIntent(title="Actual title"),
            obligations=(_title_obligation("Required title"),),
        )

        class StubSession:
            async def revise(self, **_kwargs: object) -> AgentSessionResult:
                return result

        operations = GraphAuthoringMcpOperations.create(session=StubSession(), root=REPO_ROOT)
        with patch("wellplot.mcp.agentic.service.persist_authoring_document") as persist:
            tool_result = asyncio.run(
                operations.revise(
                    logfile_path=str(fixture_paths.single_logfile),
                    request="set the title",
                )
            )

        assert tool_result.success is False
        assert tool_result.changed is False
        assert tool_result.rolled_back is True
        assert tool_result.errors
        assert "report title" in tool_result.errors[0]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_mcp_apply_rejects_unapproved_candidate_change_before_persist() -> None:
    """The MCP path rejects valid-but-out-of-envelope changes before publication."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-preservation-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        result = _successful_result(
            AuthoringDocumentIntent(title="MCP transaction title"),
            obligations=(_title_obligation("MCP transaction title"),),
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
                "wellplot.mcp.agentic.execute_authoring_plan",
                side_effect=execute_with_unrequested_section_change,
            ),
            patch("wellplot.mcp.agentic.service.persist_authoring_document") as persist,
        ):
            success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
                context=context,
                session_result=result,
                root=REPO_ROOT,
            )

        assert success is False
        assert changed is False
        assert rolled_back is True
        assert statuses == ["post_lowering_obligation_failed"]
        assert "outside the authorized reconciliation envelope" in errors[0]
        persist.assert_not_called()
        assert fixture_paths.single_logfile.read_bytes() == original_bytes


def test_mcp_apply_persists_candidate_after_shared_postconditions_pass() -> None:
    """Verified MCP candidates continue to canonical persistence."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-postcondition-pass-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture_paths.single_logfile), root=REPO_ROOT)
        original_bytes = fixture_paths.single_logfile.read_bytes()
        result = _successful_result(
            AuthoringDocumentIntent(title="MCP transaction title"),
            obligations=(_title_obligation("MCP transaction title"),),
        )
        real_persist = mcp_service.persist_authoring_document

        with patch(
            "wellplot.mcp.agentic.service.persist_authoring_document",
            wraps=real_persist,
        ) as persist:
            success, changed, rolled_back, errors, statuses, _section_ids = _apply_session_result(
                context=context,
                session_result=result,
                root=REPO_ROOT,
            )

        assert success is True
        assert changed is True
        assert rolled_back is False
        assert errors == []
        assert statuses == ["persisted"]
        persist.assert_called_once()
        assert fixture_paths.single_logfile.read_bytes() != original_bytes

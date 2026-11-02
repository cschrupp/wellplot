"""Provider-free stale-snapshot tests for MCP graph authoring."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent.session import AgentMetrics, AgentSessionResult, AgentWorkerEvidence
from wellplot.errors import AuthoringPublicationRecoveryError
from wellplot.mcp.agentic import _apply_session_result, _request_context
from wellplot.model import AuthoringDocumentIntent


def _successful_result() -> AgentSessionResult:
    """Create one provider-free result that changes the report title."""
    return AgentSessionResult(
        mode="revise",
        success=True,
        intent=AuthoringDocumentIntent(title="MCP transaction title"),
        workers=(AgentWorkerEvidence(kind="report", plan_order=0, success=True),),
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

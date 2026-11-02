"""Provider-free transaction tests for the canonical notebook adapter."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent.direct_notebook import _apply_result, _load_document_context
from wellplot.agent.session import AgentMetrics, AgentSessionResult, AgentWorkerEvidence
from wellplot.authoring_service import AuthoringService, CreateTrackRequest
from wellplot.model import AuthoringDocumentIntent


def _successful_result(intent: AuthoringDocumentIntent | None = None) -> AgentSessionResult:
    """Build a minimal successful worker result for one supplied intent."""
    return AgentSessionResult(
        mode="revise",
        success=True,
        intent=intent or AuthoringDocumentIntent(title="Updated transaction title"),
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

"""Private semantic dry-run tests for the CM-15 ProgramRuntime."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import wellplot.authoring_program.program_runtime as runtime_module
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_program.models import AuthoringProgram, ProgramMetrics, ProgramSource
from wellplot.authoring_program.program_runtime import ProgramRuntime
from wellplot.authoring_service import AuthoringService
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent


def _document() -> AuthoringDocumentSpec:
    """Build one canonical document used as immutable dry-run input."""
    return AuthoringDocumentSpec(
        name="program-runtime-test",
        title="Original",
        sections=[
            {
                "id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "id": "cbl",
                        "title": "CBL",
                        "kind": "normal",
                        "width_mm": 24,
                        "bindings": [
                            {
                                "binding_id": "main.cbl.CBL",
                                "channel": "CBL",
                            }
                        ],
                    }
                ],
            }
        ],
    )


def _program() -> AuthoringProgram:
    """Return source evidence for one dry-run result without reinterpreting it."""
    return AuthoringProgram(
        source=ProgramSource(
            text="report = wp.report(title='Revised')\n", logical_name="dry-run.wpa"
        )
    )


def _channel_intent(channel: str = "cement bond") -> AuthoringDocumentIntent:
    """Build one canonical scalar binding request for contextual semantic tests."""
    return AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "cbl",
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "main.cbl.requested",
                                "channel": channel,
                            }
                        ],
                    }
                ],
            }
        ]
    )


def test_successful_dry_run_emits_exact_artifact_and_never_mutates_caller_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Private execution applies requested state only to its isolated service copy."""
    document = _document()
    before = document.model_dump_json()
    captured: dict[str, AuthoringDocumentSpec] = {}

    def capture_private_execution(service: AuthoringService, plan: object) -> object:
        """Observe the private post-state while preserving canonical execution."""
        result = execute_authoring_plan(service, plan)  # type: ignore[arg-type]
        captured["document"] = result.document
        return result

    def persistence_attempted(_service: AuthoringService) -> dict[str, object]:
        """Fail if the dry run attempts canonical mapping serialization."""
        raise AssertionError("Dry run must not serialize or persist the private document.")

    monkeypatch.setattr(runtime_module, "execute_authoring_plan", capture_private_execution)
    monkeypatch.setattr(AuthoringService, "to_mapping", persistence_attempted)
    intent = AuthoringDocumentIntent(
        title="Revised",
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": "cbl", "width_mm": 32}],
            }
        ],
    )
    metrics = ProgramMetrics(program_chars=41, program_calls=1)

    result = ProgramRuntime(document).dry_run(_program(), intent, metrics=metrics)

    assert result.success is True
    assert result.artifact is not None
    assert result.artifact.intent_fragment == intent
    assert result.metrics == metrics
    assert document.model_dump_json() == before
    assert captured["document"].title == "Revised"
    assert captured["document"].sections[0].tracks[0].width_mm == 32


@pytest.mark.parametrize(
    ("available_channels", "channel_aliases", "expected_issue"),
    [
        (
            {"main": ["GR"]},
            ({"id": "cement_bond", "label": "Cement Bond", "mnemonics": ["CBL", "CBLF"]},),
            "channel_missing",
        ),
        (
            {"main": ["CBL", "CBLF"]},
            ({"id": "cement_bond", "label": "Cement Bond", "mnemonics": ["CBL", "CBLF"]},),
            "channel_ambiguous",
        ),
    ],
)
def test_contextual_channel_failures_are_compact_artifact_free_and_non_mutating(
    available_channels: dict[str, list[str]],
    channel_aliases: tuple[dict[str, object], ...],
    expected_issue: str,
) -> None:
    """Existing canonical channel resolution supplies stable dry-run failures."""
    document = _document()
    before = document.model_dump_json()

    result = ProgramRuntime(
        document,
        available_channels=available_channels,
        channel_aliases=channel_aliases,
    ).dry_run(_program(), _channel_intent())

    assert result.success is False
    assert result.artifact is None
    assert result.diagnostics[0].code == "program.dry_run_error"
    assert expected_issue in result.diagnostics[0].message
    assert document.model_dump_json() == before


def test_semantic_raster_compatibility_failure_cannot_emit_a_partial_artifact() -> None:
    """Lower-layer track compatibility is reported without a Code Mode approximation."""
    document = _document()
    before = document.model_dump_json()
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "cbl",
                        "bindings": [
                            {
                                "kind": "raster",
                                "binding_id": "main.cbl.VDL",
                                "channel": "VDL",
                            }
                        ],
                    }
                ],
            }
        ]
    )

    result = ProgramRuntime(
        document,
        available_channels={"main": [{"mnemonic": "VDL", "kind": "array"}]},
    ).dry_run(_program(), intent)

    assert result.success is False
    assert result.artifact is None
    assert "content_track_incompatible" in result.diagnostics[0].message
    assert document.model_dump_json() == before


def test_semantically_incomplete_direct_binding_scope_is_rejected_without_artifact() -> None:
    """A canonical but unscoped direct binding remains a lower-layer dry-run failure."""
    document = _document()
    before = document.model_dump_json()
    intent = AuthoringDocumentIntent(
        curve_bindings=[
            {
                "kind": "curve",
                "binding_id": "unscoped",
                "section_id": "main",
                "channel": "GR",
            }
        ]
    )

    result = ProgramRuntime(document, available_channels={"main": ["GR"]}).dry_run(
        _program(),
        intent,
    )

    assert result.success is False
    assert result.artifact is None
    assert "binding_scope_missing" in result.diagnostics[0].message
    assert document.model_dump_json() == before


def test_equivalent_dry_runs_produce_equal_results() -> None:
    """The runtime retains no private mutation between independent validation calls."""
    intent = AuthoringDocumentIntent(title="Revised")
    runtime = ProgramRuntime(_document())

    first = runtime.dry_run(_program(), intent)
    second = runtime.dry_run(_program(), intent)

    assert first == second


def test_program_runtime_imports_only_canonical_authoring_dependencies() -> None:
    """The private dry-run boundary remains independent from agent and edge layers."""
    module_path = Path(__file__).parents[1] / "src/wellplot/authoring_program/program_runtime.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    forbidden_prefixes = (
        "wellplot.agent",
        "wellplot.mcp",
        "langgraph",
        "mcp",
        "wellplot.render",
        "wellplot.provider",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden_prefixes
    )

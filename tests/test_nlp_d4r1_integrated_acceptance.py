"""Focused D4R1 checks for the canonical structured-worker composition."""

from __future__ import annotations

import inspect

from tests._mcp_fixtures import REPO_ROOT

from wellplot.agent.code_mode.canonical_workers import CanonicalReportWorker
from wellplot.agent.code_mode.typed_section_worker import CanonicalSectionWorker
from wellplot.agent.composition import create_canonical_dependencies
from wellplot.agent.direct_notebook import DirectNotebookSession


def test_d4r1_composition_uses_only_canonical_structured_workers() -> None:
    """The accepted D4R1 route is assembled from the one surviving engine."""
    dependencies = create_canonical_dependencies(backend=object(), server_root=REPO_ROOT)
    assert isinstance(dependencies.report_compiler, CanonicalReportWorker)
    assert isinstance(dependencies.section_compiler, CanonicalSectionWorker)
    assert "typed_delivery" not in inspect.getsource(CanonicalSectionWorker)
    assert "ProgramSectionCompiler" not in inspect.getsource(DirectNotebookSession)


def test_d4r1_fixture_source_is_project_scoped() -> None:
    """The provider-free D4 fixture remains under the repository workspace."""
    fixture = REPO_ROOT / "workspace" / "data"
    assert fixture.is_dir()
    assert fixture.resolve().is_relative_to(REPO_ROOT.resolve())

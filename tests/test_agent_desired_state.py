###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Tests for desired-state planning and agent integration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import anyio

from wellplot.agent import AuthoringRequest, AuthoringSession
from wellplot.authoring import (
    authoring_document_from_mapping,
    authoring_document_to_yaml,
    load_authoring_document,
)
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec


def _document() -> AuthoringDocumentSpec:
    """Build a minimal valid document for desired-state tests."""
    return AuthoringDocumentSpec(
        name="desired-state-test",
        title="Original",
        sections=[
            {
                "id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "id": "curves",
                        "title": "Curves",
                        "kind": "normal",
                        "width_mm": 20,
                        "bindings": [],
                    }
                ],
            }
        ],
    )


class _NoProviderBackend:
    """Backend that proves caller-supplied desired state bypasses the provider."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"
    calls = 0

    async def run_authoring(self, **_: object) -> object:
        """Fail if the typed execution path incorrectly enters the provider loop."""
        self.calls += 1
        raise AssertionError("typed desired-state execution called the provider")


class _TypedRuntime:
    """Minimal runtime for the typed desired-state integration path."""

    def __init__(self, root: Path) -> None:
        self.server_root = root
        self.session: _TypedSession | None = None

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield one stateful fake MCP session."""
        self.session = _TypedSession(self.server_root)
        yield self.session

    def build_tool_definitions(self, **_: object) -> list[object]:
        """Return no provider tools because this test uses a typed caller state."""
        return []

    @staticmethod
    def prompt_text(_: object) -> str:
        """Return an unused prompt value."""
        return ""

    @staticmethod
    def image_bytes(result: object) -> bytes:
        """Extract the fake preview bytes."""
        return bytes(result.content[0].data)

    @staticmethod
    def tool_result_payload(result: object) -> dict[str, object]:
        """Normalize one fake MCP result."""
        return {"structured": getattr(result, "structuredContent", {})}


class _TypedSession:
    """Stateful MCP double that persists the canonical YAML passed by the agent."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.tool_calls: list[tuple[str, dict[str, object]]] = []

    async def get_prompt(self, _: str, __: dict[str, object]) -> object:
        """Reject provider prompt use in the typed caller path."""
        raise AssertionError("typed desired-state execution requested a provider prompt")

    async def list_tools(self) -> object:
        """Reject provider tool discovery in the typed caller path."""
        raise AssertionError("typed desired-state execution listed provider tools")

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Return deterministic metadata and persist the typed executor result."""
        self.tool_calls.append((name, dict(arguments)))
        logfile_path = self.root / str(arguments.get("logfile_path", ""))
        if name == "create_logfile_draft":
            logfile_path = self.root / str(arguments["output_path"])
            logfile_path.parent.mkdir(parents=True, exist_ok=True)
            logfile_path.write_text(authoring_document_to_yaml(_document()) or "", encoding="utf-8")
            return SimpleNamespace(
                structuredContent={
                    "output_path": str(logfile_path),
                    "section_ids": ["main"],
                }
            )
        if name == "save_authoring_document":
            output_path = self.root / str(arguments["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            document = authoring_document_from_mapping(arguments["document"])
            output_path.write_text(authoring_document_to_yaml(document) or "", encoding="utf-8")
            return SimpleNamespace(structuredContent={"output_path": str(output_path)})
        if name == "summarize_logfile_draft":
            return SimpleNamespace(structuredContent=self._summary())
        if name == "inspect_logfile":
            return SimpleNamespace(
                structuredContent={"section_ids": ["main"], "sections": []}
            )
        if name == "validate_logfile":
            return SimpleNamespace(structuredContent={"valid": True})
        if name == "summarize_logfile_changes":
            return SimpleNamespace(
                structuredContent={"summary_lines": ["Updated report title."]}
            )
        if name in {"preview_logfile_png", "preview_section_png"}:
            return SimpleNamespace(content=[SimpleNamespace(data=b"preview")])
        raise AssertionError(f"Unexpected MCP tool: {name}")

    @staticmethod
    def _summary() -> dict[str, object]:
        """Return the source and object context consumed by the planner."""
        return {
            "has_heading": False,
            "has_remarks": False,
            "section_ids": ["main"],
            "sections": [
                {
                    "id": "main",
                    "track_ids": ["curves"],
                    "track_kinds": ["normal"],
                    "available_channels": ["GR"],
                    "source_path": "workspace/data/demo.las",
                    "source_format": "las",
                }
            ],
        }


def test_plan_builds_typed_reconciliation_operations_without_mutation() -> None:
    """Expose a desired-state dry run with the deterministic operation plan."""
    session = AuthoringSession(
        backend=_NoProviderBackend(),
        runtime=_TypedRuntime(Path("/tmp")),
    )

    plan = session.plan(
        text="Update the report title.",
        desired_state=AuthoringDocumentIntent(title="Revised"),
        existing=_document(),
    )

    assert plan.mode == "desired_state"
    assert plan.blocked is False
    assert plan.reconciliation_plan is not None
    assert [operation.object_id for operation in plan.reconciliation_plan.operations] == [
        "report"
    ]
    assert plan.desired_state is not None
    assert plan.desired_state.title == "Revised"


def test_run_executes_typed_desired_state_and_persists_after_verification(tmp_path: Path) -> None:
    """Use the canonical resolver/executor path for a caller-supplied intent."""
    backend = _NoProviderBackend()
    runtime = _TypedRuntime(tmp_path)
    session = AuthoringSession(backend=backend, runtime=runtime)

    result = anyio.run(
        session.run_request,
        AuthoringRequest(
            goal="Update the report title.",
            output_logfile="workspace/demo.log.yaml",
            example_id="demo",
            desired_state={"title": "Revised"},
        ),
    )

    assert backend.calls == 0
    assert result.plan is not None
    assert result.plan.mode == "desired_state"
    assert result.user_report.done
    assert result.phase_summaries
    saved = load_authoring_document(
        tmp_path / "workspace/demo.log.yaml",
        allowed_root=tmp_path,
    )
    assert saved.title == "Revised"
    assert [name for name, _ in runtime.session.tool_calls].count("save_authoring_document") == 1

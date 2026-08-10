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

    def __init__(self, root: Path, *, save_failures: int = 0) -> None:
        self.server_root = root
        self.save_failures = save_failures
        self.session: _TypedSession | None = None

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield one stateful fake MCP session."""
        self.session = _TypedSession(
            self.server_root,
            save_failures=self.save_failures,
        )
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

    def __init__(self, root: Path, *, save_failures: int = 0) -> None:
        self.root = root
        self.save_failures = save_failures
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
            if self.save_failures and arguments.get("output_path") == "workspace/demo.log.yaml":
                self.save_failures -= 1
                raise RuntimeError("Connection closed during save")
            output_path = self.root / str(arguments["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            document = authoring_document_from_mapping(arguments["document"])
            output_path.write_text(authoring_document_to_yaml(document) or "", encoding="utf-8")
            return SimpleNamespace(structuredContent={"output_path": str(output_path)})
        if name == "summarize_logfile_draft":
            return SimpleNamespace(structuredContent=self._summary())
        if name == "inspect_logfile":
            return SimpleNamespace(structuredContent={"section_ids": ["main"], "sections": []})
        if name == "inspect_heading_slots":
            return SimpleNamespace(
                structuredContent={
                    "target_kind": "logfile",
                    "has_heading": False,
                    "has_remarks": False,
                    "has_tail": False,
                    "provider_slots": [],
                    "general_field_slots": [],
                    "service_title_slots": [],
                    "detail_slots": {},
                    "remarks_capabilities": {},
                    "current_values": {},
                    "resource_uris": [],
                }
            )
        if name == "inspect_data_source":
            return SimpleNamespace(
                structuredContent={
                    "source_path": "workspace/data/demo.las",
                    "source_format_detected": "las",
                    "dataset_name": "Demo",
                    "index": {"depth_unit": "m", "sample_count": 2},
                    "channels": [
                        {
                            "mnemonic": "GR",
                            "kind": "scalar",
                            "value_unit": "gAPI",
                            "value_shape": [2],
                        }
                    ],
                    "metadata_keys": [],
                    "warnings": [],
                }
            )
        if name == "validate_logfile":
            return SimpleNamespace(structuredContent={"valid": True})
        if name == "summarize_logfile_changes":
            return SimpleNamespace(structuredContent={"summary_lines": ["Updated report title."]})
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
    assert [operation.object_id for operation in plan.reconciliation_plan.operations] == ["report"]
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
    save_calls = [
        arguments
        for name, arguments in runtime.session.tool_calls
        if name == "save_authoring_document"
    ]
    assert len(save_calls) >= 2
    assert [
        arguments["output_path"]
        for arguments in save_calls
        if arguments["output_path"] == "workspace/demo.log.yaml"
    ] == ["workspace/demo.log.yaml"]
    assert result.phase_summaries[0].preview_kind == "report"
    assert result.phase_summaries[0].preview_png == b"preview"


def test_typed_save_retries_once_after_transport_failure(tmp_path: Path) -> None:
    """Retry an idempotent final save once after a transient MCP failure."""
    runtime = _TypedRuntime(tmp_path, save_failures=1)
    session = AuthoringSession(backend=_NoProviderBackend(), runtime=runtime)

    result = anyio.run(
        session.run_request,
        AuthoringRequest(
            goal="Update the report title.",
            output_logfile="workspace/demo.log.yaml",
            example_id="demo",
            desired_state={"title": "Revised"},
        ),
    )

    saved = load_authoring_document(
        tmp_path / "workspace/demo.log.yaml",
        allowed_root=tmp_path,
    )
    assert saved.title == "Revised"
    assert not result.user_report.warnings_or_errors
    target_save_calls = [
        arguments
        for name, arguments in runtime.session.tool_calls
        if name == "save_authoring_document"
        and arguments["output_path"] == "workspace/demo.log.yaml"
    ]
    assert len(target_save_calls) == 2


def test_typed_save_failure_returns_structured_blocked_result(tmp_path: Path) -> None:
    """Do not leak a closed MCP transport when both final save attempts fail."""
    runtime = _TypedRuntime(tmp_path, save_failures=2)
    session = AuthoringSession(backend=_NoProviderBackend(), runtime=runtime)

    result = anyio.run(
        session.run_request,
        AuthoringRequest(
            goal="Update the report title.",
            output_logfile="workspace/demo.log.yaml",
            example_id="demo",
            desired_state={"title": "Revised"},
        ),
    )

    assert result.validation["valid"] is False
    assert (
        "save_authoring_document failed after 2 attempt(s)"
        in (result.user_report.warnings_or_errors[0])
    )
    assert result.user_report.could_not_do

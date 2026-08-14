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

from wellplot.agent import AuthoringRequest, AuthoringSession, RevisionRequest
from wellplot.agent.core import ProviderRunResult
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


class _BlockedProviderBackend:
    """Provider double that submits one valid but unresolvable channel request."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"
    supports_desired_state = True
    supports_scoped_intent_compatibility = True

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit a typed intent that deterministic channel inspection blocks."""
        tool_name = kwargs["tool_definitions"][0].name
        tool_caller = kwargs["tool_caller"]
        if tool_name == "submit_request_inventory":
            response = await tool_caller(
                tool_name,
                {
                    "items": [
                        {
                            "request_item_id": "request-001",
                            "status": "mapped",
                            "action": "add",
                            "object_family": "curve_binding",
                            "target": "NOT_AVAILABLE",
                            "parent_scope": "main/curves",
                        }
                    ]
                },
            )
            assert response["accepted"] is True
            return SimpleNamespace(final_text="Inventoried blocked request.", tool_trace=())
        assert tool_name == "submit_scalar_intent"
        response = await tool_caller(
            tool_name,
            {
                "intent": {
                    "curve_bindings": [
                        {
                            "kind": "curve",
                            "binding_id": "missing-curve",
                            "section_id": "main",
                            "track_id": "curves",
                            "channel": "NOT_AVAILABLE",
                        }
                    ]
                },
                "coverage": [
                    {
                        "unit_id": "unit-request-001",
                        "status": "mapped",
                    }
                ],
            },
        )
        assert response["accepted"] is True
        return SimpleNamespace(final_text="Submitted blocked intent.", tool_trace=())


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


def test_plan_exposes_unmatched_channel_warning_without_blocking_generic_track() -> None:
    """Report unknown mnemonics while keeping generic construction available."""
    session = AuthoringSession(
        backend=_NoProviderBackend(),
        runtime=_TypedRuntime(Path("/tmp")),
    )
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "custom_sensor",
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "sensor",
                                "channel": "SENSOR_X",
                            }
                        ],
                    }
                ],
            }
        ]
    )

    plan = session.plan(
        text="Add a custom sensor track.",
        desired_state=intent,
        existing=_document(),
        available_channels={"main": ["SENSOR_X"]},
    )

    assert plan.blocked is False
    assert any("Unmatched source channel(s)" in warning for warning in plan.warnings)
    assert any("generic_form:normal" in value for value in plan.defaults_provenance.values())


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
    assert "Updated report." in result.user_report.done
    assert "Updated report title." not in result.user_report.done
    assert result.operation_outcomes
    assert result.operation_outcomes[0]["postcondition_verified"] is True
    assert result.operation_outcomes[0]["verification"]["after"]["value"]["title"] == "Revised"
    assert result.operation_outcomes[0]["object_kind"] == "report"
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


def test_natural_language_run_blocks_backend_without_typed_authoring_support(
    tmp_path: Path,
) -> None:
    """Do not fall back to a broad provider mutation loop for an untyped backend."""
    backend = _NoProviderBackend()
    runtime = _TypedRuntime(tmp_path)
    session = AuthoringSession(backend=backend, runtime=runtime)

    result = anyio.run(
        session.run_request,
        AuthoringRequest(
            goal="Add a resistivity track.",
            output_logfile="workspace/demo.log.yaml",
            example_id="demo",
        ),
    )

    assert backend.calls == 0
    assert result.tool_trace == ()
    assert result.report_facts["extraction"]["status"] == "unsupported_provider"
    assert any(
        "legacy provider-to-MCP mutation loop is disabled" in reason
        for reason in result.user_report.why_not
    )
    assert result.user_report.next_help == (
        "Use a provider with typed authoring support or pass desired_state directly.",
    )


def test_natural_language_revision_blocks_backend_without_typed_authoring_support(
    tmp_path: Path,
) -> None:
    """Keep revisions on the typed path instead of silently using legacy tools."""
    backend = _NoProviderBackend()
    runtime = _TypedRuntime(tmp_path)
    draft_path = tmp_path / "workspace" / "demo.log.yaml"
    draft_path.parent.mkdir(parents=True)
    draft_path.write_text(authoring_document_to_yaml(_document()) or "", encoding="utf-8")
    session = AuthoringSession(backend=backend, runtime=runtime)

    result = anyio.run(
        session.revise_request,
        RevisionRequest(
            feedback="Add a resistivity track.",
            logfile_path="workspace/demo.log.yaml",
        ),
    )

    assert backend.calls == 0
    assert result.tool_trace == ()
    assert result.report_facts["extraction"]["status"] == "unsupported_provider"
    assert any(
        "legacy provider-to-MCP mutation loop is disabled" in reason
        for reason in result.user_report.why_not
    )


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


def test_blocked_provider_plan_preserves_submitted_intent(tmp_path: Path) -> None:
    """Keep extraction evidence available when reconciliation blocks mutation."""
    runtime = _TypedRuntime(tmp_path)
    session = AuthoringSession(backend=_BlockedProviderBackend(), runtime=runtime)

    result = anyio.run(
        session.run_request,
        AuthoringRequest(
            goal="Bind an unavailable curve.",
            output_logfile="workspace/demo.log.yaml",
            example_id="demo",
        ),
    )

    assert result.plan is not None
    assert result.plan.blocked is True
    assert result.submitted_intent is not None
    assert result.submitted_intent["curve_bindings"][0]["channel"] == "NOT_AVAILABLE"


def test_old_provider_capability_does_not_fallback_to_scoped_compiler(tmp_path: Path) -> None:
    """Block a backend that lacks the authoritative direct-operation capability."""

    class _OldCapabilityOnlyBackend(_NoProviderBackend):
        supports_desired_state = True

    runtime = _TypedRuntime(tmp_path)
    result = anyio.run(
        AuthoringSession(
            backend=_OldCapabilityOnlyBackend(),
            runtime=runtime,
        ).run_request,
        AuthoringRequest(
            goal="Add a remarks block.",
            output_logfile="workspace/old-capability.log.yaml",
            example_id="old-capability",
        ),
    )

    assert result.plan is None
    assert result.tool_trace == ()
    assert any(
        "does not support typed authoring extraction" in item
        for item in result.user_report.why_not
    )


def test_merge_failure_report_preserves_the_canonical_diagnostic(tmp_path: Path) -> None:
    """Keep the exact compiler reason instead of replacing it with provider advice."""

    class _MergeFailureSession(AuthoringSession):
        async def _extract_desired_state(self, **_: object) -> tuple[ProviderRunResult, None]:
            return (
                ProviderRunResult(
                    final_text="",
                    tool_trace=(),
                    report_facts={
                        "reasons": [
                            "Desired-state compilation failed: Intent field 'subtitle' "
                            "cannot be null."
                        ],
                        "extraction": {"status": "merge_failed"},
                    },
                ),
                None,
            )

    class _MergeFailureBackend(_NoProviderBackend):
        supports_desired_state = True
        supports_scoped_intent_compatibility = True

    runtime = _TypedRuntime(tmp_path)
    session = _MergeFailureSession(backend=_MergeFailureBackend(), runtime=runtime)

    result = anyio.run(
        session.run_request,
        AuthoringRequest(
            goal="Add a remarks block.",
            output_logfile="workspace/demo.log.yaml",
            example_id="demo",
        ),
    )

    assert "Desired-state compilation failed: Intent field 'subtitle' cannot be null." in (
        result.user_report.why_not
    )
    assert (
        "The provider submission could not be merged into one canonical desired state."
        in result.user_report.why_not
    )

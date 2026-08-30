"""Tests for transactional execution of graph-compiled reconstructions."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile

import pytest
from pydantic import BaseModel

pytest.importorskip("langgraph")

from langgraph.graph.state import CompiledStateGraph

import wellplot.agent.graph.reconstruction_execution as reconstruction_execution
from wellplot.agent.graph import (
    ReconstructionGraphDependencies,
    ReconstructionPlanner,
    ReportCompiler,
    SectionCompiler,
    build_compile_graph,
    execute_document_reconstruction,
)
from wellplot.agent.graph.verifier import (
    DocumentIntentVerificationResult,
    IntentVerificationIssue,
)
from wellplot.authoring import load_authoring_document
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "agentic_cbl"


@dataclass
class _ReconstructionModel:
    """Return one simple reconstruction without external provider access."""

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[BaseModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
    ) -> BaseModel:
        """Return the exact reconstruction plan and artifacts for this test."""
        del instructions, user_message, tool_description, max_rounds
        if tool_name == "submit_reconstruction_plan":
            return response_model.model_validate(
                {
                    "summary": "Build the main pass.",
                    "sections": [
                        {
                            "section_id": "main_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Build the main pass.",
                        }
                    ],
                }
            )
        if tool_name == "submit_report_artifact":
            return response_model.model_validate({"intent": {"title": "Reconstructed"}})
        if tool_name == "submit_section_artifact":
            return response_model.model_validate(
                {"section": {"section_id": "main_pass", "title": "Main pass"}}
            )
        raise AssertionError(f"Unexpected structured model request: {tool_name}")


@dataclass
class _FrozenCblModel:
    """Return frozen CBL compiler results without a provider or MCP."""

    contract: dict[str, object]

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[BaseModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
    ) -> BaseModel:
        """Return the fixture response for the planned compiler target."""
        del instructions, tool_description, max_rounds
        artifacts = self.contract["artifacts"]
        if tool_name == "submit_reconstruction_plan":
            payload = self.contract["reconstruction_plan"]
        elif tool_name == "submit_report_artifact":
            payload = artifacts["report"]
        elif "Compile section 'main_pass'." in user_message:
            payload = artifacts["sections"]["main_pass"]
        elif "Compile section 'repeat_pass'." in user_message:
            payload = artifacts["sections"]["repeat_pass"]
        else:
            raise AssertionError(f"Unexpected compiler target: {tool_name!r}")
        return response_model.model_validate(payload)


def _graph() -> CompiledStateGraph:
    """Build the generic graph with deterministic reconstruction responses."""
    registry = create_builtin_registry()
    model = _ReconstructionModel()
    return build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )


def _service() -> AuthoringService:
    """Build a minimal canonical starter document."""
    return AuthoringService(
        AuthoringDocumentSpec(
            name="reconstruction-execution-test",
            title="Original",
            sections=[
                {
                    "id": "main_pass",
                    "title": "Starter main pass",
                    "tracks": [
                        {
                            "id": "depth",
                            "title": "Depth",
                            "kind": "reference",
                            "width_mm": 20,
                        }
                    ],
                }
            ],
        )
    )


def _frozen_cbl_graph(contract: dict[str, object]) -> CompiledStateGraph:
    """Build the generic graph with frozen CBL compiler responses."""
    registry = create_builtin_registry()
    model = _FrozenCblModel(contract=contract)
    return build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )


def _cased_hole_service(tmp_path: Path) -> AuthoringService:
    """Load the tracked cased-hole scaffold without workspace state."""
    for filename in ("base.template.yaml", "cased_hole_starter.log.yaml"):
        copyfile(_FIXTURE_DIR / filename, tmp_path / filename)
    return AuthoringService(load_authoring_document(tmp_path / "cased_hole_starter.log.yaml"))


def test_reconstruction_execution_applies_and_verifies_document() -> None:
    """A reconstruction transaction applies the compiled canonical intent."""
    service = _service()

    result = asyncio.run(
        execute_document_reconstruction(
            _graph(),
            service,
            request="Build the main pass.",
        )
    )

    assert result.success is True, result.errors
    assert result.rolled_back is False
    assert result.verification is not None
    assert result.verification.success is True
    assert result.reconstruction.plan.sections[0].section_id == "main_pass"
    assert service.document.title == "Reconstructed"
    assert service.document.sections[0].title == "Main pass"


def test_reconstruction_execution_rolls_back_when_final_verification_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed final postcondition restores the original canonical document."""
    service = _service()
    before = service.document.model_dump(mode="json")
    original_verifier = reconstruction_execution.verify_document_intent

    def fail_verification(*args: object, **kwargs: object) -> DocumentIntentVerificationResult:
        """Inject one postcondition failure after normal verification succeeds."""
        verified = original_verifier(*args, **kwargs)
        return DocumentIntentVerificationResult(
            document=verified.document,
            resolution=verified.resolution,
            reconciliation_plan=verified.reconciliation_plan,
            issues=(
                IntentVerificationIssue(
                    path="main_pass",
                    code="forced_failure",
                    message="Forced final verification failure.",
                ),
            ),
        )

    monkeypatch.setattr(reconstruction_execution, "verify_document_intent", fail_verification)
    result = asyncio.run(
        execute_document_reconstruction(
            _graph(),
            service,
            request="Build the main pass.",
        )
    )

    assert result.success is False
    assert result.rolled_back is True
    assert result.verification is not None
    assert result.verification.success is False
    assert result.errors == ("Forced final verification failure.",)
    assert service.document.model_dump(mode="json") == before


def test_reconstruction_execution_applies_frozen_cbl_transaction(tmp_path: Path) -> None:
    """The full frozen CBL reconstruction compiles and verifies without MCP."""
    prompt = (_FIXTURE_DIR / "frozen_prompt.txt").read_text(encoding="utf-8")
    contract = json.loads((_FIXTURE_DIR / "compile_contract.json").read_text(encoding="utf-8"))
    service = _cased_hole_service(tmp_path)
    source_manifest = contract["source_manifest"]

    result = asyncio.run(
        execute_document_reconstruction(
            _frozen_cbl_graph(contract),
            service,
            request=prompt,
            source_manifest=source_manifest,
            available_channels={
                section_id: source["channels"] for section_id, source in source_manifest.items()
            },
            header_aliases=contract["execution_context"]["header_aliases"],
        )
    )

    assert result.success is True, result.errors
    assert result.verification is not None
    assert result.verification.success is True
    assert [section.id for section in service.document.sections] == ["main_pass", "repeat_pass"]
    for section in service.document.sections:
        assert [track.id for track in section.tracks] == ["combo", "depth", "cbl", "vdl"]

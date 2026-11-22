"""Provider-free stale-snapshot tests for MCP graph authoring."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Never
from unittest.mock import patch

import pytest
import yaml
from tests._mcp_fixtures import (
    REPO_ROOT,
    Host02GammaBackend,
    create_approved_gamma_fixture_paths,
    create_mcp_fixture_paths,
)

from wellplot.agent.code_mode.obligations import (
    RequestObligation,
    verify_document_postconditions,
)
from wellplot.agent.code_mode.planner import _PlannerWirePlan
from wellplot.agent.code_mode.semantic_actions import UpdateCurveScaleAction
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.code_mode.state import SemanticReleaseCustody
from wellplot.agent.composition import create_canonical_compile_facade
from wellplot.agent.direct_notebook import (
    DirectNotebookSession,
    _apply_result,
    _load_document_context,
)
from wellplot.agent.providers.base import ProviderMetrics, StructuredGenerationResult
from wellplot.agent.session import (
    AgentMetrics,
    AgentSession,
    AgentSessionConfig,
    AgentSessionResult,
    AgentWorkerEvidence,
)
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


class _McpSourceContextBackend:
    """Return frozen semantic outputs while leaving host compilation canonical."""

    def __init__(self) -> None:
        self.section_source_channels: tuple[str, ...] = ()

    async def generate_structured(
        self,
        request: object,
        *,
        response_model: type[object],
    ) -> StructuredGenerationResult[object]:
        """Supply one fixed scale plan and act only on host-issued handles."""
        if response_model is _PlannerWirePlan:
            value = response_model.model_validate(
                {
                    "version": "wellplot.semantic-plan.v2",
                    "summary": "Set the existing GR curve scale.",
                    "section_tasks": [
                        {
                            "goal": "Update the GR scale in Main Log.",
                            "capability_ids": [
                                "section.log_plot",
                                "track.normal",
                                "binding.curve",
                            ],
                            "existing_section_hint": "Main Log",
                            "source_hints": ["fixture.las"],
                            "requirements": [],
                            "constraints": [],
                            "scope_ref": "fixture_main",
                            "operations": [
                                {
                                    "local_ref": "update_gr_scale",
                                    "scope_ref": "fixture_main",
                                    "verb": "SET",
                                    "object_kind": "binding",
                                    "target_clue": "GR",
                                    "field_values": [
                                        {
                                            "field": "scale_minimum",
                                            "state": "SET",
                                            "value": 5.0,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        elif response_model is UpdateCurveScaleAction:
            payload = yaml.safe_load(request.user_prompt)
            section_context = payload["section_context"]
            self.section_source_channels = tuple(
                channel["mnemonic"]
                for source in section_context["sources"]
                for channel in source["channels"]
            )
            target_handle = payload["section_work_contract"]["target_handle"]
            value = response_model.model_validate(
                {
                    "action": "update_curve_scale",
                    "target": {"handle": target_handle},
                    "scale": {"kind": "linear", "minimum": 5.0, "maximum": 125.0},
                }
            )
        else:
            raise AssertionError(f"unexpected canonical worker model: {response_model!r}")

        return StructuredGenerationResult(
            value=value,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


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


def test_public_mcp_revision_passes_declared_source_into_canonical_context() -> None:
    """A valid source-backed request reaches canonical section enrichment."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-source-context-") as temp_dir:
        fixture_paths = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        backend = _McpSourceContextBackend()
        session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=backend,
                server_root=REPO_ROOT,
            ),
            config=AgentSessionConfig(),
        )
        operations = GraphAuthoringMcpOperations.create(session=session, root=REPO_ROOT)
        request = "In Main Log, set the GR curve to a linear 5-125 scale using fixture.las."

        result = asyncio.run(
            operations.revise(
                logfile_path=str(fixture_paths.single_logfile),
                request=request,
            )
        )

        assert result.success is True, result.errors
        assert "GR" in backend.section_source_channels
        persisted = yaml.safe_load(fixture_paths.single_logfile.read_text(encoding="utf-8"))
        gr_binding = next(
            item
            for item in persisted["document"]["bindings"]["channels"]
            if item["channel"] == "GR"
        )
        assert gr_binding["scale"]["kind"] == "linear"
        assert gr_binding["scale"]["min"] == 5.0
        assert gr_binding["scale"]["max"] == 125.0


def test_notebook_and_mcp_revisions_persist_equivalent_canonical_documents() -> None:
    """Current public adapters converge on the same canonical persisted state."""
    request = "In Main Log, set the GR curve to a linear 5-125 scale using fixture.las."
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="entrypoint-parity-") as temp_dir:
        root = Path(temp_dir)
        notebook_fixture = create_mcp_fixture_paths(root / "notebook")
        mcp_fixture = create_mcp_fixture_paths(root / "mcp")

        notebook_session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=_McpSourceContextBackend(),
                server_root=REPO_ROOT,
            ),
            config=AgentSessionConfig(),
        )
        mcp_session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=_McpSourceContextBackend(),
                server_root=REPO_ROOT,
            ),
            config=AgentSessionConfig(),
        )
        notebook = DirectNotebookSession(
            session=notebook_session,
            provider="test",
            model="test-model",
            credential_source=None,
            server_root=REPO_ROOT,
        )
        mcp = GraphAuthoringMcpOperations.create(session=mcp_session, root=REPO_ROOT)

        notebook_result = asyncio.run(
            notebook.revise(
                feedback=request,
                logfile_path=notebook_fixture.single_logfile,
            )
        )
        mcp_result = asyncio.run(
            mcp.revise(
                logfile_path=str(mcp_fixture.single_logfile),
                request=request,
            )
        )

        notebook_document = yaml.safe_load(
            notebook_fixture.single_logfile.read_text(encoding="utf-8")
        )["document"]
        mcp_document = yaml.safe_load(mcp_fixture.single_logfile.read_text(encoding="utf-8"))[
            "document"
        ]

    assert notebook_result.report_facts["success"] is True
    assert mcp_result.success is True, mcp_result.errors
    assert notebook_document == mcp_document
    gr_binding = next(
        item for item in mcp_document["bindings"]["channels"] if item["channel"] == "GR"
    )
    assert gr_binding["scale"] == {
        "kind": "linear",
        "min": 5.0,
        "max": 125.0,
        "reverse": False,
    }


def test_compile_only_does_not_apply_or_publish() -> None:
    """A real graph compile returns intent and leaves both source document and YAML alone."""
    request = "In Main Log, set the GR curve to a linear 5-125 scale using fixture.las."
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="compile-only-") as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        context = _request_context(str(fixture.single_logfile), root=REPO_ROOT)
        before = context.document.model_dump(mode="json")
        original = fixture.single_logfile.read_bytes()
        session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=_McpSourceContextBackend(), server_root=REPO_ROOT
            )
        )
        with (
            patch("wellplot.agent._private_apply.execute_authoring_plan") as execute,
            patch.object(mcp_service, "persist_authoring_document") as persist,
        ):
            result = asyncio.run(
                session.revise(
                    request=request, document=context.document, sources=context.source_candidates
                )
            )
        assert result.success and result.intent is not None and result.obligations
        execute.assert_not_called()
        persist.assert_not_called()
        assert context.document.model_dump(mode="json") == before
        assert fixture.single_logfile.read_bytes() == original


def test_verified_no_op_does_not_publish_in_either_adapter() -> None:
    """An unchanged verified candidate is distinct from publication."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="adapter-no-op-") as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        before = fixture.single_logfile.read_bytes()
        notebook_context = _load_document_context(fixture.single_logfile, root=REPO_ROOT)
        mcp_context = _request_context(str(fixture.single_logfile), root=REPO_ROOT)
        result = _successful_result(AuthoringDocumentIntent(title=notebook_context.document.title))
        with (
            patch(
                "wellplot.agent._private_apply.verify_document_postconditions",
                wraps=verify_document_postconditions,
            ) as verify,
            patch.object(mcp_service, "persist_authoring_document") as persist,
        ):
            notebook = _apply_result(context=notebook_context, result=result, root=REPO_ROOT)
            mcp = _apply_session_result(context=mcp_context, session_result=result, root=REPO_ROOT)

        assert notebook[:5] == (True, False, False, [], "no_op")
        assert notebook[5]["semantic_postcondition"] == "PASS"
        assert notebook[5]["persistence"] == "PASS"
        assert mcp[:5] == (True, False, False, [], ["no_op"])
        assert verify.call_count == 2
        persist.assert_not_called()
        assert fixture.single_logfile.read_bytes() == before


def test_host02_automatic_semantic_contract_reaches_both_adapters() -> None:
    """Notebook and MCP publish the same host-compiled Gamma Ray contract."""
    request = "Plot Gamma Ray."
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="host02-adapter-parity-") as temp_dir:
        root = Path(temp_dir)
        notebook_fixture = create_approved_gamma_fixture_paths(root / "notebook")
        mcp_fixture = create_approved_gamma_fixture_paths(root / "mcp")
        notebook_backend = Host02GammaBackend()
        mcp_backend = Host02GammaBackend()
        notebook_compilations: list[object] = []
        mcp_compilations: list[object] = []
        notebook_session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=notebook_backend,
                server_root=REPO_ROOT,
                result_callback=notebook_compilations.append,
            ),
            config=AgentSessionConfig(),
        )
        mcp_session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=mcp_backend,
                server_root=REPO_ROOT,
                result_callback=mcp_compilations.append,
            ),
            config=AgentSessionConfig(),
        )
        notebook = DirectNotebookSession(
            session=notebook_session,
            provider="test",
            model="test-model",
            credential_source=None,
            server_root=REPO_ROOT,
        )
        mcp = GraphAuthoringMcpOperations.create(session=mcp_session, root=REPO_ROOT)

        with patch(
            "wellplot.agent._private_apply.verify_document_postconditions",
            wraps=verify_document_postconditions,
        ) as verify:
            notebook_result = asyncio.run(
                notebook.revise(
                    feedback=request,
                    logfile_path=notebook_fixture.single_logfile,
                )
            )
            assert verify.call_count == 1
            mcp_result = asyncio.run(
                mcp.revise(
                    logfile_path=str(mcp_fixture.single_logfile),
                    request=request,
                )
            )
            assert verify.call_count == 2

        assert notebook_result.report_facts["success"] is True
        assert (
            notebook_result.report_facts["host_stage_evidence"]["semantic_postcondition"] == "PASS"
        )
        assert mcp_result.success is True, mcp_result.errors
        assert notebook_backend.response_models == ["_PlannerWirePlan", "AddBindingAction"]
        assert mcp_backend.response_models == ["_PlannerWirePlan", "AddBindingAction"]

        notebook_contract = notebook_compilations[0].semantic_publication_contract
        mcp_contract = mcp_compilations[0].semantic_publication_contract
        assert notebook_contract is not None
        assert mcp_contract is not None
        assert notebook_contract.trusted_release is not None
        assert notebook_contract.trusted_release == mcp_contract.trusted_release
        assert "trusted_release" not in notebook_contract.model_dump(mode="json")
        assert notebook_contract.model_dump(mode="json") == mcp_contract.model_dump(mode="json")
        expected = notebook_contract.expected_bindings[0]
        assert expected.requested_term == "Gamma Ray"
        assert expected.source_handle == "source-1"
        assert expected.track_id == "gr"

        notebook_document = yaml.safe_load(
            notebook_fixture.single_logfile.read_text(encoding="utf-8")
        )["document"]
        mcp_document = yaml.safe_load(mcp_fixture.single_logfile.read_text(encoding="utf-8"))[
            "document"
        ]
        for document in (notebook_document, mcp_document):
            gamma_bindings = [
                binding
                for binding in document["bindings"]["channels"]
                if binding["channel"] == "GR"
            ]
            assert len(gamma_bindings) == 1
            assert gamma_bindings[0]["track_id"] == "gr"


@pytest.mark.parametrize(
    ("defect", "code"),
    [
        ("lost", "semantic_release_custody_mismatch"),
        ("changed_snapshot", "semantic_release_custody_mismatch"),
        ("changed_request", "semantic_release_custody_mismatch"),
        ("injected_release", "semantic_release_custody_mismatch"),
        ("duplicate", "semantic_release_custody_duplicate"),
        ("deployment_changed", "semantic_catalog_stale"),
        ("deployment_unavailable", "semantic_catalog_pin_missing"),
    ],
)
def test_real_graph_release_custody_rejects_alteration(
    defect: str, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the real handoff, then prove custody failures cannot publish."""
    import wellplot.semantic_catalog as catalog

    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="gate2a-rc-") as temp_dir:
        fixture = create_approved_gamma_fixture_paths(Path(temp_dir) / "fixture")
        before = fixture.single_logfile.read_bytes()
        facade = create_canonical_compile_facade(
            backend=Host02GammaBackend(),
            server_root=REPO_ROOT,
        )
        real_invoke = facade._graph.ainvoke
        original = catalog.load_deployed_catalog_release()
        replacement = original.model_copy(
            update={"pin": original.pin.model_copy(update={"approval_record_ref": "replacement"})}
        )
        assert original.pin != replacement.pin
        assert original.pin.catalog_artifact_sha256 == replacement.pin.catalog_artifact_sha256
        assert original.pin.content_sha256 == replacement.pin.content_sha256

        async def intercept(
            state: dict[str, Any], *, context: SemanticReleaseCustody
        ) -> dict[str, Any]:
            result = await real_invoke(state, context=context)
            payload = result["semantic_publication_contract"]
            assert "trusted_release" not in payload
            contract = SemanticPublicationContract.model_validate(payload)
            assert contract.trusted_release is None
            if defect == "lost":
                result.pop("semantic_publication_contract")
            elif defect == "changed_snapshot":
                payload["expected_bindings"][0]["inspection_snapshot_id"] = "new-snapshot"
            elif defect == "changed_request":
                result["request"] = "Plot a different channel."
            elif defect == "injected_release":
                payload["trusted_release"] = replacement.model_dump(mode="json")
            elif defect == "duplicate":
                restored = context.restore(contract, state["request"])
                assert restored is not None
                context.capture(restored)
            elif defect == "deployment_changed":
                monkeypatch.setattr(catalog, "load_deployed_catalog_release", lambda: replacement)
            else:

                def unavailable() -> Never:
                    raise catalog.SemanticCatalogTrustError("semantic_catalog_pin_missing")

                monkeypatch.setattr(catalog, "load_deployed_catalog_release", unavailable)
            return result

        monkeypatch.setattr(facade._graph, "ainvoke", intercept)
        operations = GraphAuthoringMcpOperations.create(
            session=AgentSession(compiler=facade, config=AgentSessionConfig()),
            root=REPO_ROOT,
        )
        with patch("wellplot.mcp.agentic.service.persist_authoring_document") as persist:
            result = asyncio.run(
                operations.revise(
                    logfile_path=str(fixture.single_logfile),
                    request="Plot Gamma Ray.",
                )
            )
        assert not result.success
        assert code in repr(result)
        persist.assert_not_called()
        assert fixture.single_logfile.read_bytes() == before


def test_host02_notebook_ignores_planner_hint_for_host_context_scope() -> None:
    """The canonical Notebook path ignores a planner-selected section hint."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="host02-scope-authority-") as temp_dir:
        fixture = create_approved_gamma_fixture_paths(Path(temp_dir) / "notebook")
        backend = Host02GammaBackend(existing_section_hint="Invented Section")
        session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=backend,
                server_root=REPO_ROOT,
            ),
            config=AgentSessionConfig(),
        )
        notebook = DirectNotebookSession(
            session=session,
            provider="test",
            model="test-model",
            credential_source=None,
            server_root=REPO_ROOT,
        )

        result = asyncio.run(
            notebook.revise(
                feedback="Plot Gamma Ray.",
                logfile_path=fixture.single_logfile,
            )
        )

        assert result.report_facts["success"] is True
        assert backend.response_models == ["_PlannerWirePlan", "AddBindingAction"]


@pytest.mark.parametrize("adapter", ("notebook", "mcp"))
def test_host02_automatic_semantic_failure_prevents_both_publications(
    adapter: str,
) -> None:
    """A shared semantic rejection blocks publication for each public adapter."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="host02-adapter-reject-") as temp_dir:
        root = Path(temp_dir)
        fixture = create_approved_gamma_fixture_paths(root / adapter)
        original_bytes = fixture.single_logfile.read_bytes()
        backend = Host02GammaBackend()
        compilations: list[object] = []
        session = AgentSession(
            compiler=create_canonical_compile_facade(
                backend=backend,
                server_root=REPO_ROOT,
                result_callback=compilations.append,
            ),
            config=AgentSessionConfig(),
        )
        if adapter == "notebook":
            operation = DirectNotebookSession(
                session=session,
                provider="test",
                model="test-model",
                credential_source=None,
                server_root=REPO_ROOT,
            )
        else:
            operation = GraphAuthoringMcpOperations.create(session=session, root=REPO_ROOT)

        with (
            patch(
                "wellplot.agent.code_mode.obligations.verify_semantic_publication",
                side_effect=ValueError("injected semantic rejection"),
            ),
            patch(
                "wellplot.agent.direct_notebook.mcp_service.persist_authoring_document"
            ) as notebook_persist,
            patch("wellplot.mcp.agentic.service.persist_authoring_document") as mcp_persist,
        ):
            if adapter == "notebook":
                result = asyncio.run(
                    operation.revise(
                        feedback="Plot Gamma Ray.",
                        logfile_path=fixture.single_logfile,
                    )
                )
                assert result.report_facts["success"] is False
                notebook_persist.assert_not_called()
            else:
                result = asyncio.run(
                    operation.revise(
                        logfile_path=str(fixture.single_logfile),
                        request="Plot Gamma Ray.",
                    )
                )
                assert result.success is False
                mcp_persist.assert_not_called()

        assert fixture.single_logfile.read_bytes() == original_bytes
        assert compilations[0].semantic_publication_contract is not None
        assert backend.response_models == ["_PlannerWirePlan", "AddBindingAction"]


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
                "wellplot.agent._private_apply.execute_authoring_plan",
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


def test_mcp_shared_verifier_passes_before_persistence() -> None:
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
                "wellplot.agent._private_apply.verify_document_postconditions",
                side_effect=record_verify,
            ),
            patch(
                "wellplot.mcp.agentic.service.persist_authoring_document",
                side_effect=record_persist,
            ) as persist,
        ):
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
        assert events == [
            "verifier_enter",
            "verifier_pass",
            "persistence_enter",
            "persistence_pass",
        ]
        persist.assert_called_once()
        assert fixture_paths.single_logfile.read_bytes() != original_bytes

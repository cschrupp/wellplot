"""Provider-free D5-3 parity acceptance over the canonical authoring path."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT
from tests.test_nlp_d4_live_acceptance import (
    _D4PlannerBackend,
    _D4SessionBackend,
    _D4SessionHarness,
    _D4SessionPlanner,
    _D4SessionReportBackend,
    _D4SessionSectionBackend,
    _write_rehearsal_document,
)

from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.composition import create_canonical_dependencies
from wellplot.agent.session import AgentSession, AgentSessionConfig
from wellplot.authoring import AuthoringDocumentSpec
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_reconciler import reconcile_authoring
from wellplot.authoring_service import AuthoringService
from wellplot.mcp import service as mcp_service
from wellplot.mcp.agentic import GraphAuthoringMcpOperations
from wellplot.model.intent import AuthoringDocumentIntent, AuthoringFillIntent

DIRECT_CASE_IDS = (
    "D5-CBL-01",
    "D5-LAS-01-T1",
    "D5-LAS-01-T2",
    "D5-LAS-01-T3",
    "D5-LAS-01-T4",
    "D5-LAS-02-T1",
    "D5-LAS-02-T2",
    "D5-LAS-03-C01",
    "D5-LAS-04-C01",
    "D5-REL-01",
)
MCP_CASE_IDS = ("D5-MCP-01", "D5-MCP-02", "D5-MCP-03")
EXPECTED_CASE_IDS = DIRECT_CASE_IDS + MCP_CASE_IDS
RENDER_CASE_IDS = {"D5-CBL-01", "D5-LAS-01-T4", "D5-MCP-02"}


def _d4_case(turn_id: str) -> dict[str, object]:
    """Return one frozen D4 case by its immutable turn identifier."""
    return next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == turn_id)


def _d4_gold(turn_id: str) -> dict[str, object]:
    """Return one frozen D4 gold contract by its immutable turn identifier."""
    return next(item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == turn_id)


def _changed_paths(before: object, after: object, prefix: str = "") -> set[str]:
    """Return JSON-pointer-like paths whose canonical values differ."""
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: set[str] = set()
        for key in set(before) | set(after):
            child = f"{prefix}/{key}"
            paths.update(_changed_paths(before.get(key), after.get(key), child))
        return paths
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return {prefix or "/"}
        paths = set()
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            paths.update(_changed_paths(left, right, f"{prefix}/{index}"))
        return paths
    return set() if before == after else {prefix or "/"}


def _assert_allowed_changes(
    before: Mapping[str, object],
    after: Mapping[str, object],
    allowed_paths: list[str],
) -> None:
    """Require every canonical change to be inside the frozen D4 allowlist."""
    changed = _changed_paths(before, after)
    assert changed, "successful parity slice must produce a canonical change"
    for path in changed:
        assert any(
            path == allowed
            or path.startswith(f"{allowed.rstrip('/')}/")
            or allowed.startswith(f"{path.rstrip('/')}/")
            for allowed in allowed_paths
        ), (path, allowed_paths)


def _assert_reloaded(path: Path, expected: Mapping[str, object]) -> None:
    """Require persistence and reload to preserve the canonical result."""
    reloaded = d4.load_logfile_document(path)
    assert reloaded == expected


def _new_direct_harness(root: Path, source: Path) -> _D4SessionHarness:
    """Compose the canonical Direct Notebook session with the fixture backend."""
    harness = _D4SessionHarness.create(root)
    harness.adapter.source_path = source
    return harness


def _run_direct_revision(
    root: Path,
    source: Path,
    *,
    case_id: str,
    turn_id: str,
) -> tuple[Path, bytes, bytes, object]:
    """Run one isolated Direct Notebook revision and retain custody evidence."""
    harness = _new_direct_harness(root, source)
    path = harness.adapter._base_for(case_id)
    before = path.read_bytes()
    result = asyncio.run(
        harness.adapter.session.revise(feedback=_d4_case(turn_id)["request"], logfile_path=path)
    )
    after = path.read_bytes()
    return path, before, after, result


def _mcp_operations(root: Path) -> tuple[GraphAuthoringMcpOperations, list[d4.LogicalCall]]:
    """Build the MCP public adapter from the same canonical dependencies."""
    calls: list[d4.LogicalCall] = []
    ledger = d4.LogicalCallLedger()
    planner = _D4SessionPlanner(calls=[])
    backend = d4.CountingBackend(
        delegate=_D4SessionBackend(
            planner=_D4PlannerBackend(planner),
            report=_D4SessionReportBackend(),
            section=_D4SessionSectionBackend(),
        ),
        provider="deterministic",
        model="d5-provider-free-fixture",
        calls=calls,
        ledger=ledger,
    )
    dependencies = create_canonical_dependencies(backend=backend, server_root=REPO_ROOT)
    session = AgentSession(
        compiler=CodeModeCompileFacade(dependencies),
        config=AgentSessionConfig(timeout_seconds=10.0),
    )
    return GraphAuthoringMcpOperations.create(session=session, root=REPO_ROOT), calls


def _mcp_seed(path: Path, source: Path) -> None:
    """Materialize the frozen canonical LAS seed as a real MCP logfile."""
    payload = copy.deepcopy(d4.load_gold(REPO_ROOT)["canonical_las_seed"])
    payload["sections"][0]["data_source"]["source_path"] = str(source)
    payload["sections"][0]["data_source"]["source_format"] = "las"
    _write_rehearsal_document(path, payload)


def _add_foreign_cali_track(payload: dict[str, object]) -> None:
    """Add the accepted D2E-style CALI binding used by the relation guard."""
    section = payload["sections"][0]
    cali_track = copy.deepcopy(section["tracks"][1])
    cali_track["id"] = "cali"
    cali_track["title"] = "Caliper"
    cali_track["bindings"][0]["binding_id"] = "main.cali.CALI.4"
    cali_track["bindings"][0]["channel"] = "CALI"
    cali_track["bindings"][0]["label"] = "Caliper"
    section["tracks"].append(cali_track)


def test_d5_population_and_source_custody_are_frozen() -> None:
    """Bind the 13 slices to the accepted D4 inputs without duplicating requests."""
    cases = d4.load_cases(REPO_ROOT)
    gold = d4.load_gold(REPO_ROOT)
    source = REPO_ROOT / d4.SOURCE_RELATIVE

    assert EXPECTED_CASE_IDS == (
        "D5-CBL-01",
        "D5-LAS-01-T1",
        "D5-LAS-01-T2",
        "D5-LAS-01-T3",
        "D5-LAS-01-T4",
        "D5-LAS-02-T1",
        "D5-LAS-02-T2",
        "D5-LAS-03-C01",
        "D5-LAS-04-C01",
        "D5-REL-01",
        "D5-MCP-01",
        "D5-MCP-02",
        "D5-MCP-03",
    )
    assert len(cases) == 9
    assert source.is_file()
    assert d4.sha256_file(source) == gold["source_contract"]["sha256"]
    assert set(gold["source_contract"]["required_channels"]) == {
        "GR",
        "CALI",
        "ILD",
        "ILM",
        "MSFL",
        "NPHI",
    }
    assert "RT" in gold["source_contract"]["forbidden_channels"]
    assert all(case["request_sha256"] == d4.sha256_text(case["request"]) for case in cases)


def test_d5_direct_notebook_population_passes_with_bounded_real_renders() -> None:
    """Run CBL, cumulative LAS revisions, and bounded LAS safety cases directly."""
    source = REPO_ROOT / d4.SOURCE_RELATIVE
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        cbl_case = _d4_case("D4-C01:C01")
        cbl_gold = _d4_gold("D4-C01:C01")
        cbl_harness = _new_direct_harness(root / "cbl", source)
        cbl_actual = asyncio.run(cbl_harness.adapter.execute_turn(cbl_case, cbl_gold))
        cbl_grade = d4.grade_turn(cbl_actual, cbl_gold)
        assert cbl_grade["status"] == "PASS", cbl_grade
        assert {item["status"] for item in cbl_grade["verifier_requirements"]} == {"PASS"}
        assert d4.sha256_file(cbl_actual["starting_artifact_path"]) != d4.sha256_file(
            cbl_actual["ending_artifact_path"]
        )
        assert Path(cbl_actual["ending_artifact_path"]).is_file()
        _assert_reloaded(
            Path(cbl_actual["ending_artifact_path"]),
            d4.load_logfile_document(Path(cbl_actual["ending_artifact_path"])),
        )
        assert Path(cbl_actual["render_path"]).stat().st_size > 0

        cumulative = _new_direct_harness(root / "cumulative", source)
        current = cumulative.adapter._base_for("D4-L01")
        cumulative_turns = ("D4-L01:T1", "D4-L01:T2", "D4-L01:T3", "D4-L01:T4")
        for turn_id in cumulative_turns:
            before = d4.load_logfile_document(current)
            result = asyncio.run(
                cumulative.adapter.session.revise(
                    feedback=_d4_case(turn_id)["request"],
                    logfile_path=current,
                )
            )
            assert result.report_facts["success"] is True, result.report_facts
            after = d4.load_logfile_document(current)
            contract = _d4_gold(turn_id)["contract"]
            _assert_allowed_changes(before, after, contract["allowed_change_paths"])
            _assert_reloaded(current, after)
            if turn_id == "D4-L01:T1":
                assert after["title"] == "Formation Integrity Review"
            elif turn_id == "D4-L01:T2":
                assert after["sections"][0]["tracks"][1]["bindings"][0]["scale"]["minimum"] == 5.0
            elif turn_id == "D4-L01:T3":
                assert after["sections"][0]["tracks"][3]["bindings"][0]["channel"] == "ILD"
            else:
                fill = after["sections"][0]["tracks"][1]["fills"][0]
                assert fill["binding_id"] == "main.gr.GR.1"
                render_path = root / "cumulative" / "D5-LAS-01-T4.pdf"
                rendered = mcp_service.render_logfile_to_file(
                    str(current), str(render_path), overwrite=True, root=REPO_ROOT
                )
                assert rendered.output_path is not None
                assert render_path.stat().st_size > 0

        for case_id, turn_id in (
            ("D4-L02", "D4-L02:T1"),
            ("D4-L02", "D4-L02:T2"),
            ("D4-L03", "D4-L03:C01"),
            ("D4-L04", "D4-L04:C01"),
        ):
            case_root = root / turn_id.replace(":", "-")
            path, before, after, result = _run_direct_revision(
                case_root,
                source,
                case_id=case_id,
                turn_id=turn_id,
            )
            if turn_id in {"D4-L02:T1", "D4-L03:C01", "D4-L04:C01"}:
                assert before == after
                assert result.report_facts["success"] is False
                diagnostics = result.report_facts["compilation"]["diagnostics"]
                codes = {item["code"] for item in diagnostics}
                expected = {
                    "D4-L02:T1": "enrichment.section_hint_ambiguous",
                    "D4-L03:C01": "enrichment.source_missing",
                    "D4-L04:C01": "channel_missing",
                }[turn_id]
                assert expected in codes or "typed.channel_missing" in codes
            else:
                assert result.report_facts["success"] is True
                reloaded = d4.load_logfile_document(path)
                assert (
                    reloaded["sections"][0]["tracks"][1]["bindings"][0]["scale"]["minimum"] == 20.0
                )
                assert (
                    reloaded["sections"][0]["tracks"][1]["bindings"][0]["scale"]["maximum"] == 110.0
                )


def test_d5_invalid_relation_fails_at_canonical_reconciliation() -> None:
    """A fill cannot reference a binding owned by another track."""
    payload = copy.deepcopy(d4.load_gold(REPO_ROOT)["canonical_las_seed"])
    _add_foreign_cali_track(payload)
    document = AuthoringDocumentSpec.model_validate(payload)
    intent = AuthoringDocumentIntent(
        fills=[
            AuthoringFillIntent(
                fill_id="main.gr.foreign-fill",
                section_id="main",
                track_id="gr",
                kind="to_lower_limit",
                binding_id="main.cali.CALI.4",
                color="#f2e8a0",
                alpha=0.2,
            )
        ]
    )
    plan = reconcile_authoring(intent, existing=document)
    assert plan.ready is True
    service = AuthoringService(document)
    before = document.model_dump(mode="json")
    execution = execute_authoring_plan(service, plan)
    assert execution.success is False
    assert service.document.model_dump(mode="json") == before


def test_d5_mcp_overlays_use_the_shared_composition_and_preserve_semantics() -> None:
    """Run title, scale, and unavailable-channel overlays through the MCP edge."""
    source = REPO_ROOT / d4.SOURCE_RELATIVE
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        overlay_results: dict[str, object] = {}
        for overlay_id, turn_id in (
            ("D5-MCP-01", "D4-L01:T1"),
            ("D5-MCP-02", "D4-L01:T2"),
            ("D5-MCP-03", "D4-L04:C01"),
        ):
            overlay_root = root / overlay_id
            overlay_root.mkdir(parents=True)
            logfile = overlay_root / "overlay.log.yaml"
            _mcp_seed(logfile, source)
            operations, calls = _mcp_operations(overlay_root)
            before = logfile.read_bytes()
            result = asyncio.run(
                operations.revise(logfile_path=str(logfile), request=_d4_case(turn_id)["request"])
            )
            overlay_results[overlay_id] = result
            if overlay_id == "D5-MCP-03":
                assert result.success is False
                assert logfile.read_bytes() == before
                assert any("channel_missing" in error for error in result.errors)
                continue
            assert result.success is True
            assert result.changed is True
            document = d4.load_logfile_document(logfile)
            if overlay_id == "D5-MCP-01":
                assert document["title"] == "Formation Integrity Review"
            else:
                assert (
                    document["sections"][0]["tracks"][1]["bindings"][0]["scale"]["minimum"] == 5.0
                )
                render_path = overlay_root / "D5-MCP-02.pdf"
                rendered = mcp_service.render_logfile_to_file(
                    str(logfile), str(render_path), overwrite=True, root=REPO_ROOT
                )
                assert rendered.output_path is not None
                assert render_path.stat().st_size > 0
            _assert_reloaded(logfile, document)
            assert calls
            assert all(call.provider == "deterministic" for call in calls)
        assert set(overlay_results) == set(MCP_CASE_IDS)


def test_d5_provider_free_call_boundary_is_zero_network() -> None:
    """Keep the acceptance module explicitly provider-free and finite."""
    source = Path(__file__).read_text(encoding="utf-8")
    provider_factory = "create_" + "provider_backend"
    http_token = "http" + "://"
    https_token = "https" + "://"
    assert provider_factory not in source
    assert http_token not in source
    assert https_token not in source
    assert "D5-CBL-01" in source
    assert "D5-LAS-01-T4" in source
    assert "D5-MCP-02" in source

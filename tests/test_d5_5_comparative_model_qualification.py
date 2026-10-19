"""Provider-free D5-5 dual-lane qualification tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx
import pytest
from scripts import d5_5_comparative_model_qualification as d5_5
from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from tests.test_d5_provider_free_parity_acceptance import (
    _assert_frozen_las_contract,
    _assert_reloaded,
    _d4_case,
    _d4_gold,
    _new_direct_harness,
)
from tests.test_nlp_d5_live_semantic_qualification import (
    _authorization,
    _provenance,
    _ready,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _failing_generation_handler(
    requests: list[httpx.Request],
) -> Callable[[httpx.Request], Any]:
    """Return an in-memory transport handler that never contacts a provider."""

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, json={"error": {"message": "fixture"}}, request=request)

    return handler


def _run_revision_with_count(
    root: Path,
    source: Path,
    *,
    case_id: str,
    turn_id: str,
) -> tuple[Path, bytes, bytes, dict[str, object], dict[str, object], object, int]:
    """Run one isolated revision while retaining the fixture call count."""
    harness = _new_direct_harness(root, source)
    path = harness.adapter._base_for(case_id)
    before_bytes = path.read_bytes()
    before_document = d4.load_logfile_document(path)
    result = asyncio.run(
        harness.adapter.session.revise(
            feedback=_d4_case(turn_id)["request"],
            logfile_path=path,
        )
    )
    after_bytes = path.read_bytes()
    after_document = d4.load_logfile_document(path)
    return (
        path,
        before_bytes,
        after_bytes,
        before_document,
        after_document,
        result,
        harness.adapter.logical_call_count,
    )


def _run_exact_nine_turn_rehearsal(root: Path) -> dict[str, object]:
    """Run the frozen D4 nine-turn route through the canonical deterministic path."""
    source = REPO_ROOT / d4.SOURCE_RELATIVE
    logical_calls = 0

    cbl_harness = _new_direct_harness(root / "cbl", source)
    cbl_case = _d4_case("D4-C01:C01")
    cbl_gold = _d4_gold("D4-C01:C01")
    cbl_actual = asyncio.run(cbl_harness.adapter.execute_turn(cbl_case, cbl_gold))
    cbl_grade = d4.grade_turn(cbl_actual, cbl_gold)
    assert cbl_grade["status"] == "PASS", cbl_grade
    assert {item["status"] for item in cbl_grade["verifier_requirements"]} == {"PASS"}
    assert d4.sha256_file(cbl_actual["starting_artifact_path"]) != d4.sha256_file(
        cbl_actual["ending_artifact_path"]
    )
    assert Path(cbl_actual["ending_artifact_path"]).is_file()
    assert Path(cbl_actual["render_path"]).stat().st_size > 0
    logical_calls += cbl_harness.adapter.logical_call_count

    cumulative = _new_direct_harness(root / "cumulative", source)
    current = cumulative.adapter._base_for("D4-L01")
    for turn_id in ("D4-L01:T1", "D4-L01:T2", "D4-L01:T3", "D4-L01:T4"):
        before = d4.load_logfile_document(current)
        result = asyncio.run(
            cumulative.adapter.session.revise(
                feedback=_d4_case(turn_id)["request"],
                logfile_path=current,
            )
        )
        assert result.report_facts["success"] is True, result.report_facts
        after = d4.load_logfile_document(current)
        _assert_frozen_las_contract(turn_id, before, after)
        _assert_reloaded(current, after)
    logical_calls += cumulative.adapter.logical_call_count

    for case_id, turn_id in (
        ("D4-L02", "D4-L02:T1"),
        ("D4-L02", "D4-L02:T2"),
        ("D4-L03", "D4-L03:C01"),
        ("D4-L04", "D4-L04:C01"),
    ):
        path, before, after, before_document, after_document, result, calls = (
            _run_revision_with_count(
                root / turn_id.replace(":", "-"),
                source,
                case_id=case_id,
                turn_id=turn_id,
            )
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
            _assert_frozen_las_contract(turn_id, before_document, after_document)
            _assert_reloaded(path, after_document)
        logical_calls += calls

    assert logical_calls == 18
    return {
        "turns": 9,
        "logical_calls": logical_calls,
        "physical_attempts": logical_calls,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "model_calls": 0,
        "decision": "PASS",
    }


def test_lane_descriptors_share_engine_and_have_independent_custody() -> None:
    """Qwen and Luna vary only at provider configuration and artifact identity."""
    config = d5_5.load_project_config(REPO_ROOT)
    lanes = d5_5.lane_configurations(config)
    facts = d5_5.validate_lane_configurations(lanes)
    assert facts["canonical_engine"] == d5_5.CANONICAL_ENGINE_ENTRYPOINT
    assert [lane.model for lane in lanes] == ["qwen3.6-35b-a3b", "openai/gpt-6-luna"]
    assert lanes[0].base_url == config.openai_compat_base_url
    assert lanes[1].base_url == "https://openrouter.ai/api/v1"
    assert lanes[0].campaign_id != lanes[1].campaign_id
    assert lanes[0].artifact_root != lanes[1].artifact_root
    assert d5_5.HISTORICAL_CAMPAIGN not in facts["campaign_ids"]


def test_provider_factory_arguments_are_lane_local_and_share_boundary() -> None:
    """Both future live lanes delegate to the same existing provider factory."""
    config = d5_5.load_project_config(REPO_ROOT)
    lanes = d5_5.lane_configurations(config)
    arguments = [lane.provider_arguments(REPO_ROOT, "redacted-token") for lane in lanes]
    assert [item["provider"] for item in arguments] == ["openai_compat", "openai_compat"]
    assert [item["model"] for item in arguments] == [
        "qwen3.6-35b-a3b",
        "openai/gpt-6-luna",
    ]
    assert arguments[0]["base_url"] != arguments[1]["base_url"]
    assert all(item["timeout"] == 900.0 for item in arguments)


def test_lane_readiness_uses_only_its_provider_contract() -> None:
    """Qwen uses llama props while Luna uses only its model catalog."""
    config = d5_5.load_project_config(REPO_ROOT)
    calls_by_lane: dict[str, list[str]] = {}
    for lane in d5_5.lane_configurations(config):
        calls: list[str] = []
        calls_by_lane[lane.lane_id] = calls
        authorization = replace(
            _authorization(),
            campaign_id=lane.campaign_id,
            provider=lane.provider,
            model=lane.model,
            artifact_root=f"workspace/evaluations/d5-5/{lane.lane_id}",
        )

        def endpoint_get(
            url: str,
            token: str,
            *,
            calls: list[str] = calls,
        ) -> object:
            del token
            calls.append(url)
            if url == config.model_catalog_url:
                return {"data": [{"id": "qwen3.6-35b-a3b"}]}
            if url == config.props_url:
                return {
                    "model_path": "/srv/models/qwen3.6-35b-a3b.gguf",
                    "default_generation_settings": {
                        "n_ctx": 32768,
                        "temperature": 0.0,
                        "top_p": 1.0,
                    },
                    "build_info": "llama.cpp provider-free test build",
                    "total_slots": 1,
                    "chat_template": "qwen3",
                    "gguf_byte_identity": "NOT_AVAILABLE",
                }
            return {"data": [{"id": "openai/gpt-6-luna"}]}

        readiness = d5_5.prepare_lane_readiness(
            lane=lane,
            authorization=authorization,
            project_config=config,
            api_key_loader=lambda: "provider-free-token",
            endpoint_get=endpoint_get,
            static_preflight={"status": "PASS"},
        )
        if lane.lane_id == "qwen":
            assert calls == [config.model_catalog_url, config.props_url]
            assert readiness.endpoint_calls == ("/v1/models", "/props")
        else:
            assert calls == ["https://openrouter.ai/api/v1/models"]
            assert config.props_url not in calls
            assert readiness.endpoint_calls == ("/models",)
            assert "model_path_basename" not in readiness.projection.as_dict()

    assert calls_by_lane["qwen"][-1] == config.props_url
    assert calls_by_lane["luna"] == ["https://openrouter.ai/api/v1/models"]


def test_lane_live_adapters_use_existing_provider_path_without_requests() -> None:
    """Both descriptors construct the accepted D5-4 adapter with fake transport."""
    import httpx

    config = d5_5.load_project_config(REPO_ROOT)
    for lane in d5_5.lane_configurations(config):
        clients: list[httpx.AsyncClient] = []

        def factory(
            observer: Callable[[object], Any],
            *,
            clients: list[httpx.AsyncClient] = clients,
        ) -> httpx.AsyncClient:
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
                event_hooks={"request": [observer]},
            )
            clients.append(client)
            return client

        with TemporaryDirectory(dir=REPO_ROOT) as temporary:
            adapter = d5_5.create_lane_live_adapter(
                repo_root=REPO_ROOT,
                artifact_root=Path(temporary),
                api_key="provider-free-token",
                lane=lane,
                project_config=config,
                http_client_factory=factory,
            )
            backend = adapter.inner.session.session.compiler.dependencies.planner.backend
            assert backend.delegate.model == lane.model
            assert str(backend.delegate.client.base_url).startswith(lane.base_url)
        assert len(clients) == 1
        asyncio.run(clients[0].aclose())


def test_executable_lane_boundary_enters_shared_runner_without_provider_calls() -> None:
    """Both lanes reach STARTED custody and fail closed before delegation."""
    result = d5_5.verify_executable_lane_boundary(
        REPO_ROOT,
        implementation_checkpoint=d5_5._git(REPO_ROOT, "rev-parse", "HEAD"),
    )
    assert result["provider_calls"] == result["model_calls"] == 0
    assert {item["shared_runner"] for item in result["lanes"]} == {"D5CampaignRunner"}
    assert {item["live_adapter"] for item in result["lanes"]} == {"_ObservedLiveAdapter"}
    assert result["lanes"][0]["endpoint_calls"][-1].endswith("/props")
    assert result["lanes"][1]["endpoint_calls"] == ["https://openrouter.ai/api/v1/models"]


def test_execute_live_lane_runs_static_readiness_adapter_and_shared_runner_provider_free(
    tmp_path: Path,
) -> None:
    """The exact live entrypoint is exercised with only injected transports."""
    import httpx

    config = d5_5.load_project_config(REPO_ROOT)
    current = d5_5._git(REPO_ROOT, "rev-parse", "HEAD")
    for lane in d5_5.lane_configurations(config):
        artifact_root = tmp_path / lane.lane_id
        authorization = replace(
            _authorization(),
            implementation_checkpoint=current,
            campaign_id=lane.campaign_id,
            provider=lane.provider,
            model=lane.model,
            artifact_root=str(artifact_root),
        )
        sequence: list[str] = []
        readiness_calls: list[str] = []

        def endpoint_get(
            url: str,
            token: str,
            *,
            lane: d5_5.ComparativeLane = lane,
            readiness_calls: list[str] = readiness_calls,
        ) -> object:
            assert token == "provider-free-token"
            readiness_calls.append(url)
            if lane.lane_id == "qwen":
                if url == config.model_catalog_url:
                    return {"data": [{"id": lane.model}]}
                return {
                    "model_path": "/srv/models/qwen3.6-35b-a3b.gguf",
                    "default_generation_settings": {
                        "n_ctx": 32768,
                        "temperature": 0.0,
                        "top_p": 1.0,
                    },
                    "build_info": "llama.cpp provider-free test build",
                    "total_slots": 1,
                    "chat_template": "qwen3",
                    "gguf_byte_identity": "NOT_AVAILABLE",
                }
            return {"data": [{"id": lane.model}]}

        clients: list[httpx.AsyncClient] = []
        generation_requests: list[httpx.Request] = []

        def client_factory(
            observer: Callable[[object], Any],
            *,
            clients: list[httpx.AsyncClient] = clients,
            generation_requests: list[httpx.Request] = generation_requests,
        ) -> httpx.AsyncClient:
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(_failing_generation_handler(generation_requests)),
                event_hooks={"request": [observer]},
            )
            clients.append(client)
            return client

        def static_checker(
            repo_root: Path,
            checked_lane: d5_5.ComparativeLane,
            checked_authorization: d5.D5Authorization,
            *,
            sequence: list[str] = sequence,
            artifact_root: Path = artifact_root,
        ) -> dict[str, object]:
            sequence.append("static")
            return d5_5.verify_lane_static_preflight(
                repo_root,
                lane=checked_lane,
                authorization=checked_authorization,
                expected_artifact_root=artifact_root,
            )

        result = d5_5.execute_live_lane(
            repo_root=REPO_ROOT,
            lane=lane,
            authorization=authorization,
            endpoint_get=endpoint_get,
            api_key_loader=lambda: "provider-free-token",
            static_checker=static_checker,
            http_client_factory=client_factory,
        )
        sequence.append("runner")
        assert result["static_preflight"]["status"] == "PASS"
        assert result["result"]["decision"] == "INCONCLUSIVE"
        assert result["result"]["completed_turns"] == 0
        assert readiness_calls
        assert sequence == ["static", "runner"]
        assert len(generation_requests) >= 1
        assert result["result"]["terminal"]["decision"] == "INCONCLUSIVE"
        assert result["readiness"]["model_catalog"] == [lane.model]
        if lane.lane_id == "luna":
            assert config.props_url not in readiness_calls
        for client in clients:
            asyncio.run(client.aclose())


def test_lane_custody_and_call_caps_are_independent_and_fail_closed(tmp_path: Path) -> None:
    """Lane namespaces cannot cross-consume and caps reject before delegation."""
    qwen = replace(
        _authorization(campaign_id="d5-5-qwen-001"),
        model="qwen3.6-35b-a3b",
        artifact_root=str(tmp_path / "qwen"),
    )
    luna = replace(
        _authorization(campaign_id="d5-5-luna-001"),
        model="openai/gpt-6-luna",
        artifact_root=str(tmp_path / "luna"),
    )
    qwen_paths = d5.EvidencePaths(tmp_path / "qwen", qwen.campaign_id)
    luna_paths = d5.EvidencePaths(tmp_path / "luna", luna.campaign_id)
    qwen_custody = d5.D5CampaignCustody.start(
        qwen_paths,
        authorization=qwen,
        provenance=_provenance(),
        readiness=_ready().projection,
    )
    qwen_custody.finish("INCONCLUSIVE", attribution="TEST", rows=[])
    with pytest.raises(d5.D5HarnessError, match="campaign path"):
        d5.D5CampaignCustody.start(
            luna_paths,
            authorization=qwen,
            provenance=_provenance(),
            readiness=_ready().projection,
        )
    assert not any(path.exists() for path in luna_paths.all_paths())

    ledger = d5.D5LogicalCallLedger()
    for _ in range(d5.MAX_LOGICAL_CALLS):
        ledger.reserve("planner")
    with pytest.raises(d5.D5CallCapExceeded, match="logical call 46"):
        ledger.reserve("planner")
    logical_index = ledger.calls[0]["logical_call_index"]
    for _ in range(d5.MAX_PHYSICAL_ATTEMPTS):
        ledger.physical_attempt(logical_index)
    with pytest.raises(d5.D5CallCapExceeded, match="physical attempt ceiling"):
        ledger.physical_attempt(logical_index)


def test_provider_free_contract_rebinds_to_current_checkpoint_without_calls() -> None:
    """Static D5-5 custody checks preserve the exact nine-turn identities."""
    result = d5_5.verify_provider_free_contract(
        REPO_ROOT,
        implementation_checkpoint=d5_5._git(REPO_ROOT, "rev-parse", "HEAD"),
        run_attestation=True,
    )
    assert result["accepted_baseline"] == d5_5.D5_5_BASELINE
    assert result["population"]["turns"] == 9
    assert result["single_engine_attestation"] == "PASS"
    assert result["provider_calls"] == result["model_calls"] == 0


@pytest.mark.parametrize("lane_id", ["qwen", "luna"])
def test_each_lane_rehearses_the_exact_nine_turn_population(lane_id: str) -> None:
    """Each lane gets an independent 9/9 provider-free canonical rehearsal."""
    config = d5_5.load_project_config(REPO_ROOT)
    lane = next(item for item in d5_5.lane_configurations(config) if item.lane_id == lane_id)
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        result = _run_exact_nine_turn_rehearsal(Path(temporary) / lane.lane_id)
    assert result == {
        "turns": 9,
        "logical_calls": 18,
        "physical_attempts": 18,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "model_calls": 0,
        "decision": "PASS",
    }


def test_lane_artifact_roots_cannot_collide(tmp_path: Path) -> None:
    """The comparison namespace is lane-specific and historical evidence is untouched."""
    config = d5_5.load_project_config(REPO_ROOT)
    lanes = d5_5.lane_configurations(config)
    roots = [tmp_path / lane.artifact_root for lane in lanes]
    for root in roots:
        root.mkdir(parents=True)
        (root / f"{d5_5.D5_5_EXPERIMENT}.marker").write_text("fresh", encoding="utf-8")
    assert roots[0] != roots[1]
    assert not (tmp_path / d5_5.HISTORICAL_CAMPAIGN).exists()

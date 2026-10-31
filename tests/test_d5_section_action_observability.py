"""Provider-free tests for explicitly authorized section-action custody."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator, Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from pydantic import BaseModel, TypeAdapter
from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from tests.test_code_mode_planner import _consolidated_duplicate_scope_plan
from tests.test_nlp_d5_live_semantic_qualification import (
    PROJECT_CONFIG,
    REPO_ROOT,
    _authorization,
    _authorization_payload,
    _props,
    _ready,
)
from tests.test_section_work_contract import (
    _context,
    _contract,
    _smoke_request,
    _valid_reconstruct_payload,
)

from wellplot.agent.code_mode import typed_section_worker as section_worker
from wellplot.agent.code_mode.enrichment import EnrichedSemanticContext, ReportContext
from wellplot.agent.code_mode.obligations import (
    ValidationIssue,
    ValidationIssueSet,
    compile_request_contract,
)
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.semantic_actions import SectionSemanticAction
from wellplot.agent.code_mode.typed_section_worker import (
    CanonicalSectionWorker,
    SectionActionEvidenceError,
)
from wellplot.agent.code_mode.worker_contracts import (
    CanonicalWorkerResult,
    SectionWorkContractError,
)
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.model.authoring import AuthoringDocumentSpec


@pytest.fixture(autouse=True)
def _private_umask() -> Iterator[None]:
    """Exercise private custody without changing the surrounding process permanently."""
    previous = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous)


def _custody(tmp_path: Path, mode: str) -> d5.D5SmokeCustody:
    authorization = replace(
        _authorization(campaign_id="observation", artifact_root=str(tmp_path / "evidence")),
        section_action_capture_mode=mode,
    )
    paths = d5.EvidencePaths(tmp_path / "evidence", authorization.campaign_id)
    custody = d5.D5SmokeCustody.start(
        paths,
        authorization=authorization,
        static_preflight={"status": "PASS"},
        readiness=_ready().projection,
        endpoint_calls=2,
        smoke_kind=d5.SMOKE_BINDING_KIND,
    )
    custody.record_binding_call_started(
        {
            "index": 1,
            "generation_role": "section_worker",
            "provider": d5.EXPECTED_PROVIDER,
            "model": d5.EXPECTED_MODEL,
        }
    )
    return custody


def _observe(
    custody: d5.D5SmokeCustody,
    payload: dict,
    *,
    index: int = 1,
    attempt: int = 1,
    task_index: int = 0,
) -> SectionWorkContractError | None:
    """Send one synthetic typed action through the actual observation boundary."""
    action = TypeAdapter(SectionSemanticAction).validate_python(payload)
    worker = CanonicalSectionWorker(
        backend=object(),
        action_observer=custody.record_section_action,
        action_capture_mode=custody.authorization.section_action_capture_mode,
    )
    return worker._validate_observed_action(
        action,
        _contract(_smoke_request()),
        task_index=task_index,
        attempt=attempt,
        logical_call_index=index,
    )


def _rows(custody: d5.D5SmokeCustody) -> list[dict]:
    return [json.loads(line) for line in custody.paths.section_actions.read_text().splitlines()]


def test_capture_mode_requires_explicit_valid_authorization() -> None:
    """Full capture is opt-in and invalid authorization values fail closed."""
    payload = _authorization_payload()
    assert d5.D5Authorization.from_mapping(payload).section_action_capture_mode == "off"
    payload["section_action_capture_mode"] = "validated_dto"
    assert d5.D5Authorization.from_mapping(payload).section_action_capture_mode == "validated_dto"
    payload["section_action_capture_mode"] = "invalid"
    with pytest.raises(d5.D5StaticPreflightError):
        d5.D5Authorization.from_mapping(payload)


@pytest.mark.parametrize("mode", ["diagnostics", "validated_dto"])
def test_generic_ready_smoke_cannot_claim_section_capture(tmp_path: Path, mode: str) -> None:
    """The READY-only smoke cannot substitute for an authorized section capture."""
    root = tmp_path / "ready-only"
    authorization = replace(
        _authorization(campaign_id="ready-only", artifact_root=str(root)),
        section_action_capture_mode=mode,
    )
    with pytest.raises(d5.D5StaticPreflightError, match="requires binding-smoke mode"):
        d5.execute_live_smoke(repo_root=REPO_ROOT, authorization=authorization, artifact_root=root)
    assert not root.exists()


def test_private_campaign_preflight_rejects_unsafe_permissions(tmp_path: Path) -> None:
    """Full capture refuses an unsafe existing file or process umask."""
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    candidate = root / "authorization.json"
    candidate.write_text("{}")
    candidate.chmod(0o644)
    with pytest.raises(d5.D5HarnessError, match="pre-existing campaign entry"):
        d5._prepare_private_campaign_root(root)
    candidate.chmod(0o600)
    previous = os.umask(0o022)
    try:
        with pytest.raises(d5.D5HarnessError, match="umask 077"):
            d5._prepare_private_campaign_root(root)
    finally:
        os.umask(previous)


def test_full_capture_location_requires_ignored_evaluation_workspace(tmp_path: Path) -> None:
    """Full DTO custody cannot be placed outside the ignored local evaluation root."""
    d5._validate_section_capture_location(REPO_ROOT, REPO_ROOT / "workspace/evaluations/probe")
    with pytest.raises(d5.D5StaticPreflightError, match="workspace/evaluations"):
        d5._validate_section_capture_location(REPO_ROOT, tmp_path / "elsewhere")


def test_complete_capture_and_terminal_integrity(tmp_path: Path) -> None:
    """A complete DTO is private, correlated, hashed, and sealed."""
    custody = _custody(tmp_path, "validated_dto")
    payload = _valid_reconstruct_payload()
    assert _observe(custody, payload) is None
    rows = _rows(custody)
    assert [row["event"] for row in rows] == [
        "SECTION_ACTION_SCHEMA_VALIDATED",
        "SECTION_ACTION_CONTRACT_RESULT",
        "SECTION_ACTION_VALIDATED",
    ]
    first = rows[0]
    dto = custody.paths.root / first["dto_path"]
    assert first["capture_state"] == "complete"
    assert first["logical_call_index"] == 1
    assert first["contract_outcome"] == "NOT_EVALUATED"
    assert rows[1]["contract_outcome"] == "PASS"
    assert json.loads(dto.read_text()) == payload
    assert hashlib.sha256(dto.read_bytes()).hexdigest() == first["dto_sha256"]
    assert stat.S_IMODE(dto.stat().st_mode) == 0o600
    assert stat.S_IMODE(dto.parent.stat().st_mode) == 0o700
    terminal = custody.finish("SMOKE_PASS")
    assert terminal["observability_artifacts"][first["dto_path"]] == first["dto_sha256"]
    assert d5.verify_smoke_observability(custody.paths)["authorized_deleted_dtos"] == 0


@pytest.mark.parametrize("mode", ["diagnostics", "validated_dto"])
@pytest.mark.parametrize("case", ["missing_track", "unexpected_track", "binding_handle"])
def test_rejected_action_is_observed_with_typed_mismatch(
    tmp_path: Path, mode: str, case: str
) -> None:
    """Both mismatch classes preserve bounded evidence before rejection."""
    custody = _custody(tmp_path, mode)
    payload = deepcopy(_valid_reconstruct_payload())
    tracks = payload["section"]["tracks"]
    if case == "missing_track":
        tracks.pop()
    elif case == "unexpected_track":
        tracks[1]["semantic_id"] = "unexpected-track"
    else:
        tracks[1]["bindings"][0]["semantic_id"] = "unexpected-binding"
    error = _observe(custody, payload)
    assert error is not None and error.code == "worker_contract_incomplete"
    rows = _rows(custody)
    assert len(rows) == 2
    assert rows[1]["contract_outcome"] == "FAIL"
    expected = (
        "BINDING_HANDLE_SET_MISMATCH" if case == "binding_handle" else "TRACK_HANDLE_SET_MISMATCH"
    )
    assert rows[1]["mismatch"]["classification"] == expected
    assert "unexpected-track" not in json.dumps(rows)
    assert "unexpected-binding" not in json.dumps(rows)
    if case != "binding_handle":
        assert rows[1]["mismatch"]["binding_validation"] == "NOT_EVALUATED"
    if mode == "diagnostics":
        assert not custody.paths.validated_section_dtos.exists()
        assert "action" not in rows[0]
    else:
        assert json.loads((custody.paths.root / rows[0]["dto_path"]).read_text()) == payload


@pytest.mark.parametrize("case", ["secret", "path", "windows_path", "control", "oversize"])
def test_unsafe_or_oversized_capture_fails_without_partial_dto(tmp_path: Path, case: str) -> None:
    """Strong screening matches and oversize DTOs never persist partial content."""
    custody = _custody(tmp_path, "validated_dto")
    payload = deepcopy(_valid_reconstruct_payload())
    text = {
        "secret": "Bearer private-secret",
        "path": "/private/secret.las",
        "windows_path": "C:\\private\\secret.las",
        "control": "bad\u0000value",
        "oversize": "x" * 70000,
    }[case]
    payload["section"]["tracks"][0]["title"] = text
    with pytest.raises(SectionActionEvidenceError):
        _observe(custody, payload)
    rows = _rows(custody)
    assert rows[0]["capture_state"] == "INCOMPLETE"
    assert rows[0]["capture_failure"] == (
        "DTO_OVERSIZE" if case == "oversize" else "DTO_SCREENING_REJECTED"
    )
    assert text not in custody.paths.section_actions.read_text()
    assert not custody.paths.validated_section_dtos.exists()


def test_event_limit_includes_authorization_and_retention_metadata(tmp_path: Path) -> None:
    """A DTO below the byte cap is rejected if its complete event would exceed it."""
    custody = _custody(tmp_path, "validated_dto")
    payload = deepcopy(_valid_reconstruct_payload())
    payload["section"]["tracks"][0]["title"] = "x"
    action = TypeAdapter(SectionSemanticAction).validate_python(payload)
    base = json.dumps(
        action.model_dump(mode="json", exclude_unset=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    payload["section"]["tracks"][0]["title"] = "x" * (
        d5.MAX_SECTION_ACTION_EVIDENCE_BYTES - len(base) - 100
    )
    with pytest.raises(SectionActionEvidenceError):
        _observe(custody, payload)
    row = _rows(custody)[0]
    assert row["dto_size_bytes"] < d5.MAX_SECTION_ACTION_EVIDENCE_BYTES
    assert row["capture_failure"] == "DTO_OVERSIZE"
    assert not custody.paths.validated_section_dtos.exists()


def test_disabled_mode_preserves_legacy_event() -> None:
    """Disabled capture retains the pre-existing successful-observer behavior."""
    events: list[dict] = []
    worker = CanonicalSectionWorker(backend=object(), action_observer=events.append)
    action = TypeAdapter(SectionSemanticAction).validate_python(_valid_reconstruct_payload())
    assert (
        worker._validate_observed_action(
            action, _contract(_smoke_request()), task_index=0, attempt=1, logical_call_index=None
        )
        is None
    )
    assert [event["event"] for event in events] == ["SECTION_ACTION_VALIDATED"]
    assert events[0]["action"] == _valid_reconstruct_payload()


def test_capture_failure_is_not_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An authorized DTO write error propagates as an evidence failure."""
    custody = _custody(tmp_path, "validated_dto")

    def fail_write(*_args: object) -> None:
        raise OSError("private exception detail")

    monkeypatch.setattr(d5, "_write_private_exclusive", fail_write)
    with pytest.raises(SectionActionEvidenceError):
        _observe(custody, _valid_reconstruct_payload())


def test_metadata_screen_rejects_absolute_paths(tmp_path: Path) -> None:
    """Even an unexpectedly unsafe diagnostic value is not persisted."""
    custody = _custody(tmp_path, "diagnostics")
    event = {
        "event": "SECTION_ACTION_CONTRACT_RESULT",
        "event_version": "wellplot.section-action-observation.v1",
        "worker_role": "section_worker",
        "task_index": 0,
        "attempt": 1,
        "logical_call_index": 1,
        "response_schema": "ReconstructSectionAction",
        "dto_sha256": "a" * 64,
        "dto_size_bytes": 10,
        "contract_outcome": "FAIL",
        "mismatch": {"unsafe": "/private/secret.las"},
    }
    with pytest.raises(d5.D5HarnessError, match="metadata rejected"):
        custody.record_section_action(event)
    assert not custody.paths.section_actions.exists()


def test_metadata_write_failure_removes_new_dto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DTO created before metadata failure is removed rather than orphaned."""
    custody = _custody(tmp_path, "validated_dto")

    def fail_metadata(*_args: object, **_kwargs: object) -> None:
        raise OSError("private exception detail")

    monkeypatch.setattr(d5.D5SmokeCustody, "_append_section_observation", fail_metadata)
    with pytest.raises(SectionActionEvidenceError):
        _observe(custody, _valid_reconstruct_payload())
    assert list(custody.paths.validated_section_dtos.iterdir()) == []


def test_smoke_verifier_rejects_dto_tampering(tmp_path: Path) -> None:
    """Modified DTO bytes do not match sealed custody."""
    custody = _custody(tmp_path, "validated_dto")
    assert _observe(custody, _valid_reconstruct_payload()) is None
    first = _rows(custody)[0]
    custody.finish("SMOKE_PASS")
    (custody.paths.root / first["dto_path"]).write_text("{}")
    with pytest.raises(d5.D5HarnessError, match="digest mismatch"):
        d5.verify_smoke_observability(custody.paths)


def test_smoke_verifier_rejects_permission_drift(tmp_path: Path) -> None:
    """A retained DTO cannot silently become readable by other users."""
    custody = _custody(tmp_path, "validated_dto")
    assert _observe(custody, _valid_reconstruct_payload()) is None
    first = _rows(custody)[0]
    custody.finish("SMOKE_PASS")
    (custody.paths.root / first["dto_path"]).chmod(0o644)
    with pytest.raises(d5.D5HarnessError, match="not private"):
        d5.verify_smoke_observability(custody.paths)


def test_retention_requires_expiry_and_keeps_sealed_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deletion requires expiry and retains the original digest and metadata."""
    custody = _custody(tmp_path, "validated_dto")
    assert _observe(custody, _valid_reconstruct_payload()) is None
    first = _rows(custody)[0]
    custody.finish("SMOKE_PASS")
    with pytest.raises(d5.D5HarnessError, match="not expired"):
        d5.delete_expired_validated_dtos(custody.paths, deletion_authorization_id="DELETE-001")
    expiry = datetime.fromisoformat(first["retention_until_utc"])
    monkeypatch.setattr(d5, "_utc_now", lambda: expiry + timedelta(seconds=1))
    receipt = d5.delete_expired_validated_dtos(
        custody.paths,
        deletion_authorization_id="DELETE-001",
    )
    assert receipt["authorized_files"][first["dto_path"]] == first["dto_sha256"]
    assert not (custody.paths.root / first["dto_path"]).exists()
    assert _rows(custody)[0]["dto_sha256"] == first["dto_sha256"]
    assert d5.verify_smoke_observability(custody.paths)["authorized_deleted_dtos"] == 1


def test_verifier_rejects_forged_early_deletion_receipt(tmp_path: Path) -> None:
    """A deletion receipt cannot authorize deletion before the recorded deadline."""
    custody = _custody(tmp_path, "validated_dto")
    assert _observe(custody, _valid_reconstruct_payload()) is None
    first = _rows(custody)[0]
    custody.finish("SMOKE_PASS")
    expiry = datetime.fromisoformat(first["retention_until_utc"])
    receipt = {
        "campaign_id": custody.paths.campaign_id,
        "deletion_authorization_id": "DELETE-001",
        "terminal_sha256": d5._sha256_file(custody.paths.terminal),
        "authorized_at_utc": (expiry - timedelta(seconds=1)).isoformat(),
        "authorized_files": {first["dto_path"]: first["dto_sha256"]},
    }
    custody.paths.dto_deletion_receipt.write_text(json.dumps(receipt))
    (custody.paths.root / first["dto_path"]).unlink()
    with pytest.raises(d5.D5HarnessError, match="predates retention expiry"):
        d5.verify_smoke_observability(custody.paths)


def test_verifier_rejects_unsealed_extra_dto(tmp_path: Path) -> None:
    """Unsealed additions to the private DTO directory are rejected."""
    custody = _custody(tmp_path, "validated_dto")
    assert _observe(custody, _valid_reconstruct_payload()) is None
    custody.finish("SMOKE_PASS")
    (custody.paths.validated_section_dtos / "extra.json").write_text("{}")
    with pytest.raises(d5.D5HarnessError, match="unsealed validated DTO entry"):
        d5.verify_smoke_observability(custody.paths)


@pytest.mark.parametrize("tampering", ["extra", "missing"])
def test_terminal_rejects_dto_set_drift_before_sealing(tmp_path: Path, tampering: str) -> None:
    """Missing or injected DTO files cannot be sealed as complete capture."""
    custody = _custody(tmp_path, "validated_dto")
    assert _observe(custody, _valid_reconstruct_payload()) is None
    row = _rows(custody)[0]
    if tampering == "extra":
        (custody.paths.validated_section_dtos / "task-99-call-99-attempt-1.json").write_text("{}")
    else:
        (custody.paths.root / row["dto_path"]).unlink()
    with pytest.raises(d5.D5HarnessError, match="custody set"):
        custody.finish("SMOKE_PASS")
    assert not custody.paths.terminal.exists()
    assert json.loads(custody.paths.state.read_text())["status"] == "SMOKE_STARTED"


def _compile_worker(
    payloads: list[dict],
    observer: Callable[[Mapping[str, object]], None],
    mode: Literal["off", "diagnostics", "validated_dto"],
) -> tuple[CanonicalWorkerResult, int, SectionTask]:
    """Exercise a worker using only synthetic responses and local objects."""
    compilation = compile_request_contract(_smoke_request())
    task = SectionTask(
        goal="Add the requested tracks.",
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        existing_section_hint="Main Log",
        obligations=compilation.requirements.requirements,
    )
    section = _context()
    context = EnrichedSemanticContext(
        plan=SemanticPlan(summary="Add tracks", section_tasks=(task,)),
        sections=(section,),
        report=ReportContext(),
    )
    document = AuthoringDocumentSpec.model_validate(
        {
            "name": "fixture",
            "sections": [
                {
                    "id": "main",
                    "title": "Main Log",
                    "data_source": {
                        "source_path": "/private/source/fixture.las",
                        "source_format": "las",
                    },
                    "tracks": [{"id": "depth", "kind": "normal", "title": "Depth", "width_mm": 12}],
                }
            ],
        }
    )

    class Backend:
        calls = 0

        async def generate_structured(
            self, _request: StructuredGenerationRequest, *, response_model: type[BaseModel]
        ) -> StructuredGenerationResult[BaseModel]:
            self.calls += 1
            return StructuredGenerationResult(
                value=response_model.model_validate(payloads[self.calls - 1]),
                metrics=ProviderMetrics(),
                logical_call_index=self.calls + 10,
            )

    backend = Backend()
    worker = CanonicalSectionWorker(
        backend=backend, action_observer=observer, action_capture_mode=mode
    )
    result = asyncio.run(
        worker.compile(
            task_index=0,
            context=context,
            document=document,
            authoritative_request=_smoke_request(),
            work_contract=_contract(_smoke_request(), context=section),
            timeout_seconds=5,
        )
    )
    return result, backend.calls, task


def test_worker_rejected_dto_is_observed_before_contract_failure() -> None:
    """A rejected typed action is captured before deterministic validation."""
    payload = deepcopy(_valid_reconstruct_payload())
    payload["section"]["tracks"].pop()
    events: list[dict] = []
    result, calls, _task = _compile_worker([payload], events.append, "validated_dto")
    assert not result.success
    assert result.diagnostics[0].code == "worker_contract_incomplete"
    assert result.stage_evidence.semantic_lowering == "NOT_REACHED"
    assert calls == 1
    assert [event["event"] for event in events] == [
        "SECTION_ACTION_SCHEMA_VALIDATED",
        "SECTION_ACTION_CONTRACT_RESULT",
    ]
    assert events[0]["action"] == payload
    assert events[1]["mismatch"]["classification"] == "TRACK_HANDLE_SET_MISMATCH"
    assert events[0]["logical_call_index"] == events[1]["logical_call_index"] == 11


def test_worker_capture_write_failure_stops_before_lowering() -> None:
    """A mandatory observation failure prevents lowering and further calls."""

    def fail(_event: Mapping[str, object]) -> None:
        raise OSError("private error")

    result, calls, _task = _compile_worker([_valid_reconstruct_payload()], fail, "validated_dto")
    assert not result.success
    assert result.diagnostics[0].code == "worker_evidence_integrity_failure"
    assert result.stage_evidence.semantic_lowering == "NOT_REACHED"
    assert calls == 1


def test_worker_preserves_contract_failure_when_diagnostic_write_fails() -> None:
    """A failed evidence write retains the known contract failure as secondary evidence."""
    payload = deepcopy(_valid_reconstruct_payload())
    payload["section"]["tracks"].pop()

    def observer(event: Mapping[str, object]) -> None:
        if event["event"] == "SECTION_ACTION_CONTRACT_RESULT":
            raise OSError("private error")

    result, calls, _task = _compile_worker([payload], observer, "validated_dto")
    assert not result.success
    assert [item.code for item in result.diagnostics] == [
        "worker_evidence_integrity_failure",
        "worker_contract_incomplete",
    ]
    assert result.stage_evidence.semantic_lowering == "NOT_REACHED"
    assert calls == 1


def test_concurrent_logical_call_ids_follow_their_own_results() -> None:
    """Concurrent completions keep their individual logical-call identities."""
    action_model = section_worker.ReconstructSectionAction

    class Backend:
        def __init__(self) -> None:
            self.first_started = asyncio.Event()
            self.release_first = asyncio.Event()
            self.calls = 0

        async def generate_structured(
            self, _request: StructuredGenerationRequest, *, response_model: type[BaseModel]
        ) -> StructuredGenerationResult[BaseModel]:
            self.calls += 1
            if self.calls == 1:
                self.first_started.set()
                await self.release_first.wait()
            else:
                self.release_first.set()
            return StructuredGenerationResult(
                value=response_model.model_validate(_valid_reconstruct_payload()),
                metrics=ProviderMetrics(),
            )

    async def run() -> list[StructuredGenerationResult[Any]]:
        delegate = Backend()
        counted = d4.CountingBackend(delegate=delegate, capture_logical_identity=True)
        request = StructuredGenerationRequest(
            system_prompt="system", user_prompt="user", timeout_seconds=5
        )
        first = asyncio.create_task(
            counted.generate_structured(request, response_model=action_model)
        )
        await delegate.first_started.wait()
        second = asyncio.create_task(
            counted.generate_structured(request, response_model=action_model)
        )
        return await asyncio.gather(first, second)

    first, second = asyncio.run(run())
    assert first.logical_call_index == 1
    assert second.logical_call_index == 2


def test_interleaved_worker_observations_preserve_task_and_call_identity(tmp_path: Path) -> None:
    """Out-of-order worker results remain linked to their own task and call."""
    custody = _custody(tmp_path, "validated_dto")
    custody.record_binding_call_started(
        {
            "index": 2,
            "generation_role": "section_worker",
            "provider": d5.EXPECTED_PROVIDER,
            "model": d5.EXPECTED_MODEL,
        }
    )
    payload = _valid_reconstruct_payload()
    assert _observe(custody, payload, index=2, task_index=1) is None
    assert _observe(custody, payload, index=1, task_index=0) is None
    rows = [row for row in _rows(custody) if row["event"] == "SECTION_ACTION_SCHEMA_VALIDATED"]
    assert [(row["task_index"], row["logical_call_index"], row["attempt"]) for row in rows] == [
        (1, 2, 1),
        (0, 1, 1),
    ]
    assert rows[0]["dto_path"] != rows[1]["dto_path"]
    custody.finish("SMOKE_PASS")
    assert d5.verify_smoke_observability(custody.paths)["authorized_deleted_dtos"] == 0


def test_schema_invalid_response_does_not_claim_a_validated_dto() -> None:
    """A schema-invalid response produces no schema-valid action event."""
    events: list[dict] = []
    result, calls, _task = _compile_worker([{"action": "invalid"}], events.append, "validated_dto")
    assert not result.success
    assert result.diagnostics[0].code == "structured_schema_validation_failure"
    assert calls == 1
    assert events == []


@pytest.mark.parametrize(
    "change,expected_code",
    [
        ("owner", "worker_contract_binding_owner_mismatch"),
        ("width", "worker_contract_track_mismatch"),
        ("scale", "worker_contract_binding_mismatch"),
        ("color", "worker_contract_binding_mismatch"),
    ],
)
def test_other_contract_rejections_remain_distinct(
    tmp_path: Path, change: str, expected_code: str
) -> None:
    """Other contract failures retain their distinct existing public codes."""
    custody = _custody(tmp_path, "diagnostics")
    payload = deepcopy(_valid_reconstruct_payload())
    first, second = payload["section"]["tracks"]
    if change == "owner":
        first["bindings"], second["bindings"] = second["bindings"], first["bindings"]
    elif change == "width":
        first["width_mm"] = 35
    elif change == "scale":
        first["bindings"][0]["scale"]["maximum"] = 2
    else:
        first["bindings"][0]["style"]["color"] = "#222222"
    error = _observe(custody, payload)
    assert error is not None and error.code == expected_code
    assert _rows(custody)[1]["diagnostic_code"] == expected_code
    assert _rows(custody)[1]["mismatch"] is None


def test_missing_binding_has_distinct_binding_mismatch(tmp_path: Path) -> None:
    """A missing required binding is distinct from a track-set mismatch."""
    custody = _custody(tmp_path, "diagnostics")
    contract = _contract(_smoke_request())
    extra = contract.required_bindings[0].model_copy(update={"handle": "bond_index.binding.2"})
    contract = contract.model_copy(
        update={"required_bindings": (*contract.required_bindings, extra)}
    )
    action = TypeAdapter(SectionSemanticAction).validate_python(_valid_reconstruct_payload())
    worker = CanonicalSectionWorker(
        backend=object(),
        action_observer=custody.record_section_action,
        action_capture_mode="diagnostics",
    )
    error = worker._validate_observed_action(
        action, contract, task_index=0, attempt=1, logical_call_index=1
    )
    assert error is not None and error.code == "worker_contract_incomplete"
    assert _rows(custody)[1]["mismatch"]["classification"] == "BINDING_HANDLE_SET_MISMATCH"
    assert _rows(custody)[1]["mismatch"]["missing_count"] == 1


def test_worker_correction_attempts_have_distinct_correlated_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing bounded correction attempts keep separate observation identities."""
    compilation = compile_request_contract(_smoke_request())
    width = next(
        item
        for item in compilation.requirements.requirements
        if item.owner_ref == "bond_index" and item.field == "width_mm"
    )
    issue = ValidationIssue(
        requirement_id=width.requirement_id,
        owner_kind=width.owner_kind,
        owner_ref=width.owner_ref,
        field=width.field,
        expected_value=width.value,
        code="synthetic_width_issue",
    )
    monkeypatch.setattr(
        section_worker,
        "_collect_validation_issues",
        lambda *_args, **_kwargs: ValidationIssueSet(issues=(issue,)),
    )
    rejected = deepcopy(_valid_reconstruct_payload())
    rejected["section"]["tracks"].pop()
    events: list[dict] = []
    result, calls, _task = _compile_worker(
        [_valid_reconstruct_payload(), rejected], events.append, "validated_dto"
    )
    assert not result.success
    assert result.diagnostics[0].code == "worker_contract_incomplete"
    assert calls == 2
    captured = [event for event in events if event["event"] == "SECTION_ACTION_SCHEMA_VALIDATED"]
    assert [(event["attempt"], event["logical_call_index"]) for event in captured] == [
        (1, 11),
        (2, 12),
    ]
    assert captured[1]["action"] == rejected


@pytest.mark.parametrize(
    ("case", "mode"),
    [
        ("valid", "validated_dto"),
        ("unsafe", "validated_dto"),
        ("rejected", "validated_dto"),
        ("valid", "diagnostics"),
        ("rejected", "diagnostics"),
    ],
)
def test_provider_free_binding_smoke_captures_correlated_worker_dto(
    tmp_path: Path, case: str, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mocked canonical smoke seals complete or rejected capture correctly."""
    if not (REPO_ROOT / "workspace/data/CBL_Main_REV1.las").is_file():
        pytest.skip("local engineering LAS fixture is unavailable")
    monkeypatch.setattr(d5, "_validate_section_capture_location", lambda *_args: None)
    artifact_root = tmp_path / "binding-observability"
    authorization = replace(
        _authorization(campaign_id="binding-observability", artifact_root=str(artifact_root)),
        section_action_capture_mode=mode,
    )
    schemas: list[str] = []
    clients: list[httpx.AsyncClient] = []
    section_payload = deepcopy(_valid_reconstruct_payload())
    if case == "unsafe":
        section_payload["section"]["tracks"][0]["title"] = "Bearer private-secret"
    elif case == "rejected":
        section_payload["section"]["tracks"].pop()

    def client_factory(observer: d5._PhysicalAttemptObserver) -> httpx.AsyncClient:
        async def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            name = body["response_format"]["json_schema"]["name"]
            schemas.append(name)
            payload = (
                _consolidated_duplicate_scope_plan()
                if name == "PlannerWirePlan"
                else section_payload
            )
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": json.dumps(payload)},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            event_hooks={"request": [observer.on_request], "response": [observer.on_response]},
        )
        client._platform = "Linux"
        clients.append(client)
        return client

    def provider_factory(repo_root: Path, smoke_root: Path, token: str, **kwargs: object) -> object:
        adapter = d5.create_live_adapter(
            repo_root=repo_root,
            artifact_root=smoke_root,
            api_key=token,
            project_config=PROJECT_CONFIG,
            request_options=d5._thinking_control_options(),
            require_thinking_control=True,
            http_client_factory=client_factory,
            **kwargs,
        )
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        client._platform = "Linux"
        return adapter

    def endpoint_get(url: str, _token: str) -> dict[str, object]:
        if url == PROJECT_CONFIG.model_catalog_url:
            return {"data": [{"id": d5.EXPECTED_MODEL}]}
        assert url == PROJECT_CONFIG.props_url
        return _props()

    try:
        result = d5.execute_live_binding_smoke(
            repo_root=REPO_ROOT,
            authorization=authorization,
            artifact_root=artifact_root,
            logfile_path=REPO_ROOT / "examples/cbl_main.log.yaml",
            endpoint_get=endpoint_get,
            api_key_loader=lambda: "provider-free-token",
            static_checker=lambda *_args: {"status": "PASS"},
            provider_factory=provider_factory,
        )
    finally:
        for client in clients:
            asyncio.run(client.aclose())

    assert schemas == ["PlannerWirePlan", "ReconstructSectionAction"]
    assert result["terminal"]["logical_calls_by_role"] == {"planner": 1, "section_worker": 1}
    assert result["terminal"]["scientific_population_loaded"] is False
    paths = d5.EvidencePaths(artifact_root, authorization.campaign_id)
    assert stat.S_IMODE(artifact_root.stat().st_mode) == 0o700
    for path in artifact_root.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected
    rows = [json.loads(line) for line in paths.section_actions.read_text().splitlines()]
    assert rows[0]["logical_call_index"] == 2
    if mode == "diagnostics":
        assert result["status"] == ("SMOKE_PASS" if case == "valid" else "SMOKE_CONTRACT_FAIL")
        assert rows[0]["capture_state"] == "metadata_only"
        assert "action" not in rows[0]
        assert not paths.validated_section_dtos.exists()
        assert d5.verify_smoke_observability(paths)["authorized_deleted_dtos"] == 0
        return
    if case == "unsafe":
        assert result["status"] == "SMOKE_HARNESS_FAIL"
        assert result["terminal"]["reason"] == "section_action_evidence_integrity"
        assert rows[0]["capture_state"] == "INCOMPLETE"
        assert rows[0]["capture_failure"] == "DTO_SCREENING_REJECTED"
        assert not paths.validated_section_dtos.exists()
        assert "private-secret" not in paths.section_actions.read_text()
        for path in artifact_root.rglob("*"):
            if path.is_file():
                assert b"private-secret" not in path.read_bytes()
        compile_result = json.loads(paths.compile_result.read_text())
        assert compile_result["diagnostics"][0]["code"] == "worker_evidence_integrity_failure"
        assert compile_result["workers"][0]["stage_evidence"]["semantic_lowering"] == "NOT_REACHED"
        assert d5.verify_smoke_observability(paths)["authorized_deleted_dtos"] == 0
        return
    if case == "rejected":
        assert result["status"] == "SMOKE_CONTRACT_FAIL"
        assert rows[1]["contract_outcome"] == "FAIL"
        assert rows[1]["mismatch"]["classification"] == "TRACK_HANDLE_SET_MISMATCH"
        assert json.loads((paths.root / rows[0]["dto_path"]).read_text()) == section_payload
        assert d5.verify_smoke_observability(paths)["authorized_deleted_dtos"] == 0
        return
    assert result["status"] == "SMOKE_PASS"
    assert rows[1]["contract_outcome"] == "PASS"
    assert (
        json.loads((paths.root / rows[0]["dto_path"]).read_text()) == _valid_reconstruct_payload()
    )
    assert d5.verify_smoke_observability(paths)["authorized_deleted_dtos"] == 0

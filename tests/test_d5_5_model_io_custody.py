"""Provider-free tests for D5 model-I/O custody and inspection rendering."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from scripts import d5_5_inspection_report as report
from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from tests.test_nlp_d5_live_semantic_qualification import (
    REPO_ROOT,
    _authorization,
    _provenance,
    _ready,
)

from wellplot.agent.providers.base import ProviderRequestError, StructuredGenerationRequest
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    ProviderSchemaValidationIssue,
    ProviderSchemaValidationShape,
    StructuredResponseProviderError,
)


def _request() -> StructuredGenerationRequest:
    """Build one deterministic request body for observer tests."""
    return StructuredGenerationRequest(
        system_prompt="system prompt",
        user_prompt="user prompt",
        timeout_seconds=10.0,
        temperature=0.0,
        max_output_tokens=None,
    )


def test_observer_captures_exact_bodies_without_headers() -> None:
    """The request/response pair is captured at the existing HTTP boundary."""
    observer = d5._PhysicalAttemptObserver()
    physical: list[int] = []
    captured: list[dict[str, object]] = []
    observer.callback = physical.append
    observer.bind_model_io(captured.append)
    observer.logical_call_started({"index": 1, "generation_role": "planner", "model": "test-model"})
    observer.set_active_turn("D4-L01:T1")
    request = httpx.Request(
        "POST",
        "https://provider.test/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
            "response_format": {"type": "json_schema"},
        },
        headers={"Authorization": "Bearer secret-token"},
    )
    response = httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": '{"ok": true}'},
                    "finish_reason": "stop",
                }
            ]
        },
        request=request,
    )

    asyncio.run(observer.on_request(request))
    asyncio.run(observer.on_response(response))

    assert physical == [1]
    assert [row["event"] for row in captured] == ["physical_request", "physical_response"]
    row = captured[1]
    assert row["event"] == "physical_response"
    assert row["turn_id"] == "D4-L01:T1"
    assert row["role"] == "planner"
    request_row = captured[0]
    assert request_row["request_json"]["messages"][1]["content"] == "user prompt"  # type: ignore[index]
    assert row["response_json"]["choices"][0]["message"]["content"] == '{"ok": true}'  # type: ignore[index]
    assert "headers" not in json.dumps(captured)
    assert "secret-token" not in json.dumps(captured)


def test_observer_seals_request_when_transport_has_no_response() -> None:
    """A failed transport still leaves the exact attempted request inspectable."""
    observer = d5._PhysicalAttemptObserver()
    captured: list[dict[str, object]] = []
    observer.callback = lambda index: None
    observer.bind_model_io(captured.append)
    observer.logical_call_started({"index": 1, "generation_role": "planner", "model": "test-model"})
    observer.set_active_turn("D4-L01:T1")
    request = httpx.Request(
        "POST",
        "https://provider.test/v1/chat/completions",
        json={"model": "test-model", "messages": []},
    )

    asyncio.run(observer.on_request(request))

    assert len(captured) == 1
    assert captured[0]["event"] == "physical_request"
    assert captured[0]["turn_id"] == "D4-L01:T1"
    assert "response_sha256" not in captured[0]


@pytest.mark.parametrize(
    ("reason", "shape"),
    [
        (ProviderResponseFailureReason.INVALID_JSON, None),
        (
            ProviderResponseFailureReason.SCHEMA_VALIDATION,
            ProviderSchemaValidationShape(
                issue_count=1,
                issues=(ProviderSchemaValidationIssue("missing", ("value",)),),
                truncated=False,
            ),
        ),
    ],
)
def test_counting_backend_preserves_structured_failure_reason_and_shape(
    reason: ProviderResponseFailureReason,
    shape: ProviderSchemaValidationShape | None,
) -> None:
    """Canonical backend diagnostics remain distinguishable in custody events."""

    class BrokenBackend:
        async def generate_structured(self, request: object, *, response_model: object) -> object:
            del request, response_model
            raise StructuredResponseProviderError(
                "bounded provider response failure",
                response_reason=reason,
                validation_shape=shape,
            )

    events: list[dict[str, object]] = []
    backend = d4.CountingBackend(
        delegate=BrokenBackend(),
        call_completed=events.append,
    )
    with pytest.raises(ProviderRequestError):
        asyncio.run(backend.generate_structured(_request(), response_model=d4.SemanticPlan))

    assert events[0]["response_reason"] == reason.value
    if shape is None:
        assert events[0]["validation_shape"] is None
    else:
        assert events[0]["validation_shape"] == shape.to_json()


def test_model_io_digest_is_terminal_and_old_five_file_custody_remains_valid(
    tmp_path: Path,
) -> None:
    """New custody seals model-I/O while historical five-file records remain valid."""
    paths = d5.EvidencePaths(tmp_path / "new", "new-campaign")
    custody = d5.D5CampaignCustody.start(
        paths,
        authorization=_authorization(campaign_id="new-campaign", artifact_root=str(paths.root)),
        provenance=_provenance(),
        readiness=_ready().projection,
    )
    custody.begin_turn("D4-L01:T1")
    custody.record_model_io(
        {
            "event": "physical_response",
            "logical_call_index": 1,
            "request_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "request_body": '{"model":"test-model"}',
            "response_body": '{"choices":[]}',
        }
    )
    custody.finish("INCONCLUSIVE", attribution="TEST", rows=[])
    digests = d5.verify_custody_artifacts(paths)
    assert "model_io_sha256" in digests
    assert (
        json.loads(paths.terminal.read_text(encoding="utf-8"))["model_io_sha256"]
        == digests["model_io_sha256"]
    )

    legacy = tmp_path / "legacy"
    legacy_paths = d5.EvidencePaths(legacy, "legacy-campaign")
    legacy_custody = d5.D5CampaignCustody.start(
        legacy_paths,
        authorization=_authorization(
            campaign_id="legacy-campaign", artifact_root=str(legacy_paths.root)
        ),
        provenance=_provenance(),
        readiness=_ready().projection,
    )
    legacy_paths.model_io.unlink()
    legacy_custody.finish("INCONCLUSIVE", attribution="TEST", rows=[])
    assert d5.verify_custody_artifacts(legacy_paths)["terminal_sha256"] == d5._sha256_file(
        legacy_paths.terminal
    )


def test_inspection_renderer_displays_synthetic_io_and_omits_reasoning(tmp_path: Path) -> None:
    """The read-only renderer exposes prompts/responses without hidden reasoning."""
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "synthetic.state.json").write_text(
        json.dumps({"campaign_id": "synthetic", "decision": "PASS"}), encoding="utf-8"
    )
    case = d4.load_cases(REPO_ROOT)[0]
    (campaign / "synthetic.evidence.jsonl").write_text(
        json.dumps(
            {
                "turn_id": case["turn_id"],
                "outcome": "PASS",
                "grader_status": "PASS",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (campaign / "synthetic.model-io.jsonl").write_text(
        json.dumps(
            {
                "event": "physical_response",
                "turn_id": case["turn_id"],
                "logical_call_index": 1,
                "role": "planner",
                "model": "test-model",
                "physical_attempt": 1,
                "request_sha256": "a" * 64,
                "response_sha256": "b" * 64,
                "request_json": {
                    "model": "test-model",
                    "messages": [
                        {"role": "system", "content": "system-visible"},
                        {"role": "user", "content": "user-visible"},
                    ],
                    "response_format": {"type": "json_schema"},
                },
                "response_json": {
                    "choices": [
                        {
                            "message": {
                                "content": '{"answer": "visible"}',
                                "reasoning_content": "must not appear",
                            }
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "inspection.html"
    report.render_report(REPO_ROOT, campaign, output)
    rendered = output.read_text(encoding="utf-8")
    assert "system-visible" in rendered
    assert "user-visible" in rendered
    assert "answer" in rendered
    assert "must not appear" not in rendered
    assert "Authorization" not in rendered

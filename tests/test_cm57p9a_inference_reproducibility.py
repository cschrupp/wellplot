"""Provider-free CM-57P9A reproducibility harness tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from scripts import cm57p9_runtime_fingerprint as fingerprint
from scripts import cm57p9a_inference_reproducibility as p9

from wellplot.agent.providers.base import StructuredGenerationRequest


def _call(
    *,
    content_hash: str = "content",
    structure_hash: str = "structure",
    outcome: str = "structured_success",
) -> dict[str, object]:
    """Build one bounded synthetic provider call."""
    return {
        "call_kind": "INITIAL",
        "outcome": outcome,
        "provider_category": None,
        "raw_assistant_content_sha256": content_hash,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_ms": 1.0,
        "structure_hash": structure_hash,
    }


def _result(
    *,
    plan_hash: str | None = "plan",
    facts_hash: str | None = "facts",
    content_hash: str = "content",
    structure_hash: str = "structure",
    outcome: str = "structured_success",
) -> dict[str, object]:
    """Build one bounded synthetic arm result."""
    call = _call(
        content_hash=content_hash,
        structure_hash=structure_hash,
        outcome=outcome,
    )
    return {
        "final_plan_available": plan_hash is not None,
        "final_classification": "PLANNER_CONTRACT_OK"
        if plan_hash is not None
        else "PLANNER_SCHEMA_FAILURE",
        "planner_call_count": 1,
        "invalid_response_retry_used": False,
        "semantic_correction_used": False,
        "semantic_plan_sha256": plan_hash,
        "planner_facts_sha256": facts_hash,
        "call_path_sha256": p9._call_path_hash([call]),
        "call_path_structure_sha256": p9._call_path_structure_hash([call]),
        "call_trace": [call],
        "final_facts": {
            "report_presence_correct": False,
            "report_capabilities_exact": False,
            "section_count_correct": False,
            "section_multiset_exact": False,
            "duplicate_capability_type": False,
            "parent_closure_valid": False,
            "unresolved_correct": False,
        },
    }


def _group_rows(
    *,
    plan_hashes: tuple[str | None, ...] = ("plan",) * p9.ATTEMPTS,
    facts_hashes: tuple[str | None, ...] = ("facts",) * p9.ATTEMPTS,
    content_hashes: tuple[str, ...] = ("content",) * p9.ATTEMPTS,
    structure_hashes: tuple[str, ...] = ("structure",) * p9.ATTEMPTS,
) -> list[dict[str, object]]:
    """Build eight rows for one synthetic case and arm."""
    case = p9.load_manifest()[0]
    return [
        {
            "case_id": case["case_id"],
            "repetition_index": index,
            "arms": {
                "P": _result(
                    plan_hash=plan_hashes[index],
                    facts_hash=facts_hashes[index],
                    content_hash=content_hashes[index],
                    structure_hash=structure_hashes[index],
                ),
                "RC": _result(),
            },
        }
        for index in range(p9.ATTEMPTS)
    ]


def test_manifest_is_hash_only_and_has_frozen_case_order() -> None:
    """The manifest resolves six cases without retaining request prose."""
    cases = p9.load_manifest()
    assert [case["case_id"] for case in cases] == list(p9.CASE_IDS)
    assert all("request" in case for case in cases)
    payload = json.loads(p9.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert all("request" not in entry for entry in payload["cases"])
    assert p9.artifact_sha256(p9.MANIFEST_PATH) == p9.EXPECTED_MANIFEST_SHA256


def test_frozen_controls_and_future_population_are_provider_free() -> None:
    """The pre-live report declares the full population without provider work."""
    report = p9.prelive_report()
    assert report["provider_calls"] == 0
    assert report["worker_program_calls"] == 0
    assert report["cases"] == 6
    assert report["arms"] == ["P", "RC"]
    assert report["repetitions"] == 8
    assert report["planner_executions"] == 96
    assert report["provider_calls_min"] == 96
    assert report["provider_calls_max"] == 192
    assert report["live_inference"] == "NOT_STARTED"


def test_prompt_backend_changes_only_the_frozen_system_prompt() -> None:
    """P and RC preserve every provider-neutral request field except the prompt."""

    class Delegate:
        def __init__(self) -> None:
            self.requests: list[StructuredGenerationRequest] = []

        async def generate_structured(
            self,
            request: StructuredGenerationRequest,
            *,
            response_model: type[BaseModel],
        ) -> str:
            del response_model
            self.requests.append(request)
            return "result"

    request = StructuredGenerationRequest(
        system_prompt=p9._PLANNER_SYSTEM_PROMPT,
        user_prompt="payload",
        timeout_seconds=900.0,
        temperature=0.0,
        max_output_tokens=16384,
    )
    delegate = Delegate()
    backend = p9.PromptBackend(delegate=delegate, arm="RC")
    result = asyncio.run(backend.generate_structured(request, response_model=BaseModel))
    assert result == "result"
    forwarded = delegate.requests[0]
    assert forwarded.system_prompt == p9.composed_prompt("RC")
    assert forwarded.user_prompt == request.user_prompt
    assert forwarded.timeout_seconds == request.timeout_seconds
    assert forwarded.temperature == request.temperature
    assert forwarded.max_output_tokens == request.max_output_tokens


def test_observed_client_returns_original_response_and_redacted_event() -> None:
    """Observation hashes assistant text but never serializes the text itself."""

    class Completions:
        def __init__(self, response: object) -> None:
            self.response = response
            self.arguments: dict[str, object] | None = None

        async def create(self, **arguments: object) -> object:
            self.arguments = arguments
            return self.response

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="private response"), finish_reason="stop"
            )
        ],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4, total_tokens=7),
    )
    completions = Completions(response)
    observer = p9.ResponseObserver(events=[])
    client = p9.ObservedClient(
        SimpleNamespace(chat=SimpleNamespace(completions=completions)), observer
    )
    observed = asyncio.run(client.chat.completions.create(model="qwen", messages=[]))
    assert observed is response
    assert completions.arguments == {"model": "qwen", "messages": []}
    event = observer.events[0]
    assert event["raw_assistant_content_sha256"] == p9.sha256_text("private response")
    assert "private response" not in json.dumps(event)


def test_observed_client_records_transport_failure_without_exception_text() -> None:
    """Transport failures remain bounded evidence and retain no exception text."""

    class Completions:
        async def create(self, **arguments: object) -> object:
            del arguments
            raise RuntimeError("secret endpoint detail")

    observer = p9.ResponseObserver(events=[])
    client = p9.ObservedClient(
        SimpleNamespace(chat=SimpleNamespace(completions=Completions())), observer
    )
    with pytest.raises(RuntimeError, match="secret endpoint detail"):
        asyncio.run(client.chat.completions.create(model="qwen"))
    assert observer.events[0]["response_observed"] is False
    assert "secret endpoint detail" not in json.dumps(observer.events)


def test_group_classification_allows_provider_text_variation_for_plan_reproducibility() -> None:
    """Stable facts and call structure classify differing response text as plan-stable."""
    rows = _group_rows(content_hashes=tuple(f"content-{index}" for index in range(p9.ATTEMPTS)))
    group = p9._classify_group(rows, p9.load_manifest()[0], "P")
    assert group["classification"] == "PLAN_REPRODUCIBLE_WITH_TEXT_VARIATION"
    assert group["levels"]["provider"] == "PROVIDER_TEXT_VARIANT"
    assert group["levels"]["semantic_plan"] == "SEMANTIC_PLAN_STABLE"
    assert group["levels"]["contract_facts"] == "CONTRACT_FACTS_STABLE"


def test_group_classification_distinguishes_contract_and_nonreproducible_variation() -> None:
    """Fact variation is a contract failure; plan-only variation remains contract-stable."""
    case = p9.load_manifest()[0]
    plan_variants = _group_rows(plan_hashes=tuple(f"plan-{index}" for index in range(p9.ATTEMPTS)))
    assert p9._classify_group(plan_variants, case, "P")["classification"] == (
        "CONTRACT_REPRODUCIBLE_WITH_SEMANTIC_TEXT_VARIATION"
    )
    fact_variants = _group_rows(
        facts_hashes=tuple(f"facts-{index}" for index in range(p9.ATTEMPTS))
    )
    assert p9._classify_group(fact_variants, case, "P")["classification"] == "NOT_REPRODUCIBLE"
    path_variants = _group_rows()
    for index, row in enumerate(path_variants):
        call = row["arms"]["P"]["call_trace"][0]
        call["outcome"] = f"outcome-{index}"
        row["arms"]["P"]["call_path_sha256"] = p9._call_path_hash([call])
        row["arms"]["P"]["call_path_structure_sha256"] = p9._call_path_structure_hash([call])
    assert p9._classify_group(path_variants, case, "P")["classification"] == "NOT_REPRODUCIBLE"


def test_identical_terminal_failures_are_reproducible() -> None:
    """A repeated terminal schema failure is still a stable inference outcome."""
    case = p9.load_manifest()[0]
    failures = _group_rows(
        plan_hashes=(None,) * p9.ATTEMPTS,
        facts_hashes=("terminal-failure",) * p9.ATTEMPTS,
    )
    group = p9._classify_group(failures, case, "P")
    assert group["classification"] == "EXACT_REPRODUCIBLE"
    assert group["levels"]["semantic_plan"] == "SEMANTIC_PLAN_ABSENT_STABLE"


def test_mixed_terminal_success_and_failure_is_not_reproducible() -> None:
    """A single success among repeated terminal failures breaks plan stability."""
    plan_hashes = (None,) * (p9.ATTEMPTS - 1) + ("plan",)
    facts_hashes = ("terminal-failure",) * (p9.ATTEMPTS - 1) + ("success",)
    rows = _group_rows(plan_hashes=plan_hashes, facts_hashes=facts_hashes)
    assert p9._classify_group(rows, p9.load_manifest()[0], "P")["classification"] == (
        "NOT_REPRODUCIBLE"
    )


def test_terminal_category_variation_is_not_reproducible() -> None:
    """Different terminal classifications produce different planner-facts hashes."""
    rows = _group_rows(
        plan_hashes=(None,) * p9.ATTEMPTS,
        facts_hashes=("terminal-failure",) * p9.ATTEMPTS,
    )
    result = rows[-1]["arms"]["P"]
    result["final_classification"] = "PROVIDER_INFRA_FAILURE"
    result["planner_facts_sha256"] = p9._planner_facts_hash(
        None,
        "PROVIDER_INFRA_FAILURE",
        final_plan_available=False,
    )
    assert p9._classify_group(rows, p9.load_manifest()[0], "P")["classification"] == (
        "NOT_REPRODUCIBLE"
    )


def test_terminal_response_text_variation_uses_a_lower_exactness_tier() -> None:
    """Terminal state can remain reproducible when only provider text varies."""
    rows = _group_rows(
        plan_hashes=(None,) * p9.ATTEMPTS,
        facts_hashes=("terminal-failure",) * p9.ATTEMPTS,
        content_hashes=tuple(f"terminal-{index}" for index in range(p9.ATTEMPTS)),
    )
    assert p9._classify_group(rows, p9.load_manifest()[0], "P")["classification"] == (
        "PLAN_REPRODUCIBLE_WITH_TEXT_VARIATION"
    )


def test_decision_precedence_prioritizes_nonreproducibility() -> None:
    """The frozen top-level decision prefers lower reproducibility levels."""
    groups = [{"classification": "EXACT_REPRODUCIBLE"}]
    assert p9._decision(True, [], groups) == "SAME_PROCESS_EXACT_REPRODUCIBLE"
    groups.append({"classification": "PLAN_REPRODUCIBLE_WITH_TEXT_VARIATION"})
    assert p9._decision(True, [], groups) == "SAME_PROCESS_PLAN_REPRODUCIBLE"
    groups.append({"classification": "CONTRACT_REPRODUCIBLE_WITH_SEMANTIC_TEXT_VARIATION"})
    assert p9._decision(True, [], groups) == "SAME_PROCESS_CONTRACT_REPRODUCIBLE"
    groups.append({"classification": "NOT_REPRODUCIBLE"})
    assert p9._decision(True, [], groups) == "SAME_PROCESS_NOT_REPRODUCIBLE"
    assert p9._decision(False, ["wrong_row_count"], groups) == (
        "INCONCLUSIVE_REPRODUCIBILITY_EVALUATION"
    )


def test_population_integrity_rejects_infrastructure_and_worker_calls() -> None:
    """Infrastructure and accidental worker activity invalidate the population."""
    cases = p9.load_manifest()
    rows: list[dict[str, object]] = []
    for case in cases:
        for repetition_index in range(p9.ATTEMPTS):
            rows.append(
                {
                    **p9._frozen_provenance(),
                    "case_id": case["case_id"],
                    "repetition_index": repetition_index,
                    "request_sha256": p9.sha256_text(str(case["request"])),
                    "gold_sha256": p9._gold_sha(case),
                    "arms": {
                        arm: {
                            "prompt_sha256": p9.PROMPT_SHA256[arm],
                            "response_schema_sha256": p9.EXPECTED_SCHEMA_SHA256,
                            "program_call_count": 1 if arm == "RC" else 0,
                            "provider_infrastructure_failure": arm == "P",
                            "final_facts": None,
                        }
                        for arm in p9.ARMS
                    },
                    "authorized_checkpoint": "wrong-checkpoint",
                    "runtime_fingerprint_sha256": "wrong-fingerprint",
                }
            )
    complete, reasons = p9.population_integrity(
        rows,
        cases,
        runtime_fingerprint_sha256="expected-fingerprint",
        expected_checkpoint="expected-checkpoint",
    )
    assert not complete
    assert "provider_infrastructure_failure" in reasons
    assert "worker_program_call" in reasons
    assert "runtime_fingerprint_mismatch" in reasons
    assert "authorized_checkpoint_mismatch" in reasons


def test_runtime_fingerprint_validation_and_comparison_are_provider_free(tmp_path: Path) -> None:
    """Fingerprint identity is locally derived and detects endpoint drift."""
    binary = tmp_path / "llama-server"
    model = tmp_path / "model.gguf"
    binary.write_bytes(b"binary")
    model.write_bytes(b"model")
    value = fingerprint.build_fingerprint(
        server_pid=1,
        llama_binary=binary,
        model_file=model,
        endpoint="http://127.0.0.1:8888/v1",
        model_api_label=p9.FROZEN_MODEL,
    )
    valid, reasons = fingerprint.validate_fingerprint(value)
    assert valid, reasons
    changed = dict(value, endpoint="http://127.0.0.1:9999/v1")
    assert "endpoint" in fingerprint.compare_fingerprints(value, changed)
    invalid = dict(value, model_sha256=None)
    valid, reasons = fingerprint.validate_fingerprint(invalid)
    assert not valid
    assert "model_sha256_invalid" in reasons


def test_continuous_batching_requires_an_explicit_flag() -> None:
    """The helper does not mistake llama.cpp's implicit default for a fact."""
    assert fingerprint._runtime_settings(None)["continuous_batching"] is None
    assert fingerprint._runtime_settings([])["continuous_batching"] is None
    assert fingerprint._runtime_settings(["--cont-batching"])["continuous_batching"] is True
    assert fingerprint._runtime_settings(["-cb"])["continuous_batching"] is True
    assert fingerprint._runtime_settings(["--no-cont-batching"])["continuous_batching"] is False
    assert fingerprint._runtime_settings(["-nocb"])["continuous_batching"] is False


def test_live_mode_rejects_nonempty_evidence_before_provider_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A populated evidence path cannot be resumed or append-written."""
    evidence = tmp_path / "evidence.jsonl"
    evidence.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(p9, "OUTPUT_PATH", evidence)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:8888/v1",
        api_key_env="UNUSED",
        api_key_file=None,
        runtime_fingerprint_pre=str(tmp_path / "pre.json"),
    )
    with pytest.raises(RuntimeError, match="Refusing to append"):
        asyncio.run(p9._run_live(args, "0" * 40))


def test_special_diagnostics_accepts_terminal_provider_failures() -> None:
    """Provider failures with no facts remain summarizable evidence."""
    rows = [
        {
            "case_id": case_id,
            "arms": {
                arm: {
                    "final_facts": None,
                    "final_plan_available": False,
                    "final_classification": "PROVIDER_INFRA_FAILURE",
                    "invalid_response_retry_used": False,
                    "reference": {
                        "missing_required_reference": None,
                    },
                }
                for arm in p9.ARMS
            },
        }
        for case_id in p9.CASE_IDS
    ]
    diagnostics = p9._special_diagnostics(rows)
    assert diagnostics["p7-dossier-gamma-17"]["P"] == {"present": 0, "absent": 0}

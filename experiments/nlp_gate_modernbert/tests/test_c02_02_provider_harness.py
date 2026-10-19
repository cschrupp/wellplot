"""C02-02: mocked provider/local harness qualification (zero live inference)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlp_gate_modernbert.decomposer_capability_02.budget import BudgetExhausted, CallBudget
from nlp_gate_modernbert.decomposer_capability_02.contracts import ModelPathId, SemanticDecomposerRequest
from nlp_gate_modernbert.decomposer_capability_02.normalize import extract_json_object_text
from nlp_gate_modernbert.decomposer_capability_02.openrouter_adapter import ForbiddenLiveTransport
from nlp_gate_modernbert.decomposer_capability_02.registry import (
    CAPABILITIES,
    OPENROUTER_DEEPSEEK_V41_FLASH_1017,
    OPENROUTER_GEMINI_4_ARGON,
    build_mocked_local_adapter,
    build_mocked_openrouter_adapter,
)
from nlp_gate_modernbert.decomposer_pilot import prompt_contract
from nlp_gate_modernbert.nl_program_eval.freeze import freeze_candidate, FrozenCandidate
from nlp_gate_modernbert.paths import EVIDENCE_DIR

DC02 = EVIDENCE_DIR / "decomposer_capability_02"
C02_01 = DC02 / "c02_01"
C02_02 = DC02 / "c02_02"
SNAP = C02_02 / "openrouter_snapshots"


def _req() -> SemanticDecomposerRequest:
    return SemanticDecomposerRequest(
        utterance="Add a Petrophysics track with GR 0–150 and RT logarithmic 0.2–2000.",
        projected_workspace_json='{"curves":[],"tracks":[]}',
        case_id="D5GAP-0096",
    )


def test_all_four_paths_registered() -> None:
    assert set(CAPABILITIES) == set(ModelPathId)


def test_gemini_and_deepseek_ids_match_verified_catalog() -> None:
    assert CAPABILITIES[ModelPathId.GEMINI_4_ARGON].openrouter_model_id == OPENROUTER_GEMINI_4_ARGON
    assert (
        CAPABILITIES[ModelPathId.DEEPSEEK_V41_FLASH_1017].openrouter_model_id
        == OPENROUTER_DEEPSEEK_V41_FLASH_1017
    )
    gem = json.loads((SNAP / "gemini_4_argon_model.json").read_text())
    ds = json.loads((SNAP / "deepseek_v4_1_flash_1017_model.json").read_text())
    assert gem["id"] == OPENROUTER_GEMINI_4_ARGON
    assert ds["id"] == OPENROUTER_DEEPSEEK_V41_FLASH_1017
    assert "response_format" in gem["supported_parameters"]
    assert "structured_outputs" in ds["supported_parameters"]


def test_openrouter_request_uses_frozen_prompt_and_excludes_case_id() -> None:
    def transport(body):
        raise AssertionError("should not be called")

    adapter = build_mocked_openrouter_adapter(
        ModelPathId.GEMINI_4_ARGON, budget=CallBudget(authorized=1), transport=transport
    )
    body = adapter.build_request(_req())
    assert body["model"] == OPENROUTER_GEMINI_4_ARGON
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["content"] == prompt_contract.SYSTEM_PROMPT
    blob = json.dumps(body)
    assert "D5GAP-0096" not in blob
    assert "case_id" not in blob


def test_mocked_openrouter_success_normalizes_and_freezes() -> None:
    program = {"version": None, "tasks": []}

    def transport(body):
        return {
            "id": "gen-mock",
            "model": body["model"],
            "provider": "MockProvider",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(program)},
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

    for path in (ModelPathId.GEMINI_4_ARGON, ModelPathId.DEEPSEEK_V41_FLASH_1017):
        adapter = build_mocked_openrouter_adapter(
            path, budget=CallBudget(authorized=1), transport=transport
        )
        out = adapter.generate(_req())
        assert out.ok
        assert out.provider == "MockProvider"
        assert out.prompt_tokens == 10
        frozen = freeze_candidate(out.final_answer_text.encode("utf-8"))
        assert isinstance(frozen, FrozenCandidate)


def test_mocked_openrouter_parse_error_and_provider_error() -> None:
    def bad_json(_body):
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "not json"}}],
            "usage": {},
        }

    adapter = build_mocked_openrouter_adapter(
        ModelPathId.GEMINI_4_ARGON, budget=CallBudget(authorized=2), transport=bad_json
    )
    out = adapter.generate(_req())
    assert out.error and out.error.startswith("parse_error:")

    def provider_err(_body):
        return {"error": {"message": "rate_limit", "code": 429}}

    adapter2 = build_mocked_openrouter_adapter(
        ModelPathId.DEEPSEEK_V41_FLASH_1017,
        budget=CallBudget(authorized=1),
        transport=provider_err,
    )
    out2 = adapter2.generate(_req())
    assert out2.error and "provider_error" in out2.error


def test_budget_enforcement() -> None:
    calls = {"n": 0}

    def transport(_body):
        calls["n"] += 1
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"tasks":[]}'}}],
            "usage": {},
        }

    adapter = build_mocked_openrouter_adapter(
        ModelPathId.GEMINI_4_ARGON, budget=CallBudget(authorized=1), transport=transport
    )
    assert adapter.generate(_req()).ok
    with pytest.raises(BudgetExhausted):
        adapter.generate(_req())
    assert calls["n"] == 1


def test_live_transport_forbidden() -> None:
    adapter = build_mocked_openrouter_adapter(
        ModelPathId.GEMINI_4_ARGON,
        budget=CallBudget(authorized=1),
        transport=ForbiddenLiveTransport(),
    )
    out = adapter.generate(_req())
    assert out.error and "live_openrouter_transport_forbidden" in out.error
    assert "execution_authority" in out.error


def test_local_qwen_paths_mock_thinking_separation() -> None:
    def gen_instruct(body):
        assert body["enable_thinking"] is False
        assert body["hf_model_id"] == "Qwen/Qwen3-4B-Instruct-2507"
        return {
            "text": '{"version":null,"tasks":[]}',
            "finish_reason": "stop",
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
        }

    def gen_thinking(body):
        assert body["enable_thinking"] is True
        return {
            "text": '<think>plan</think>\n{"version":null,"tasks":[]}',
            "reasoning_text": "plan",
            "finish_reason": "stop",
            "prompt_tokens": 3,
            "completion_tokens": 8,
            "reasoning_tokens": 4,
            "total_tokens": 11,
        }

    inst = build_mocked_local_adapter(
        ModelPathId.QWEN3_4B_INSTRUCT_2507,
        budget=CallBudget(authorized=1),
        generate_fn=gen_instruct,
    )
    think = build_mocked_local_adapter(
        ModelPathId.QWEN3_4B_THINKING_2507,
        budget=CallBudget(authorized=1),
        generate_fn=gen_thinking,
    )
    o1 = inst.generate(_req())
    o2 = think.generate(_req())
    assert o1.ok and o2.ok
    assert o2.reasoning_text == "plan"
    assert "think" not in o2.final_answer_text


def test_extract_json_from_fence() -> None:
    text = 'Here:\n```json\n{"tasks":[],"version":null}\n```\n'
    out = extract_json_object_text(text)
    assert '"tasks":[]' in out


def test_c02_01_benchmark_unchanged_digests() -> None:
    bench = json.loads((C02_01 / "benchmark_manifest.json").read_text())
    # Smoke: six cases still present; C02-02 must not rewrite gold.
    assert len(bench["cases"]) == 6
    assert bench["gold_cases_unchanged_by_deepseek_amendment"] is True


def test_qualification_manifest_exists_and_claims_zero_live_calls() -> None:
    man = json.loads((C02_02 / "qualification_manifest.json").read_text())
    assert man["slice"] == "C02-02"
    assert man["live_inference_calls"] == 0
    assert man["billable_openrouter_calls"] == 0
    assert man["gemini_endpoint_status"] == "RESOLVED"
    assert man["gemini_openrouter_model_id"] == OPENROUTER_GEMINI_4_ARGON
    assert set(man["qualified_adapter_paths"]) == {p.value for p in ModelPathId}

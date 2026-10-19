"""WP-DC02-03-DEEPSEEK-CORRECTIVE-SMOKE-AUTH-001 — exactly one Morph DeepSeek call."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_capability_02.api_key import inspect_api_key_presence
from nlp_gate_modernbert.decomposer_capability_02.budget import ExecutionBudgets
from nlp_gate_modernbert.decomposer_capability_02.contracts import (
    ModelPathId,
    SemanticDecomposerRequest,
)
from nlp_gate_modernbert.decomposer_capability_02.cost_accounting import dual_cost_record
from nlp_gate_modernbert.decomposer_capability_02.live_rate_snapshot import (
    fetch_endpoints_document,
    morph_cost_card_from_endpoints,
)
from nlp_gate_modernbert.decomposer_capability_02.live_transport import (
    LiveOpenRouterTransport,
    redact_request_for_archive,
)
from nlp_gate_modernbert.decomposer_capability_02.openrouter_adapter import OpenRouterAdapter
from nlp_gate_modernbert.decomposer_capability_02.registry import (
    DEEPSEEK_PROVIDER_ORDER,
    OPENROUTER_DEEPSEEK_V41_FLASH_1017,
)
from nlp_gate_modernbert.decomposer_pilot import prompt_contract, workspace_serialize
from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import INVOCATION_ORDER
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate
from nlp_gate_modernbert.nl_program_eval.input import build_decomposer_input
from nlp_gate_modernbert.paths import EVIDENCE_DIR, EXPERIMENT_ROOT

AUTHORITY = "WP-DC02-03-DEEPSEEK-CORRECTIVE-SMOKE-AUTH-001"
PARENT_SHA = "f0459470e448bf06525024d6141822e7859057b7"
SMOKE_CASE = "D5GAP-0085"
MAX_TOKENS = 4096
REASONING = {"effort": "low"}
OUT = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_deepseek_corrective_smoke"
ORIGINAL_SMOKE = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_joint_hosted_smoke"

EXPECTED_SYSTEM_SHA = "e617d84e535f72423285f8824014d52c67f40533aaae660783a7dbcb5988b8f4"
EXPECTED_USER_SHA = "5662a961cf892c5aafc9448f5daa18ac2f93bc24efda0c07d3da19b5fb9aaddb"
EXPECTED_ORACLE_CLEANED = "9181ee1d1d414870b59ca4d4946b3f0c0607d1d8e19388e099711e7cd15a164d"
EXPECTED_ORACLE_FROZEN = "54b7045da274250bc971588282bb5e441b74e96ca250ea76a699ea2e46b514bb"
EXPECTED_DECOMPOSER_INPUT = "91622db600dd94d48881adbdad694188bb34c4117f6f9ee9f9ce557cfd70ac4f"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    import subprocess

    return (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(EXPERIMENT_ROOT.parents[1]),
            text=True,
        ).strip()
    )


def preflight() -> dict[str, Any]:
    import subprocess

    head = _git_head()
    repo = str(EXPERIMENT_ROOT.parents[1])
    if head != PARENT_SHA:
        rc = subprocess.call(
            ["git", "merge-base", "--is-ancestor", PARENT_SHA, head],
            cwd=repo,
        )
        if rc != 0:
            raise RuntimeError(f"preflight_fail:head_not_descendant_of_parent:{head}")

    key = inspect_api_key_presence()
    if not key.present:
        raise RuntimeError("preflight_fail:OPENROUTER_API_KEY_PRESENT=false")

    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"preflight_fail:evidence_destination_not_empty:{OUT}")

    # Original joint-smoke DeepSeek observation must remain immutable.
    orig_sum = ORIGINAL_SMOKE / "deepseek" / "generation_summary.json"
    if not orig_sum.is_file():
        raise RuntimeError("preflight_fail:original_deepseek_smoke_missing")
    orig = json.loads(orig_sum.read_text(encoding="utf-8"))
    if orig.get("completion_tokens") != 1024 or orig.get("reasoning_tokens") != 1024:
        raise RuntimeError("preflight_fail:original_deepseek_smoke_digest_unexpected")

    bench = json.loads(
        (EVIDENCE_DIR / "decomposer_capability_02/c02_01/benchmark_manifest.json").read_text()
    )
    case0 = bench["cases"][0]
    assert case0["case_id"] == SMOKE_CASE
    assert bench["invocation_order"][0] == SMOKE_CASE
    assert INVOCATION_ORDER[0] == SMOKE_CASE
    if case0["oracle_cleaned_program_sha256"] != EXPECTED_ORACLE_CLEANED:
        raise RuntimeError("preflight_fail:oracle_cleaned_digest_mismatch")
    if case0["oracle_frozen_candidate_sha256"] != EXPECTED_ORACLE_FROZEN:
        raise RuntimeError("preflight_fail:oracle_frozen_digest_mismatch")
    if case0["decomposer_input_sha256"] != EXPECTED_DECOMPOSER_INPUT:
        raise RuntimeError("preflight_fail:decomposer_input_digest_mismatch")

    oracle_ref = EVIDENCE_DIR / "decomposer_capability_02/c02_01/oracle_refs" / f"{SMOKE_CASE}.json"
    oracle_ref_sha = _sha256_file(oracle_ref)

    di = build_decomposer_input(SMOKE_CASE)
    ws_json = workspace_serialize.serialize_projected_workspace(di.projected_workspace)
    assert set(di.to_payload().keys()) == {"utterance", "projected_workspace"}

    endpoints_doc = fetch_endpoints_document(OPENROUTER_DEEPSEEK_V41_FLASH_1017)
    cost_card, rate_archive = morph_cost_card_from_endpoints(
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        endpoints_doc=endpoints_doc,
    )

    sys_sha = prompt_contract.system_prompt_sha256()
    user_sha = prompt_contract.user_template_sha256()
    report = {
        "authority": AUTHORITY,
        "parent_sha": PARENT_SHA,
        "starting_head": head,
        "parent_is_ancestor_or_equal": True,
        "OPENROUTER_API_KEY_PRESENT": True,
        "smoke_case_id": SMOKE_CASE,
        "openrouter_model_id": OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        "provider_order": list(DEEPSEEK_PROVIDER_ORDER),
        "allow_fallbacks": False,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
        "include_reasoning": False,
        "reasoning": dict(REASONING),
        "response_format": {"type": "json_object"},
        "prompt_system_sha256": sys_sha,
        "prompt_user_template_sha256": user_sha,
        "expected_prompt_system_sha256": EXPECTED_SYSTEM_SHA,
        "expected_prompt_user_template_sha256": EXPECTED_USER_SHA,
        "prompt_match": sys_sha == EXPECTED_SYSTEM_SHA and user_sha == EXPECTED_USER_SHA,
        "oracle_cleaned_program_sha256": EXPECTED_ORACLE_CLEANED,
        "oracle_frozen_candidate_sha256": EXPECTED_ORACLE_FROZEN,
        "decomposer_input_sha256": EXPECTED_DECOMPOSER_INPUT,
        "oracle_ref_file_sha256": oracle_ref_sha,
        "evidence_destination": str(OUT.relative_to(EXPERIMENT_ROOT.parents[1])),
        "original_joint_smoke_deepseek_immutable": True,
        "live_morph_rate_card": cost_card.to_json(),
        "live_morph_rate_archive": rate_archive,
        "budgets": {
            "logical_calls_authorized": 1,
            "transport_attempts_authorized": 2,
        },
        "gemini_retest_authorized": False,
        "cases_2_through_6_authorized": False,
        "preflight_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not report["prompt_match"]:
        raise RuntimeError("preflight_fail:prompt_digest_mismatch")
    if DEEPSEEK_PROVIDER_ORDER != ("Morph",):
        raise RuntimeError("preflight_fail:provider_pin_not_morph")
    return report, cost_card, endpoints_doc


def run_deepseek_corrective_smoke() -> dict[str, Any]:
    pf, cost_card, endpoints_doc = preflight()
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / "preflight.json").write_text(json.dumps(pf, indent=2, sort_keys=True) + "\n")
    (OUT / "live_morph_endpoints_snapshot.json").write_text(
        json.dumps(endpoints_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT / "live_morph_rate_card.json").write_text(
        json.dumps(pf["live_morph_rate_archive"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    di = build_decomposer_input(SMOKE_CASE)
    ws_json = workspace_serialize.serialize_projected_workspace(di.projected_workspace)
    req = SemanticDecomposerRequest(
        utterance=di.utterance,
        projected_workspace_json=ws_json,
        case_id=SMOKE_CASE,
    )

    budgets = ExecutionBudgets.for_six_case_ceiling(
        logical_authorized=1,
        transport_authorized=2,
        estimated_usd_cap=2.0,
    )
    transport = LiveOpenRouterTransport()
    adapter = OpenRouterAdapter(
        model_path=ModelPathId.DEEPSEEK_V41_FLASH_1017,
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        budgets=budgets,
        transport=transport,
        temperature=0.0,
        max_tokens=MAX_TOKENS,
        include_reasoning=False,
        reasoning=dict(REASONING),
        provider_order=list(DEEPSEEK_PROVIDER_ORDER),
        allow_fallbacks=False,
        require_provider_pin=True,
        max_transport_attempts_per_logical_call=2,
        cost_card=cost_card,
    )

    arm_dir = OUT / "deepseek"
    arm_dir.mkdir(parents=True, exist_ok=True)
    body = adapter.build_request(req)
    (arm_dir / "request_redacted.json").write_text(
        json.dumps(redact_request_for_archive(body), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    t0 = time.perf_counter()
    gen = adapter.generate(req)
    latency = time.perf_counter() - t0

    eval_result: dict[str, Any] | None = None
    freeze_status = None
    semantic_equivalent = None
    failure_labels: list[str] = []
    schema_valid = None
    reached_freeze = False

    if gen.final_answer_text:
        ev = evaluate_raw_candidate(SMOKE_CASE, gen.final_answer_text)
        freeze_status = ev.freeze_status
        semantic_equivalent = ev.semantically_equivalent
        failure_labels = list(ev.failure_labels)
        schema_valid = ev.schema_valid
        reached_freeze = bool(ev.schema_valid)
        eval_result = ev.to_json()
        operational_pass = True
        # Structural freeze failure is still an operational PASS (pipeline exercised).
        semantic_layer1_completed = bool(ev.schema_valid)
    else:
        operational_pass = False
        semantic_layer1_completed = False
        freeze_status = "NOT_REACHED"

    dual = dual_cost_record(
        cost_card=cost_card,
        prompt_tokens=gen.prompt_tokens,
        completion_tokens=gen.completion_tokens,
        raw_usage=(gen.metadata or {}).get("raw_usage"),
    )

    row = {
        "arm": "deepseek_corrective",
        "authority": AUTHORITY,
        "case_id": SMOKE_CASE,
        "model_path": gen.model_path.value,
        "openrouter_model_id": gen.openrouter_model_id,
        "requested_provider_order": (gen.metadata or {}).get("requested_provider_order"),
        "observed_provider": gen.provider,
        "error": gen.error,
        "operational_smoke_pass": operational_pass,
        "semantic_equivalent": semantic_equivalent,
        "semantic_layer1_completed": semantic_layer1_completed,
        "schema_valid": schema_valid,
        "reached_freeze": reached_freeze,
        "freeze_status": freeze_status,
        "failure_labels": failure_labels,
        "prompt_tokens": gen.prompt_tokens,
        "completion_tokens": gen.completion_tokens,
        "reasoning_tokens": gen.reasoning_tokens,
        "total_tokens": gen.total_tokens,
        "estimated_usd_from_live_rate_card": dual["estimated_usd_from_pre_run_cost_card"],
        "provider_reported_usd": dual["provider_reported_usd"],
        "dual_cost": dual,
        "transport_attempts": (gen.metadata or {}).get("transport_attempts"),
        "latency_seconds": latency,
        "finish_reason": gen.finish_reason,
        "generation_id": (gen.metadata or {}).get("id"),
        "raw_usage": (gen.metadata or {}).get("raw_usage"),
        "raw_output_sha256": _sha256_text(gen.raw_text or ""),
        "final_answer_sha256": _sha256_text(gen.final_answer_text or ""),
        "request_max_tokens": MAX_TOKENS,
        "request_reasoning": dict(REASONING),
        "include_reasoning": False,
        "original_joint_smoke_retained_immutable": True,
    }
    (arm_dir / "generation_summary.json").write_text(
        json.dumps(row, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (arm_dir / "raw_output_utf8.txt").write_text(gen.raw_text or "", encoding="utf-8")
    if gen.final_answer_text:
        (arm_dir / "final_answer.json").write_text(gen.final_answer_text + "\n", encoding="utf-8")
    if eval_result is not None:
        (arm_dir / "evaluation.json").write_text(
            json.dumps(eval_result, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    summary = {
        "authority": AUTHORITY,
        "parent_sha": PARENT_SHA,
        "smoke_case_id": SMOKE_CASE,
        "logical_calls": budgets.logical_calls.consumed,
        "transport_attempts": budgets.transport_attempts.consumed,
        "operational_smoke_pass": operational_pass,
        "semantic_layer1_completed": semantic_layer1_completed,
        "semantic_equivalent": semantic_equivalent,
        "freeze_status": freeze_status,
        "schema_valid": schema_valid,
        "observed_provider": gen.provider,
        "error": gen.error,
        "prompt_tokens": gen.prompt_tokens,
        "completion_tokens": gen.completion_tokens,
        "reasoning_tokens": gen.reasoning_tokens,
        "finish_reason": gen.finish_reason,
        "provider_reported_usd": dual["provider_reported_usd"],
        "estimated_usd_from_live_rate_card": dual["estimated_usd_from_pre_run_cost_card"],
        "gemini_retest_executed": False,
        "cases_2_through_6_executed": False,
        "original_joint_smoke_retained_immutable": True,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "STOP_FOR_INDEPENDENT_CORRECTIVE_SMOKE_REVIEW",
        "arm": row,
    }
    (OUT / "smoke_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    (OUT / "authorization.json").write_text(
        json.dumps(
            {
                "authority": AUTHORITY,
                "parent_sha": PARENT_SHA,
                "logical_calls_authorized": 1,
                "transport_attempts_authorized": 2,
                "gemini_retest_authorized": False,
                "cases_2_through_6_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (OUT / "provenance.md").write_text(
        f"""# DeepSeek corrective smoke (Morph)

```
AUTHORITY: {AUTHORITY}
PARENT SHA: {PARENT_SHA}
SMOKE CASE: {SMOKE_CASE}
MODEL: {OPENROUTER_DEEPSEEK_V41_FLASH_1017}
PROVIDER: Morph (no fallback)
max_tokens: {MAX_TOKENS}
reasoning.effort: low
include_reasoning: false
LOGICAL CALLS: {budgets.logical_calls.consumed}/1
TRANSPORT ATTEMPTS: {budgets.transport_attempts.consumed}/2
OPERATIONAL PASS: {operational_pass}
FREEZE STATUS: {freeze_status}
PROVIDER REPORTED USD: {dual['provider_reported_usd']}
```

Original joint-smoke DeepSeek observation retained immutable.
Gemini retest not executed. Cases 2–6 not executed.

STATUS:
STOP FOR INDEPENDENT DEEPSEEK CORRECTIVE SMOKE REVIEW
"""
    )
    return summary


if __name__ == "__main__":
    summary = run_deepseek_corrective_smoke()
    print(
        json.dumps(
            {
                "logical_calls": summary["logical_calls"],
                "transport_attempts": summary["transport_attempts"],
                "operational_smoke_pass": summary["operational_smoke_pass"],
                "freeze_status": summary["freeze_status"],
                "schema_valid": summary["schema_valid"],
                "semantic_layer1_completed": summary["semantic_layer1_completed"],
                "observed_provider": summary["observed_provider"],
                "error": summary["error"],
                "prompt_tokens": summary["prompt_tokens"],
                "completion_tokens": summary["completion_tokens"],
                "reasoning_tokens": summary["reasoning_tokens"],
                "finish_reason": summary["finish_reason"],
                "provider_reported_usd": summary["provider_reported_usd"],
            },
            indent=2,
        )
    )

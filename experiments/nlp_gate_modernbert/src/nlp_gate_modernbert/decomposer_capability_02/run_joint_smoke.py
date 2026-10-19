"""WP-DC02-03-JOINT-HOSTED-SMOKE-AUTH-001 — exactly two logical OpenRouter calls."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_capability_02.api_key import inspect_api_key_presence
from nlp_gate_modernbert.decomposer_capability_02.budget import ExecutionBudgets
from nlp_gate_modernbert.decomposer_capability_02.contracts import SemanticDecomposerRequest
from nlp_gate_modernbert.decomposer_capability_02.cost_card import load_cost_card
from nlp_gate_modernbert.decomposer_capability_02.live_transport import (
    LiveOpenRouterTransport,
    redact_request_for_archive,
)
from nlp_gate_modernbert.decomposer_capability_02.registry import (
    DEEPSEEK_PROVIDER_ORDER,
    GEMINI_PROVIDER_ORDER,
    OPENROUTER_DEEPSEEK_V41_FLASH_1017,
    OPENROUTER_GEMINI_4_ARGON,
    build_deepseek_budget_adapter,
    build_gemini_ceiling_prep_adapter,
)
from nlp_gate_modernbert.decomposer_pilot import prompt_contract, workspace_serialize
from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import INVOCATION_ORDER
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate
from nlp_gate_modernbert.nl_program_eval.input import build_decomposer_input
from nlp_gate_modernbert.paths import EVIDENCE_DIR, EXPERIMENT_ROOT

AUTHORITY = "WP-DC02-03-JOINT-HOSTED-SMOKE-AUTH-001"
PARENT_SHA = "ab6fcd29f4545e0128afaefb2c1b032df8f30bc7"
SMOKE_CASE = "D5GAP-0085"
OUT = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_joint_hosted_smoke"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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

    gem_card = load_cost_card(
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        pinned_provider=GEMINI_PROVIDER_ORDER[0],
    )
    ds_card = load_cost_card(
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        pinned_provider=DEEPSEEK_PROVIDER_ORDER[0],
    )

    di = build_decomposer_input(SMOKE_CASE)
    ws_json = workspace_serialize.serialize_projected_workspace(di.projected_workspace)
    assert set(di.to_payload().keys()) == {"utterance", "projected_workspace"}

    bench = json.loads(
        (EVIDENCE_DIR / "decomposer_capability_02/c02_01/benchmark_manifest.json").read_text()
    )
    assert bench["invocation_order"][0] == SMOKE_CASE
    assert INVOCATION_ORDER[0] == SMOKE_CASE

    report = {
        "authority": AUTHORITY,
        "parent_sha": PARENT_SHA,
        "starting_head": head,
        "parent_is_ancestor_or_equal": True,
        "OPENROUTER_API_KEY_PRESENT": True,
        "smoke_case_id": SMOKE_CASE,
        "prompt_system_sha256": prompt_contract.system_prompt_sha256(),
        "prompt_user_template_sha256": prompt_contract.user_template_sha256(),
        "expected_prompt_system_sha256": "e617d84e535f72423285f8824014d52c67f40533aaae660783a7dbcb5988b8f4",
        "expected_prompt_user_template_sha256": "5662a961cf892c5aafc9448f5daa18ac2f93bc24efda0c07d3da19b5fb9aaddb",
        "prompt_match": (
            prompt_contract.system_prompt_sha256()
            == "e617d84e535f72423285f8824014d52c67f40533aaae660783a7dbcb5988b8f4"
            and prompt_contract.user_template_sha256()
            == "5662a961cf892c5aafc9448f5daa18ac2f93bc24efda0c07d3da19b5fb9aaddb"
        ),
        "gemini": {
            "model": OPENROUTER_GEMINI_4_ARGON,
            "provider_order": list(GEMINI_PROVIDER_ORDER),
            "cost_card": gem_card.to_json(),
        },
        "deepseek": {
            "model": OPENROUTER_DEEPSEEK_V41_FLASH_1017,
            "provider_order": list(DEEPSEEK_PROVIDER_ORDER),
            "provider_selection_rationale": (
                "Morph from C02-02 DeepSeek endpoint snapshot: "
                "has_response_format + has_structured_outputs; no fallback"
            ),
            "cost_card": ds_card.to_json(),
        },
        "budgets": {
            "logical_calls_authorized": 2,
            "transport_attempts_authorized": 4,
            "estimated_usd_cap": 2.0,
        },
        "cases_2_through_6_authorized": False,
        "decoding_note": "json_object + freeze_candidate; XGrammar hard-mask equivalence NOT claimed",
        "preflight_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not report["prompt_match"]:
        raise RuntimeError("preflight_fail:prompt_digest_mismatch")
    return report


def _run_one(
    *,
    arm: str,
    adapter,
    req: SemanticDecomposerRequest,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    body = adapter.build_request(req)
    (out_dir / "request_redacted.json").write_text(
        json.dumps(redact_request_for_archive(body), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    t0 = time.perf_counter()
    gen = adapter.generate(req)
    latency = time.perf_counter() - t0

    operational_pass = gen.error is None or (
        # smoke operational pass requires pipeline exercise; parse/freeze can still run
        False
    )
    # Authority: smoke passes if correct model/provider, response complete enough to exercise
    # normalization and scoring, evidence preserved, freeze/eval executes.
    eval_result: dict[str, Any] | None = None
    freeze_status = None
    semantic_equivalent = None
    failure_labels: list[str] = []

    if gen.final_answer_text:
        ev = evaluate_raw_candidate(SMOKE_CASE, gen.final_answer_text)
        freeze_status = ev.freeze_status
        semantic_equivalent = ev.semantically_equivalent
        failure_labels = list(ev.failure_labels)
        eval_result = ev.to_json()
        operational_pass = True
    elif gen.error and gen.error.startswith("parse_error:"):
        # Response received; normalize attempted; freeze not reached — still operationally informative
        # but authority says "complete enough to exercise normalization and scoring".
        # Parse failure means scoring path partially exercised; treat as operational FAIL for full pipeline.
        operational_pass = False
        freeze_status = "NOT_REACHED"
    elif gen.error:
        operational_pass = False
        freeze_status = "NOT_REACHED"
    else:
        operational_pass = False

    row = {
        "arm": arm,
        "case_id": SMOKE_CASE,
        "model_path": gen.model_path.value,
        "openrouter_model_id": gen.openrouter_model_id,
        "requested_provider_order": (gen.metadata or {}).get("requested_provider_order"),
        "observed_provider": gen.provider,
        "error": gen.error,
        "operational_smoke_pass": operational_pass,
        "semantic_equivalent": semantic_equivalent,
        "freeze_status": freeze_status,
        "failure_labels": failure_labels,
        "prompt_tokens": gen.prompt_tokens,
        "completion_tokens": gen.completion_tokens,
        "reasoning_tokens": gen.reasoning_tokens,
        "total_tokens": gen.total_tokens,
        "estimated_usd": (gen.metadata or {}).get("estimated_usd"),
        "transport_attempts": (gen.metadata or {}).get("transport_attempts"),
        "latency_seconds": latency,
        "finish_reason": gen.finish_reason,
        "generation_id": (gen.metadata or {}).get("id"),
        "raw_usage": (gen.metadata or {}).get("raw_usage"),
        "raw_output_sha256": _sha256_text(gen.raw_text or ""),
        "final_answer_sha256": _sha256_text(gen.final_answer_text or ""),
    }
    (out_dir / "generation_summary.json").write_text(
        json.dumps(row, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (out_dir / "raw_output_utf8.txt").write_text(gen.raw_text or "", encoding="utf-8")
    if gen.final_answer_text:
        (out_dir / "final_answer.json").write_text(gen.final_answer_text + "\n", encoding="utf-8")
    if eval_result is not None:
        (out_dir / "evaluation.json").write_text(
            json.dumps(eval_result, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    # Never write Authorization or API key material.
    return row


def run_joint_smoke() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    pf = preflight()
    (OUT / "preflight.json").write_text(json.dumps(pf, indent=2, sort_keys=True) + "\n")

    di = build_decomposer_input(SMOKE_CASE)
    ws_json = workspace_serialize.serialize_projected_workspace(di.projected_workspace)
    req = SemanticDecomposerRequest(
        utterance=di.utterance,
        projected_workspace_json=ws_json,
        case_id=SMOKE_CASE,
    )

    budgets = ExecutionBudgets.for_six_case_ceiling(
        logical_authorized=2,
        transport_authorized=4,
        estimated_usd_cap=2.0,
    )
    transport = LiveOpenRouterTransport()

    gemini = build_gemini_ceiling_prep_adapter(budgets=budgets, transport=transport)
    deepseek = build_deepseek_budget_adapter(budgets=budgets, transport=transport)

    results = []
    results.append(
        _run_one(arm="gemini", adapter=gemini, req=req, out_dir=OUT / "gemini")
    )
    results.append(
        _run_one(arm="deepseek", adapter=deepseek, req=req, out_dir=OUT / "deepseek")
    )

    summary = {
        "authority": AUTHORITY,
        "parent_sha": PARENT_SHA,
        "smoke_case_id": SMOKE_CASE,
        "logical_calls": budgets.logical_calls.consumed,
        "transport_attempts": budgets.transport_attempts.consumed,
        "estimated_usd": budgets.estimated_usd,
        "estimated_usd_cap": budgets.estimated_usd_cap,
        "cases_2_through_6_executed": False,
        "arms": results,
        "both_operational_pass": all(r["operational_smoke_pass"] for r in results),
        "decoding_comparability": "NOT_XGRAMMAR_HARD_MASK",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "STOP_FOR_INDEPENDENT_SMOKE_REVIEW",
    }
    (OUT / "smoke_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    (OUT / "provenance.md").write_text(
        f"""# Joint hosted smoke — Gemini + DeepSeek

```
AUTHORITY: {AUTHORITY}
PARENT SHA: {PARENT_SHA}
SMOKE CASE: {SMOKE_CASE}
LOGICAL CALLS: {budgets.logical_calls.consumed}/2
TRANSPORT ATTEMPTS: {budgets.transport_attempts.consumed}/4
ESTIMATED USD: {budgets.estimated_usd}
CASES 2–6: NOT EXECUTED
```

## Outcomes

| Arm | Operational smoke | Semantic equivalent | Provider | Error |
|-----|-------------------|---------------------|----------|-------|
| Gemini | {results[0]['operational_smoke_pass']} | {results[0]['semantic_equivalent']} | {results[0]['observed_provider']} | {results[0]['error']} |
| DeepSeek | {results[1]['operational_smoke_pass']} | {results[1]['semantic_equivalent']} | {results[1]['observed_provider']} | {results[1]['error']} |

XGrammar hard-mask equivalence is not claimed.

STATUS:
STOP FOR INDEPENDENT JOINT SMOKE REVIEW
"""
    )
    return summary


if __name__ == "__main__":
    summary = run_joint_smoke()
    # Print only non-secret summary fields
    print(
        json.dumps(
            {
                "logical_calls": summary["logical_calls"],
                "transport_attempts": summary["transport_attempts"],
                "estimated_usd": summary["estimated_usd"],
                "both_operational_pass": summary["both_operational_pass"],
                "arms": [
                    {
                        "arm": a["arm"],
                        "operational_smoke_pass": a["operational_smoke_pass"],
                        "semantic_equivalent": a["semantic_equivalent"],
                        "observed_provider": a["observed_provider"],
                        "error": a["error"],
                        "prompt_tokens": a["prompt_tokens"],
                        "completion_tokens": a["completion_tokens"],
                    }
                    for a in summary["arms"]
                ],
            },
            indent=2,
        )
    )

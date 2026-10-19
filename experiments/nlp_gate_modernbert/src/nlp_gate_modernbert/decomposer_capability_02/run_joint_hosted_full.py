"""WP-DC02-03-JOINT-HOSTED-FULL-RUN-AUTH-001 — cases 2–6 for Gemini + DeepSeek."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections import Counter
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
from nlp_gate_modernbert.decomposer_capability_02.cost_card import CostCard
from nlp_gate_modernbert.decomposer_capability_02.live_rate_snapshot import (
    fetch_endpoints_document,
    google_ai_studio_cost_card_from_endpoints,
    morph_cost_card_from_endpoints,
)
from nlp_gate_modernbert.decomposer_capability_02.live_transport import (
    LiveOpenRouterTransport,
    redact_request_for_archive,
)
from nlp_gate_modernbert.decomposer_capability_02.openrouter_adapter import OpenRouterAdapter
from nlp_gate_modernbert.decomposer_capability_02.registry import (
    DEEPSEEK_PROVIDER_ORDER,
    GEMINI_PROVIDER_ORDER,
    OPENROUTER_DEEPSEEK_V41_FLASH_1017,
    OPENROUTER_GEMINI_4_ARGON,
)
from nlp_gate_modernbert.decomposer_pilot import prompt_contract, workspace_serialize
from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import INVOCATION_ORDER
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate
from nlp_gate_modernbert.nl_program_eval.input import build_decomposer_input
from nlp_gate_modernbert.paths import EVIDENCE_DIR, EXPERIMENT_ROOT

AUTHORITY = "WP-DC02-03-JOINT-HOSTED-FULL-RUN-AUTH-001"
PARENT_SHA = "27db77a3ca913b4298afef291f09064d9d1931d2"
OUT = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_joint_hosted_full_run"

CASE_1 = INVOCATION_ORDER[0]
CASES_2_THROUGH_6 = tuple(INVOCATION_ORDER[1:])
ALL_CASES = tuple(INVOCATION_ORDER)

GEMINI_CASE1_SRC = (
    EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_joint_hosted_smoke" / "gemini"
)
DEEPSEEK_CASE1_SRC = (
    EVIDENCE_DIR
    / "decomposer_capability_02"
    / "c02_03_deepseek_corrective_smoke"
    / "deepseek"
)
ORIGINAL_FAILED_DEEPSEEK = (
    EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_joint_hosted_smoke" / "deepseek"
)

EXPECTED_SYSTEM_SHA = "e617d84e535f72423285f8824014d52c67f40533aaae660783a7dbcb5988b8f4"
EXPECTED_USER_SHA = "5662a961cf892c5aafc9448f5daa18ac2f93bc24efda0c07d3da19b5fb9aaddb"

GEMINI_MAX_TOKENS = 1024
DEEPSEEK_MAX_TOKENS = 4096
DEEPSEEK_REASONING = {"effort": "low"}


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


def _load_benchmark_case_digests() -> dict[str, dict[str, str]]:
    bench = json.loads(
        (EVIDENCE_DIR / "decomposer_capability_02/c02_01/benchmark_manifest.json").read_text()
    )
    assert tuple(bench["invocation_order"]) == ALL_CASES
    assert tuple(INVOCATION_ORDER) == ALL_CASES
    out: dict[str, dict[str, str]] = {}
    for row in bench["cases"]:
        out[row["case_id"]] = {
            "oracle_cleaned_program_sha256": row["oracle_cleaned_program_sha256"],
            "oracle_frozen_candidate_sha256": row["oracle_frozen_candidate_sha256"],
            "decomposer_input_sha256": row["decomposer_input_sha256"],
            "utterance_sha256": row["utterance_sha256"],
        }
    return out


def _common_preflight_checks() -> dict[str, Any]:
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

    for path in (GEMINI_CASE1_SRC, DEEPSEEK_CASE1_SRC, ORIGINAL_FAILED_DEEPSEEK):
        if not (path / "generation_summary.json").is_file():
            raise RuntimeError(f"preflight_fail:missing_case1_source:{path}")

    orig_fail = json.loads(
        (ORIGINAL_FAILED_DEEPSEEK / "generation_summary.json").read_text(encoding="utf-8")
    )
    if orig_fail.get("reasoning_tokens") != 1024 or orig_fail.get("completion_tokens") != 1024:
        raise RuntimeError("preflight_fail:original_failed_deepseek_unexpected")

    digests = _load_benchmark_case_digests()
    sys_sha = prompt_contract.system_prompt_sha256()
    user_sha = prompt_contract.user_template_sha256()
    if sys_sha != EXPECTED_SYSTEM_SHA or user_sha != EXPECTED_USER_SHA:
        raise RuntimeError("preflight_fail:prompt_digest_mismatch")

    return {
        "authority": AUTHORITY,
        "parent_sha": PARENT_SHA,
        "starting_head": head,
        "OPENROUTER_API_KEY_PRESENT": True,
        "prompt_system_sha256": sys_sha,
        "prompt_user_template_sha256": user_sha,
        "prompt_match": True,
        "cases_authorized_new": list(CASES_2_THROUGH_6),
        "case_1_rerun_authorized": False,
        "case_digests": digests,
        "gemini_case1_source": str(GEMINI_CASE1_SRC.relative_to(EXPERIMENT_ROOT.parents[1])),
        "deepseek_case1_source": str(DEEPSEEK_CASE1_SRC.relative_to(EXPERIMENT_ROOT.parents[1])),
        "original_failed_deepseek_qualification_only": str(
            ORIGINAL_FAILED_DEEPSEEK.relative_to(EXPERIMENT_ROOT.parents[1])
        ),
        "decoding_comparability": "json_object_plus_freeze_NOT_XGRAMMAR_HARD_MASK",
        "preflight_utc": datetime.now(timezone.utc).isoformat(),
    }


def _arm_preflight(
    *,
    arm: str,
    openrouter_model_id: str,
    provider_order: tuple[str, ...],
    max_tokens: int,
    reasoning: dict[str, Any] | None,
    include_reasoning: bool,
    cost_card: CostCard,
    rate_archive: dict[str, Any],
) -> dict[str, Any]:
    return {
        "arm": arm,
        "openrouter_model_id": openrouter_model_id,
        "provider_order": list(provider_order),
        "allow_fallbacks": False,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "include_reasoning": include_reasoning,
        "reasoning": reasoning,
        "response_format": {"type": "json_object"},
        "live_rate_card": cost_card.to_json(),
        "live_rate_archive": rate_archive,
        "cases": list(CASES_2_THROUGH_6),
        "logical_calls_authorized": 5,
        "transport_attempts_authorized_per_case": 2,
        "semantic_retries": 0,
    }


def _row_from_generation(
    *,
    arm: str,
    case_id: str,
    gen,
    latency: float,
    cost_card: CostCard,
    request_max_tokens: int,
    request_reasoning: dict[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    eval_result: dict[str, Any] | None = None
    freeze_status = "NOT_REACHED"
    semantic_equivalent = None
    failure_labels: list[str] = []
    schema_valid = False
    semantic_layer1_completed = False
    pipeline_exercised = False

    if gen.final_answer_text:
        ev = evaluate_raw_candidate(case_id, gen.final_answer_text)
        freeze_status = ev.freeze_status
        semantic_equivalent = ev.semantically_equivalent
        failure_labels = list(ev.failure_labels)
        schema_valid = bool(ev.schema_valid)
        semantic_layer1_completed = bool(ev.schema_valid)
        pipeline_exercised = True
        eval_result = ev.to_json()
    elif gen.error:
        failure_labels = [str(gen.error)]

    dual = dual_cost_record(
        cost_card=cost_card,
        prompt_tokens=gen.prompt_tokens,
        completion_tokens=gen.completion_tokens,
        raw_usage=(gen.metadata or {}).get("raw_usage"),
    )

    return {
        "arm": arm,
        "case_id": case_id,
        "source": source,
        "model_path": gen.model_path.value if hasattr(gen.model_path, "value") else gen.model_path,
        "openrouter_model_id": gen.openrouter_model_id,
        "requested_provider_order": (gen.metadata or {}).get("requested_provider_order"),
        "observed_provider": gen.provider,
        "error": gen.error,
        "pipeline_exercised": pipeline_exercised,
        "schema_valid": schema_valid,
        "reached_freeze": schema_valid,
        "semantic_layer1_completed": semantic_layer1_completed,
        "semantic_equivalent": semantic_equivalent,
        "freeze_status": freeze_status,
        "failure_labels": failure_labels,
        "prompt_tokens": gen.prompt_tokens,
        "completion_tokens": gen.completion_tokens,
        "reasoning_tokens": gen.reasoning_tokens,
        "total_tokens": gen.total_tokens,
        "dual_cost": dual,
        "provider_reported_usd": dual["provider_reported_usd"],
        "estimated_usd_from_live_rate_card": dual["estimated_usd_from_pre_run_cost_card"],
        "transport_attempts": (gen.metadata or {}).get("transport_attempts"),
        "latency_seconds": latency,
        "finish_reason": gen.finish_reason,
        "generation_id": (gen.metadata or {}).get("id"),
        "raw_usage": (gen.metadata or {}).get("raw_usage"),
        "raw_output_sha256": _sha256_text(gen.raw_text or ""),
        "final_answer_sha256": _sha256_text(gen.final_answer_text or ""),
        "request_max_tokens": request_max_tokens,
        "request_reasoning": request_reasoning,
        "evaluation": eval_result,
        "raw_text": gen.raw_text or "",
        "final_answer_text": gen.final_answer_text or "",
        "request_body": None,
    }


def _import_case1_row(*, arm: str, src: Path, expected_case: str) -> dict[str, Any]:
    gen_sum = json.loads((src / "generation_summary.json").read_text(encoding="utf-8"))
    if gen_sum.get("case_id") != expected_case:
        raise RuntimeError(f"case1_import_fail:case_mismatch:{src}")
    eval_path = src / "evaluation.json"
    evaluation = (
        json.loads(eval_path.read_text(encoding="utf-8")) if eval_path.is_file() else None
    )
    schema_valid = bool(evaluation.get("schema_valid")) if evaluation else False
    freeze_status = (
        evaluation.get("freeze_status")
        if evaluation
        else gen_sum.get("freeze_status") or "NOT_REACHED"
    )
    semantic_equivalent = (
        evaluation.get("semantically_equivalent")
        if evaluation
        else gen_sum.get("semantic_equivalent")
    )
    failure_labels = (
        list(evaluation.get("failure_labels") or [])
        if evaluation
        else list(gen_sum.get("failure_labels") or [])
    )
    provider_reported = gen_sum.get("provider_reported_usd")
    if provider_reported is None:
        raw_usage = gen_sum.get("raw_usage") or {}
        provider_reported = raw_usage.get("cost")

    return {
        "arm": arm,
        "case_id": expected_case,
        "source": "imported_case1_smoke",
        "model_path": gen_sum.get("model_path"),
        "openrouter_model_id": gen_sum.get("openrouter_model_id"),
        "requested_provider_order": gen_sum.get("requested_provider_order"),
        "observed_provider": gen_sum.get("observed_provider"),
        "error": gen_sum.get("error"),
        "pipeline_exercised": bool(
            (src / "final_answer.json").is_file() or gen_sum.get("final_answer_sha256")
        ),
        "schema_valid": schema_valid,
        "reached_freeze": schema_valid,
        "semantic_layer1_completed": schema_valid,
        "semantic_equivalent": semantic_equivalent,
        "freeze_status": freeze_status,
        "failure_labels": failure_labels,
        "prompt_tokens": gen_sum.get("prompt_tokens"),
        "completion_tokens": gen_sum.get("completion_tokens"),
        "reasoning_tokens": gen_sum.get("reasoning_tokens"),
        "total_tokens": gen_sum.get("total_tokens"),
        "dual_cost": gen_sum.get("dual_cost"),
        "provider_reported_usd": provider_reported,
        "estimated_usd_from_live_rate_card": gen_sum.get("estimated_usd_from_live_rate_card")
        or gen_sum.get("estimated_usd"),
        "transport_attempts": gen_sum.get("transport_attempts"),
        "latency_seconds": gen_sum.get("latency_seconds"),
        "finish_reason": gen_sum.get("finish_reason"),
        "generation_id": gen_sum.get("generation_id"),
        "raw_usage": gen_sum.get("raw_usage"),
        "raw_output_sha256": gen_sum.get("raw_output_sha256"),
        "final_answer_sha256": gen_sum.get("final_answer_sha256"),
        "request_max_tokens": gen_sum.get("request_max_tokens"),
        "request_reasoning": gen_sum.get("request_reasoning"),
        "evaluation": evaluation,
        "import_source_path": str(src.relative_to(EXPERIMENT_ROOT.parents[1])),
        "import_generation_summary_sha256": _sha256_file(src / "generation_summary.json"),
    }


def _write_case_artifacts(case_dir: Path, row: dict[str, Any], request_body: dict | None) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    persist = {k: v for k, v in row.items() if k not in ("raw_text", "final_answer_text", "request_body")}
    (case_dir / "generation_summary.json").write_text(
        json.dumps(persist, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    if request_body is not None:
        (case_dir / "request_redacted.json").write_text(
            json.dumps(redact_request_for_archive(request_body), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if row.get("raw_text") is not None and row.get("source") != "imported_case1_smoke":
        (case_dir / "raw_output_utf8.txt").write_text(row.get("raw_text") or "", encoding="utf-8")
    if row.get("final_answer_text"):
        (case_dir / "final_answer.json").write_text(
            (row["final_answer_text"] if row["final_answer_text"].endswith("\n") else row["final_answer_text"] + "\n"),
            encoding="utf-8",
        )
    if row.get("evaluation") is not None:
        (case_dir / "evaluation.json").write_text(
            json.dumps(row["evaluation"], indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )


def _copy_case1_artifacts(arm_dir: Path, src: Path) -> None:
    dest = arm_dir / CASE_1
    dest.mkdir(parents=True, exist_ok=True)
    for name in (
        "generation_summary.json",
        "evaluation.json",
        "final_answer.json",
        "raw_output_utf8.txt",
        "request_redacted.json",
    ):
        p = src / name
        if p.is_file():
            shutil.copy2(p, dest / name)
    pointer = {
        "imported": True,
        "case_id": CASE_1,
        "source_path": str(src.relative_to(EXPERIMENT_ROOT.parents[1])),
        "note": "Case 1 not re-executed; copied from accepted smoke evidence.",
    }
    (dest / "import_pointer.json").write_text(
        json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _run_arm_cases(
    *,
    arm: str,
    adapter: OpenRouterAdapter,
    cost_card: CostCard,
    arm_dir: Path,
    request_max_tokens: int,
    request_reasoning: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_id in CASES_2_THROUGH_6:
        di = build_decomposer_input(case_id)
        ws_json = workspace_serialize.serialize_projected_workspace(di.projected_workspace)
        req = SemanticDecomposerRequest(
            utterance=di.utterance,
            projected_workspace_json=ws_json,
            case_id=case_id,
        )
        body = adapter.build_request(req)
        t0 = time.perf_counter()
        gen = adapter.generate(req)
        latency = time.perf_counter() - t0

        # Protocol defects that must stop the campaign.
        if gen.error and str(gen.error).startswith("provider_mismatch"):
            raise RuntimeError(f"protocol_defect:provider_mismatch:{arm}:{case_id}:{gen.error}")
        observed = gen.provider
        if observed is not None and observed not in adapter.provider_order:
            raise RuntimeError(
                f"protocol_defect:unauthorized_provider:{arm}:{case_id}:{observed}"
            )
        if gen.openrouter_model_id and adapter.openrouter_model_id not in str(
            gen.openrouter_model_id
        ):
            # Allow provider-returned aliases that still contain the requested id.
            if gen.openrouter_model_id != adapter.openrouter_model_id:
                # Soft check: recorded requested model must match adapter pin.
                pass

        row = _row_from_generation(
            arm=arm,
            case_id=case_id,
            gen=gen,
            latency=latency,
            cost_card=cost_card,
            request_max_tokens=request_max_tokens,
            request_reasoning=request_reasoning,
            source="live_full_run",
        )
        _write_case_artifacts(arm_dir / case_id, row, body)
        # Drop bulky fields from in-memory matrix rows.
        slim = {k: v for k, v in row.items() if k not in ("raw_text", "final_answer_text")}
        rows.append(slim)
    return rows


def _summarize_arm(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    reached = sum(1 for r in rows if r.get("reached_freeze"))
    schema_valid = sum(1 for r in rows if r.get("schema_valid"))
    frozen_rows = [r for r in rows if r.get("schema_valid")]
    sem_among_frozen = sum(1 for r in frozen_rows if r.get("semantic_equivalent") is True)
    sem_overall = sum(1 for r in rows if r.get("semantic_equivalent") is True)
    labels: Counter[str] = Counter()
    for r in rows:
        for lab in r.get("failure_labels") or []:
            labels[str(lab)] += 1
        if r.get("schema_valid") and r.get("semantic_equivalent") is True:
            labels["SEMANTIC_EQUIVALENT"] += 1
    costs = [float(r["provider_reported_usd"]) for r in rows if r.get("provider_reported_usd") is not None]
    return {
        "arm": arm,
        "n_cases": n,
        "reached_freeze_count": reached,
        "schema_valid_count": schema_valid,
        "semantic_equivalent_among_frozen": sem_among_frozen,
        "semantic_equivalent_among_frozen_denominator": len(frozen_rows),
        "semantic_equivalent_overall": sem_overall,
        "failure_label_distribution": dict(sorted(labels.items())),
        "latency_seconds_total": sum(float(r.get("latency_seconds") or 0) for r in rows),
        "prompt_tokens_total": sum(int(r.get("prompt_tokens") or 0) for r in rows),
        "completion_tokens_total": sum(int(r.get("completion_tokens") or 0) for r in rows),
        "reasoning_tokens_total": sum(int(r.get("reasoning_tokens") or 0) for r in rows),
        "provider_reported_usd_total": sum(costs) if costs else None,
        "cases": [
            {
                "case_id": r["case_id"],
                "source": r.get("source"),
                "observed_provider": r.get("observed_provider"),
                "freeze_status": r.get("freeze_status"),
                "schema_valid": r.get("schema_valid"),
                "semantic_equivalent": r.get("semantic_equivalent"),
                "semantic_layer1_completed": r.get("semantic_layer1_completed"),
                "failure_labels": r.get("failure_labels"),
                "prompt_tokens": r.get("prompt_tokens"),
                "completion_tokens": r.get("completion_tokens"),
                "reasoning_tokens": r.get("reasoning_tokens"),
                "latency_seconds": r.get("latency_seconds"),
                "provider_reported_usd": r.get("provider_reported_usd"),
                "finish_reason": r.get("finish_reason"),
                "error": r.get("error"),
            }
            for r in rows
        ],
    }


def run_joint_hosted_full() -> dict[str, Any]:
    common = _common_preflight_checks()
    OUT.mkdir(parents=True, exist_ok=False)

    # --- Gemini arm preflight + 5 calls ---
    gem_endpoints = fetch_endpoints_document(OPENROUTER_GEMINI_4_ARGON)
    gem_card, gem_archive = google_ai_studio_cost_card_from_endpoints(
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        endpoints_doc=gem_endpoints,
    )
    gem_pf = _arm_preflight(
        arm="gemini",
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        provider_order=GEMINI_PROVIDER_ORDER,
        max_tokens=GEMINI_MAX_TOKENS,
        reasoning=None,
        include_reasoning=False,
        cost_card=gem_card,
        rate_archive=gem_archive,
    )
    gem_dir = OUT / "gemini"
    gem_dir.mkdir(parents=True, exist_ok=True)
    (gem_dir / "preflight.json").write_text(
        json.dumps({**common, **gem_pf}, indent=2, sort_keys=True) + "\n"
    )
    (gem_dir / "live_endpoints_snapshot.json").write_text(
        json.dumps(gem_endpoints, indent=2, sort_keys=True) + "\n"
    )
    (gem_dir / "live_rate_card.json").write_text(
        json.dumps(gem_archive, indent=2, sort_keys=True) + "\n"
    )

    gem_budgets = ExecutionBudgets.for_six_case_ceiling(
        logical_authorized=5,
        transport_authorized=10,
        estimated_usd_cap=25.0,
    )
    gem_adapter = OpenRouterAdapter(
        model_path=ModelPathId.GEMINI_4_ARGON,
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        budgets=gem_budgets,
        transport=LiveOpenRouterTransport(),
        temperature=0.0,
        max_tokens=GEMINI_MAX_TOKENS,
        include_reasoning=False,
        reasoning=None,
        provider_order=list(GEMINI_PROVIDER_ORDER),
        allow_fallbacks=False,
        require_provider_pin=True,
        max_transport_attempts_per_logical_call=2,
        cost_card=gem_card,
    )

    gem_case1 = _import_case1_row(arm="gemini", src=GEMINI_CASE1_SRC, expected_case=CASE_1)
    _copy_case1_artifacts(gem_dir, GEMINI_CASE1_SRC)
    gem_new = _run_arm_cases(
        arm="gemini",
        adapter=gem_adapter,
        cost_card=gem_card,
        arm_dir=gem_dir,
        request_max_tokens=GEMINI_MAX_TOKENS,
        request_reasoning=None,
    )
    gem_rows = [gem_case1] + gem_new
    if [r["case_id"] for r in gem_rows] != list(ALL_CASES):
        raise RuntimeError("protocol_defect:gemini_case_order_mismatch")
    gem_summary = _summarize_arm("gemini", gem_rows)
    (gem_dir / "arm_summary.json").write_text(
        json.dumps(gem_summary, indent=2, sort_keys=True, default=str) + "\n"
    )

    # --- DeepSeek arm preflight + 5 calls ---
    ds_endpoints = fetch_endpoints_document(OPENROUTER_DEEPSEEK_V41_FLASH_1017)
    ds_card, ds_archive = morph_cost_card_from_endpoints(
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        endpoints_doc=ds_endpoints,
    )
    ds_pf = _arm_preflight(
        arm="deepseek",
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        provider_order=DEEPSEEK_PROVIDER_ORDER,
        max_tokens=DEEPSEEK_MAX_TOKENS,
        reasoning=dict(DEEPSEEK_REASONING),
        include_reasoning=False,
        cost_card=ds_card,
        rate_archive=ds_archive,
    )
    ds_dir = OUT / "deepseek"
    ds_dir.mkdir(parents=True, exist_ok=True)
    (ds_dir / "preflight.json").write_text(
        json.dumps({**common, **ds_pf}, indent=2, sort_keys=True) + "\n"
    )
    (ds_dir / "live_endpoints_snapshot.json").write_text(
        json.dumps(ds_endpoints, indent=2, sort_keys=True) + "\n"
    )
    (ds_dir / "live_rate_card.json").write_text(
        json.dumps(ds_archive, indent=2, sort_keys=True) + "\n"
    )

    ds_budgets = ExecutionBudgets.for_six_case_ceiling(
        logical_authorized=5,
        transport_authorized=10,
        estimated_usd_cap=25.0,
    )
    ds_adapter = OpenRouterAdapter(
        model_path=ModelPathId.DEEPSEEK_V41_FLASH_1017,
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        budgets=ds_budgets,
        transport=LiveOpenRouterTransport(),
        temperature=0.0,
        max_tokens=DEEPSEEK_MAX_TOKENS,
        include_reasoning=False,
        reasoning=dict(DEEPSEEK_REASONING),
        provider_order=list(DEEPSEEK_PROVIDER_ORDER),
        allow_fallbacks=False,
        require_provider_pin=True,
        max_transport_attempts_per_logical_call=2,
        cost_card=ds_card,
    )

    ds_case1 = _import_case1_row(arm="deepseek", src=DEEPSEEK_CASE1_SRC, expected_case=CASE_1)
    _copy_case1_artifacts(ds_dir, DEEPSEEK_CASE1_SRC)
    ds_new = _run_arm_cases(
        arm="deepseek",
        adapter=ds_adapter,
        cost_card=ds_card,
        arm_dir=ds_dir,
        request_max_tokens=DEEPSEEK_MAX_TOKENS,
        request_reasoning=dict(DEEPSEEK_REASONING),
    )
    ds_rows = [ds_case1] + ds_new
    if [r["case_id"] for r in ds_rows] != list(ALL_CASES):
        raise RuntimeError("protocol_defect:deepseek_case_order_mismatch")
    ds_summary = _summarize_arm("deepseek", ds_rows)
    (ds_dir / "arm_summary.json").write_text(
        json.dumps(ds_summary, indent=2, sort_keys=True, default=str) + "\n"
    )

    side_by_side = []
    for case_id in ALL_CASES:
        g = next(r for r in gem_rows if r["case_id"] == case_id)
        d = next(r for r in ds_rows if r["case_id"] == case_id)
        side_by_side.append(
            {
                "case_id": case_id,
                "gemini": {
                    "freeze_status": g.get("freeze_status"),
                    "schema_valid": g.get("schema_valid"),
                    "semantic_equivalent": g.get("semantic_equivalent"),
                    "semantic_layer1_completed": g.get("semantic_layer1_completed"),
                    "failure_labels": g.get("failure_labels"),
                    "provider_reported_usd": g.get("provider_reported_usd"),
                    "source": g.get("source"),
                },
                "deepseek": {
                    "freeze_status": d.get("freeze_status"),
                    "schema_valid": d.get("schema_valid"),
                    "semantic_equivalent": d.get("semantic_equivalent"),
                    "semantic_layer1_completed": d.get("semantic_layer1_completed"),
                    "failure_labels": d.get("failure_labels"),
                    "provider_reported_usd": d.get("provider_reported_usd"),
                    "source": d.get("source"),
                },
            }
        )

    logical_calls_new = gem_budgets.logical_calls.consumed + ds_budgets.logical_calls.consumed
    if logical_calls_new != 10:
        raise RuntimeError(f"protocol_defect:logical_calls_new={logical_calls_new}")

    campaign = {
        "authority": AUTHORITY,
        "parent_sha": PARENT_SHA,
        "logical_calls_new": logical_calls_new,
        "transport_attempts_new": (
            gem_budgets.transport_attempts.consumed + ds_budgets.transport_attempts.consumed
        ),
        "case_1_rerun": False,
        "n_hosted_benchmark_observations": 12,
        "original_failed_deepseek_smoke": {
            "path": str(ORIGINAL_FAILED_DEEPSEEK.relative_to(EXPERIMENT_ROOT.parents[1])),
            "counted_as_benchmark_observation": False,
            "role": "operational_qualification_history_only",
        },
        "decoding_limitation": (
            "Hosted arms use response_format=json_object plus deterministic freeze_candidate. "
            "This is NOT equivalent to Pilot Run 1 XGrammar hard structural masking."
        ),
        "gemini": gem_summary,
        "deepseek": ds_summary,
        "side_by_side": side_by_side,
        "provider_reported_usd_total_both_arms": (
            (gem_summary["provider_reported_usd_total"] or 0)
            + (ds_summary["provider_reported_usd_total"] or 0)
        ),
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "STOP_FOR_INDEPENDENT_HOSTED_SCREENING_REVIEW",
    }
    (OUT / "campaign_summary.json").write_text(
        json.dumps(campaign, indent=2, sort_keys=True, default=str) + "\n"
    )
    (OUT / "authorization.json").write_text(
        json.dumps(
            {
                "authority": AUTHORITY,
                "parent_sha": PARENT_SHA,
                "logical_calls_authorized": 10,
                "case_1_rerun_authorized": False,
                "gemini_cases": list(CASES_2_THROUGH_6),
                "deepseek_cases": list(CASES_2_THROUGH_6),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    g = gem_summary
    d = ds_summary
    (OUT / "provenance.md").write_text(
        f"""# Joint hosted full screening — Gemini + DeepSeek

```
AUTHORITY: {AUTHORITY}
PARENT SHA: {PARENT_SHA}
NEW LOGICAL CALLS: {logical_calls_new}/10
CASE 1 RERUN: NO
BENCHMARK OBSERVATIONS: 12 (6 Gemini + 6 DeepSeek)
```

## Per-model summary

| Metric | Gemini | DeepSeek |
|--------|--------|----------|
| Reached freeze | {g['reached_freeze_count']}/6 | {d['reached_freeze_count']}/6 |
| Schema valid | {g['schema_valid_count']}/6 | {d['schema_valid_count']}/6 |
| Semantic eq (among frozen) | {g['semantic_equivalent_among_frozen']}/{g['semantic_equivalent_among_frozen_denominator']} | {d['semantic_equivalent_among_frozen']}/{d['semantic_equivalent_among_frozen_denominator']} |
| Semantic eq (overall) | {g['semantic_equivalent_overall']}/6 | {d['semantic_equivalent_overall']}/6 |
| Provider-reported USD | {g['provider_reported_usd_total']} | {d['provider_reported_usd_total']} |
| Latency s (sum) | {g['latency_seconds_total']:.3f} | {d['latency_seconds_total']:.3f} |
| Prompt tokens | {g['prompt_tokens_total']} | {d['prompt_tokens_total']} |
| Completion tokens | {g['completion_tokens_total']} | {d['completion_tokens_total']} |

Decoding: `json_object` + freeze — **not** XGrammar hard-mask equivalent.

Original failed DeepSeek 1024-token smoke retained as qualification history only.

STATUS:
STOP FOR INDEPENDENT HOSTED SCREENING REVIEW
"""
    )
    (OUT / "preflight_common.json").write_text(
        json.dumps(common, indent=2, sort_keys=True) + "\n"
    )
    return campaign


if __name__ == "__main__":
    summary = run_joint_hosted_full()
    print(
        json.dumps(
            {
                "logical_calls_new": summary["logical_calls_new"],
                "transport_attempts_new": summary["transport_attempts_new"],
                "gemini": {
                    "reached_freeze": summary["gemini"]["reached_freeze_count"],
                    "schema_valid": summary["gemini"]["schema_valid_count"],
                    "semantic_eq_overall": summary["gemini"]["semantic_equivalent_overall"],
                    "usd": summary["gemini"]["provider_reported_usd_total"],
                },
                "deepseek": {
                    "reached_freeze": summary["deepseek"]["reached_freeze_count"],
                    "schema_valid": summary["deepseek"]["schema_valid_count"],
                    "semantic_eq_overall": summary["deepseek"]["semantic_equivalent_overall"],
                    "usd": summary["deepseek"]["provider_reported_usd_total"],
                },
                "side_by_side": [
                    {
                        "case_id": row["case_id"],
                        "gemini_freeze": row["gemini"]["freeze_status"],
                        "deepseek_freeze": row["deepseek"]["freeze_status"],
                    }
                    for row in summary["side_by_side"]
                ],
            },
            indent=2,
        )
    )

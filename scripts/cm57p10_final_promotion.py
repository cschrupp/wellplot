"""CM-57P10 final fresh promotion gate.

The default command is provider-free. Live inference is intentionally withheld
behind explicit authorization and is not part of this implementation slice.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from scripts import cm57p7_fresh_promotion as p7  # noqa: E402
from scripts import cm57p9_runtime_fingerprint as fingerprint  # noqa: E402
from wellplot.agent.code_mode.planner import SemanticPlan  # noqa: E402
from wellplot.agent.providers.base import ModelBackendProtocol  # noqa: E402
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p10_final_promotion_cases.json"
P9C_SUMMARY_PATH = (
    REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P9C-endpoint-provenance-summary.json"
)
OUTPUT_PATH = Path("/tmp/cm57p10-final-promotion-qwen.jsonl")

BASELINE_SHA = "5244db6fc169c78201c1ffcd751c01c0d045b5fd"
EXPERIMENT_VERSION = "CM-57P10"
CORPUS_VERSION = "cm57p10.final-promotion.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
ARMS: tuple[str, ...] = ("P", "RC")
FAMILIES: tuple[str, ...] = (
    "REPORT_ONLY",
    "SINGLE_SECTION_NO_REFERENCE",
    "REFERENCE_REQUIRED",
    "MULTITRACK_SINGLE_SECTION",
    "MULTI_SECTION",
    "MIXED_REPORT_SECTION",
)
Arm = Literal["P", "RC"]
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;]+")
CAPABILITY_IDS = (
    "report.standard",
    "section.log_plot",
    "track.normal",
    "track.reference",
    "track.array",
    "binding.curve",
    "binding.raster",
)
FORBIDDEN_REQUEST_TERMS = (
    "SectionTask",
    "ReportTask",
    "SemanticPlan",
    "capability_ids",
    "expected_sections",
    "expected_report_capabilities",
)

FIXED_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
    "concurrency": 1,
}
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_PROVIDER_BASE_SHA256 = "4c14afc1e6e53faef1ef99266059b7b88b6c4dec4bfb5a4768ca5b36efc3f049"
EXPECTED_PROVIDER_OPENAI_COMPAT_SHA256 = (
    "1409f83cdc6e8ed376f3d1d59102acde06b3e272ce15035adec6cd830723c653"
)
EXPECTED_CAPABILITY_CATALOG_FILE_SHA256 = (
    "2290d9656bf69cea130e97c39da4c572449a0bbb3bcd6aff61463f25b2702cac"
)
EXPECTED_CAPABILITY_CATALOG_SHA256 = (
    "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37"
)
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
EXPECTED_SCHEMA_SHA256 = "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3"


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text."""
    return sha256_bytes(value.encode("utf-8"))


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact."""
    return sha256_bytes(path.read_bytes())


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _normalized_request(request: str) -> str:
    """Normalize request text for corpus disjointness checks."""
    return " ".join(request.casefold().split())


def _fixed_source_summary_sha() -> str:
    """Return the frozen production-safe source-summary hash."""
    return sha256_text(p5.canonical_json(p5.FIXED_SOURCE_SUMMARY))


def _prompt_sha256(arm: Arm) -> str:
    """Return the frozen system-prompt hash for one arm."""
    return sha256_text(p5.composed_prompt(arm))


def _schema_sha256() -> str:
    """Return the frozen production SemanticPlan schema hash."""
    return p7.p6.schema_sha256(SemanticPlan)


def _previous_request_hashes() -> set[str]:
    """Return request hashes from all earlier holdout corpora."""
    previous = p5.load_case_definitions()
    p7_cases = p7.load_case_definitions()
    return {sha256_text(str(case["request"])) for case in (*previous, *p7_cases)}


def load_case_definitions(path: Path = CASE_PATH) -> tuple[dict[str, object], ...]:
    """Load and validate the final 24-case fresh promotion corpus."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != CORPUS_VERSION:
        raise ValueError("Unexpected CM-57P10 corpus version.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("CM-57P10 requires exactly 24 cases.")
    registry = create_builtin_registry()
    previous_ids = {
        str(case["case_id"]) for case in (*p5.load_case_definitions(), *p7.load_case_definitions())
    }
    previous_requests = {
        _normalized_request(str(case["request"]))
        for case in (*p5.load_case_definitions(), *p7.load_case_definitions())
    }
    previous_hashes = _previous_request_hashes()
    seen_ids: set[str] = set()
    seen_requests: set[str] = set()
    seen_hashes: set[str] = set()
    family_counts: Counter[str] = Counter()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("CM-57P10 cases must be objects.")
        case_id = case.get("case_id")
        family = case.get("family")
        request = case.get("request")
        report = case.get("expected_report_capabilities")
        sections = case.get("expected_sections")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("CM-57P10 case IDs must be unique non-empty strings.")
        if case_id in previous_ids:
            raise ValueError(f"Case ID is not fresh: {case_id!r}.")
        if family not in FAMILIES:
            raise ValueError(f"Unknown CM-57P10 family: {family!r}.")
        if not isinstance(request, str) or not request.strip() or PATH_RE.search(request):
            raise ValueError(f"Case {case_id!r} has unsafe request text.")
        normalized = _normalized_request(request)
        request_hash = sha256_text(request)
        if normalized in seen_requests or normalized in previous_requests:
            raise ValueError(f"Case {case_id!r} reuses normalized request text.")
        if request_hash in seen_hashes or request_hash in previous_hashes:
            raise ValueError(f"Case {case_id!r} reuses a historical request hash.")
        if any(term.casefold() in request.casefold() for term in FORBIDDEN_REQUEST_TERMS):
            raise ValueError(f"Case {case_id!r} leaks planner vocabulary.")
        if any(value.casefold() in request.casefold() for value in CAPABILITY_IDS):
            raise ValueError(f"Case {case_id!r} leaks capability IDs.")
        if not isinstance(report, list) or not all(isinstance(value, str) for value in report):
            raise ValueError(f"Case {case_id!r} has invalid report gold.")
        if not isinstance(sections, list) or not all(isinstance(value, list) for value in sections):
            raise ValueError(f"Case {case_id!r} has invalid section gold.")
        if case.get("expected_unresolved_count") != 0:
            raise ValueError("CM-57P10 permits only zero unresolved requirements.")
        p5._validate_report_gold(report, registry, case_id)
        for section in sections:
            p5._validate_section_gold(section, registry, case_id)
        seen_ids.add(case_id)
        seen_requests.add(normalized)
        seen_hashes.add(request_hash)
        family_counts[str(family)] += 1
    if family_counts != Counter(dict.fromkeys(FAMILIES, 4)):
        raise ValueError(f"CM-57P10 family distribution is invalid: {family_counts!r}.")
    return tuple(cases)


def frozen_provenance() -> dict[str, object]:
    """Return immutable provenance for future P10 rows."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "planner_source_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/planner.py"
        ),
        "provider_base_sha256": artifact_sha256(REPO_ROOT / "src/wellplot/agent/providers/base.py"),
        "provider_openai_compat_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/providers/openai_compat_v2.py"
        ),
        "capability_catalog_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/capabilities/builtins.py"
        ),
        "P_prompt_sha256": _prompt_sha256("P"),
        "RC_prompt_sha256": _prompt_sha256("RC"),
        "response_schema_sha256": _schema_sha256(),
        "source_summary_sha256": _fixed_source_summary_sha(),
        "execution_controls": dict(FIXED_EXECUTION_CONTROLS),
    }


def _arm(row: dict[str, object], arm: str) -> dict[str, object]:
    """Return one bounded arm result."""
    arms = row.get("arms")
    value = arms.get(arm) if isinstance(arms, dict) else None
    return value if isinstance(value, dict) else {}


def _facts(row: dict[str, object], arm: str) -> dict[str, object] | None:
    """Return final facts when semantic evaluation completed."""
    value = _arm(row, arm).get("final_work_unit_facts")
    return value if isinstance(value, dict) else None


def _reference_required(case: dict[str, object]) -> bool:
    """Return whether any gold section requires a reference track."""
    return any("track.reference" in section for section in case["expected_sections"])


def _reference_present(facts: dict[str, object] | None) -> bool | None:
    """Project actual reference presence from established section facts."""
    if facts is None:
        return None
    return any(
        "track.reference" in signature
        for signature in facts.get("section_capability_signatures", [])
    )


def _attempt_signature(result: dict[str, object]) -> tuple[object, ...]:
    """Return bounded facts used for case-level reproducibility."""
    return (
        bool(result.get("final_contract_ok")),
        canonical_json(result.get("final_work_unit_facts")),
        result.get("final_classification"),
        result.get("final_error_code"),
        bool(result.get("final_planner_success")),
        bool(result.get("provider_infrastructure_failure")),
    )


def _case_arm_status(rows: list[dict[str, object]], case_id: str, arm: Arm) -> str:
    """Classify two attempts for one case and arm."""
    case_rows = sorted(
        (row for row in rows if row.get("case_id") == case_id),
        key=lambda row: int(row.get("attempt_index", -1)),
    )
    if len(case_rows) != ATTEMPTS:
        return "UNAVAILABLE"
    results = [_arm(row, arm) for row in case_rows]
    if _attempt_signature(results[0]) != _attempt_signature(results[1]):
        return "UNSTABLE"
    return "STABLE_PASS" if bool(results[0].get("final_contract_ok")) else "STABLE_FAIL"


def case_arm_statuses(
    rows: list[dict[str, object]], cases: tuple[dict[str, object], ...]
) -> dict[str, dict[str, str]]:
    """Return stable pass/fail/unstable status for every case and arm."""
    return {
        str(case["case_id"]): {
            arm: _case_arm_status(rows, str(case["case_id"]), arm) for arm in ARMS
        }
        for case in cases
    }


def _reference_safety(
    rows: list[dict[str, object]], cases: tuple[dict[str, object], ...]
) -> dict[str, int]:
    """Count reference-track violations across all RC attempts."""
    by_id = {str(case["case_id"]): case for case in cases}
    unexpected = missing = 0
    for row in rows:
        case = by_id.get(str(row.get("case_id")))
        if case is None:
            continue
        present = _reference_present(_facts(row, "RC"))
        if present is None:
            continue
        if _reference_required(case) and not present:
            missing += 1
        if not _reference_required(case) and present:
            unexpected += 1
    return {
        "unexpected_reference": unexpected,
        "missing_required_reference": missing,
    }


def _structural_safety(rows: list[dict[str, object]]) -> dict[str, int]:
    """Count protected RC structural violations."""
    parent = duplicate = 0
    for row in rows:
        facts = _facts(row, "RC")
        if facts is None:
            continue
        parent += not bool(facts.get("parent_closure_valid"))
        duplicate += bool(facts.get("duplicate_capability_type"))
    return {
        "parent_closure_invalid": parent,
        "duplicate_capability_type": duplicate,
    }


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on exact rows, provenance, prompts, schema, and controls."""
    reasons: set[str] = set()
    expected_ids = {str(case["case_id"]) for case in cases}
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.add("wrong_row_count")
    if len(set(pairs)) != len(pairs):
        reasons.add("duplicate_case_attempt")
    if {case_id for case_id, _ in pairs} != expected_ids:
        reasons.add("case_set_mismatch")
    by_case: dict[str, set[object]] = {}
    for case_id, attempt in pairs:
        by_case.setdefault(case_id, set()).add(attempt)
    if any(attempts != set(range(ATTEMPTS)) for attempts in by_case.values()):
        reasons.add("attempt_index_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if None in checkpoints or len(checkpoints) != 1:
        reasons.add("checkpoint_missing_or_mixed")
    elif expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.add("checkpoint_mismatch")
    expected = {str(case["case_id"]): case for case in cases}
    provenance = frozen_provenance()
    for row in rows:
        case = expected.get(str(row.get("case_id")))
        if case is None:
            continue
        if not isinstance(row.get("arms"), dict) or set(row["arms"]) != set(ARMS):
            reasons.add("arm_set_mismatch")
        if row.get("family") != case["family"]:
            reasons.add("family_mismatch")
        for field, value in provenance.items():
            if row.get(field) != value:
                reasons.add(f"{field}_mismatch")
        if row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.add("request_hash_mismatch")
        if row.get("expected_report_capabilities") != case["expected_report_capabilities"]:
            reasons.add("report_gold_mismatch")
        if row.get("expected_sections") != case["expected_sections"]:
            reasons.add("section_gold_mismatch")
        if row.get("expected_unresolved_count") != case["expected_unresolved_count"]:
            reasons.add("unresolved_gold_mismatch")
        for arm in ARMS:
            result = _arm(row, arm)
            if result.get("prompt_sha256") != _prompt_sha256(arm):
                reasons.add(f"{arm}_prompt_mismatch")
            if result.get("response_schema_sha256") != _schema_sha256():
                reasons.add(f"{arm}_schema_mismatch")
            if int(result.get("program_calls", 0)) != 0:
                reasons.add("worker_program_call")
    return not reasons, sorted(reasons)


def _endpoint_provenance_status(
    pre: dict[str, object] | None, post: dict[str, object] | None
) -> tuple[bool, list[str]]:
    """Validate and compare normalized PRE/POST endpoint identity."""
    if pre is None or post is None:
        return False, ["endpoint_fingerprint_missing"]
    pre_valid, pre_reasons = fingerprint.validate_endpoint_fingerprint_v2(pre)
    post_valid, post_reasons = fingerprint.validate_endpoint_fingerprint_v2(post)
    reasons = [f"pre_{reason}" for reason in pre_reasons]
    reasons.extend(f"post_{reason}" for reason in post_reasons)
    reasons.extend(
        f"endpoint_{reason}" for reason in fingerprint.compare_endpoint_fingerprints_v2(pre, post)
    )
    return pre_valid and post_valid and not reasons, sorted(set(reasons))


def decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
    p9c_stable: bool = False,
) -> str:
    """Apply the final promotion decision without interpreting bad output as infra."""
    complete, _ = population_integrity(rows, cases, expected_checkpoint=expected_checkpoint)
    endpoint_ok, _ = _endpoint_provenance_status(pre_fingerprint, post_fingerprint)
    if not complete or not endpoint_ok or not p9c_stable:
        return "INCONCLUSIVE_FINAL_PROMOTION_EVALUATION"
    if any(
        bool(_arm(row, arm).get("provider_infrastructure_failure")) for row in rows for arm in ARMS
    ):
        return "INCONCLUSIVE_FINAL_PROMOTION_EVALUATION"
    statuses = case_arm_statuses(rows, cases)
    rc_unstable = sum(status["RC"] == "UNSTABLE" for status in statuses.values())
    if rc_unstable:
        return "FINAL_PROMOTION_RC_REJECTED"
    protected_regressions = sum(
        status["P"] == "STABLE_PASS" and status["RC"] != "STABLE_PASS"
        for status in statuses.values()
    )
    gains = sum(
        status["P"] == "STABLE_FAIL" and status["RC"] == "STABLE_PASS"
        for status in statuses.values()
    )
    p_passes = sum(status["P"] == "STABLE_PASS" for status in statuses.values())
    rc_passes = sum(status["RC"] == "STABLE_PASS" for status in statuses.values())
    reference = _reference_safety(rows, cases)
    structural = _structural_safety(rows)
    if (
        protected_regressions
        or gains < 3
        or rc_passes < p_passes + 3
        or rc_passes < 18
        or reference["unexpected_reference"]
        or reference["missing_required_reference"]
        or structural["parent_closure_invalid"]
        or structural["duplicate_capability_type"]
    ):
        return "FINAL_PROMOTION_RC_REJECTED"
    return "FINAL_PROMOTION_RC_ACCEPTED"


def _p9c_summary() -> dict[str, object] | None:
    """Load the reviewed normalized-provenance result when available."""
    if not P9C_SUMMARY_PATH.exists():
        return None
    value = json.loads(P9C_SUMMARY_PATH.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _arm_metrics(rows: list[dict[str, object]], arm: Arm) -> dict[str, int]:
    """Aggregate bounded metrics for one arm."""
    results = [_arm(row, arm) for row in rows]
    return {
        "planner_executions": len(results),
        "provider_calls": sum(int(result.get("provider_calls", 0)) for result in results),
        "final_contract_passes": sum(bool(result.get("final_contract_ok")) for result in results),
        "semantic_corrections": sum(
            bool(result.get("semantic_correction_used")) for result in results
        ),
        "invalid_response_retries": sum(
            bool(result.get("invalid_response_retry_used")) for result in results
        ),
        "terminal_failures": sum(
            not bool(result.get("final_planner_success")) for result in results
        ),
        "provider_infrastructure_failures": sum(
            bool(result.get("provider_infrastructure_failure")) for result in results
        ),
        "program_calls": sum(int(result.get("program_calls", 0)) for result in results),
    }


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build bounded final evidence without retaining provider responses."""
    complete, reasons = population_integrity(rows, cases, expected_checkpoint=authorized_checkpoint)
    p9c = _p9c_summary()
    p9c_stable = bool(p9c and p9c.get("decision") == "ENDPOINT_PROVENANCE_NORMALIZED_STABLE")
    statuses = case_arm_statuses(rows, cases)
    reference = _reference_safety(rows, cases)
    structural = _structural_safety(rows)
    endpoint_ok, endpoint_reasons = _endpoint_provenance_status(pre_fingerprint, post_fingerprint)
    final_decision = decision(
        rows,
        cases,
        expected_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre_fingerprint,
        post_fingerprint=post_fingerprint,
        p9c_stable=p9c_stable,
    )
    p_passes = sum(status["P"] == "STABLE_PASS" for status in statuses.values())
    rc_passes = sum(status["RC"] == "STABLE_PASS" for status in statuses.values())
    gains = sum(
        status["P"] == "STABLE_FAIL" and status["RC"] == "STABLE_PASS"
        for status in statuses.values()
    )
    protected = sum(
        status["P"] == "STABLE_PASS" and status["RC"] != "STABLE_PASS"
        for status in statuses.values()
    )
    family_results = {
        family: {
            arm: Counter(
                statuses[str(case["case_id"])][arm] for case in cases if case["family"] == family
            )
            for arm in ARMS
        }
        for family in FAMILIES
    }
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_checkpoint": authorized_checkpoint,
        "decision": final_decision,
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "families": len(FAMILIES),
            "attempts_per_case": ATTEMPTS,
            "planner_executions": len(cases) * ATTEMPTS * len(ARMS),
            "provider_calls": sum(
                int(_arm(row, arm).get("provider_calls", 0)) for row in rows for arm in ARMS
            ),
            "worker_program_calls": sum(
                int(_arm(row, arm).get("program_calls", 0)) for row in rows for arm in ARMS
            ),
            "complete": complete,
            "reasons": reasons,
        },
        "p9c": {
            "decision_bearing": p9c.get("decision") if p9c else None,
            "summary_sha256": (
                artifact_sha256(P9C_SUMMARY_PATH) if P9C_SUMMARY_PATH.exists() else None
            ),
        },
        "endpoint_provenance": {
            "valid_and_equal": endpoint_ok,
            "reasons": endpoint_reasons,
            "pre_normalized_identity_sha256": (
                pre_fingerprint.get("normalized_identity_sha256") if pre_fingerprint else None
            ),
            "post_normalized_identity_sha256": (
                post_fingerprint.get("normalized_identity_sha256") if post_fingerprint else None
            ),
            "pre_raw_model_catalog_sha256": (
                pre_fingerprint.get("raw_model_catalog_sha256") if pre_fingerprint else None
            ),
            "post_raw_model_catalog_sha256": (
                post_fingerprint.get("raw_model_catalog_sha256") if post_fingerprint else None
            ),
        },
        "arm_metrics": {arm: _arm_metrics(rows, arm) for arm in ARMS},
        "case_arm_statuses": statuses,
        "family_results": family_results,
        "promotion_metrics": {
            "P_stable_passes": p_passes,
            "RC_stable_passes": rc_passes,
            "candidate_gains": gains,
            "protected_regressions": protected,
            "RC_unstable_cases": sum(status["RC"] == "UNSTABLE" for status in statuses.values()),
        },
        "reference_safety": reference,
        "structural_safety": structural,
        "controls": dict(FIXED_EXECUTION_CONTROLS),
        "prompt_hashes": {arm: _prompt_sha256(arm) for arm in ARMS},
        "response_schema_sha256": _schema_sha256(),
        "production_adoption": "NOT_AUTHORIZED",
        "CM57P_closed_after_valid_result": False,
        "CM57D": "BLOCKED",
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require exact reviewed bytes before any future provider construction."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P10 checkout does not match the authorized checkpoint.")
    guarded = (
        "scripts/cm57p10_final_promotion.py",
        "tests/fixtures/typed_worker/cm57p10_final_promotion_cases.json",
        "scripts/cm57p9_runtime_fingerprint.py",
        "docs/evaluations/agent-code-mode/CM-57P9C-endpoint-provenance-summary.json",
        "scripts/cm57p5_fresh_holdout.py",
        "scripts/cm57p7_fresh_promotion.py",
        "src/wellplot/agent/code_mode/planner.py",
        "src/wellplot/agent/providers/base.py",
        "src/wellplot/agent/providers/openai_compat_v2.py",
        "src/wellplot/capabilities/builtins.py",
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if not path.exists() or path.read_bytes() != _git_output(
            "show", f"{checkpoint}:{relative_path}"
        ):
            raise RuntimeError(f"CM-57P10 guarded artifact drifted: {relative_path}")


def verify_frozen_contract(*, require_p9c: bool = False) -> dict[str, object]:
    """Verify the fresh corpus and all frozen provider-facing artifacts."""
    cases = load_case_definitions()
    if require_p9c:
        p9c = _p9c_summary()
        if not p9c or p9c.get("decision") != "ENDPOINT_PROVENANCE_NORMALIZED_STABLE":
            raise RuntimeError("CM-57P10 requires a stable CM-57P9C result.")
    artifact_checks = {
        REPO_ROOT / "src/wellplot/agent/code_mode/planner.py": EXPECTED_PLANNER_SOURCE_SHA256,
        REPO_ROOT / "src/wellplot/agent/providers/base.py": EXPECTED_PROVIDER_BASE_SHA256,
        REPO_ROOT / "src/wellplot/agent/providers/openai_compat_v2.py": (
            EXPECTED_PROVIDER_OPENAI_COMPAT_SHA256
        ),
        REPO_ROOT
        / "src/wellplot/capabilities/builtins.py": EXPECTED_CAPABILITY_CATALOG_FILE_SHA256,
    }
    for path, expected in artifact_checks.items():
        if artifact_sha256(path) != expected:
            raise RuntimeError(f"CM-57P10 frozen artifact drifted: {path}")
    if p5._catalog_sha256() != EXPECTED_CAPABILITY_CATALOG_SHA256:
        raise RuntimeError("CM-57P10 capability catalogue drifted.")
    if _fixed_source_summary_sha() != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("CM-57P10 source summary drifted.")
    if _prompt_sha256("P") != "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18":
        raise RuntimeError("CM-57P10 production prompt drifted.")
    if _prompt_sha256("RC") != "e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34":
        raise RuntimeError("CM-57P10 RC prompt drifted.")
    if _schema_sha256() != EXPECTED_SCHEMA_SHA256:
        raise RuntimeError("CM-57P10 response schema drifted.")
    return {
        "cases": len(cases),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "P_prompt_sha256": _prompt_sha256("P"),
        "RC_prompt_sha256": _prompt_sha256("RC"),
        "response_schema_sha256": _schema_sha256(),
        "source_summary_sha256": _fixed_source_summary_sha(),
        "p9c_summary_sha256": artifact_sha256(P9C_SUMMARY_PATH)
        if P9C_SUMMARY_PATH.exists()
        else None,
    }


def prelive_report() -> dict[str, object]:
    """Run provider-free validation and describe the withheld final matrix."""
    contract = verify_frozen_contract()
    cases = load_case_definitions()
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "provider_calls": 0,
        "worker_program_calls": 0,
        "production_changes": 0,
        "live_inference": "NOT_STARTED",
        "production_adoption": "NOT_AUTHORIZED",
        "CM57D": "BLOCKED",
        "future_controls": {**FIXED_EXECUTION_CONTROLS, "attempts": ATTEMPTS},
        "future_population": {
            "cases": len(cases),
            "families": len(FAMILIES),
            "cases_per_family": 4,
            "arms": list(ARMS),
            "planner_executions": len(cases) * ATTEMPTS * len(ARMS),
            "provider_calls_min": len(cases) * ATTEMPTS * len(ARMS),
            "provider_calls_max": len(cases) * ATTEMPTS * len(ARMS) * 2,
        },
        **contract,
    }


def _api_key(args: argparse.Namespace) -> str:
    """Resolve the API key without retaining it in evidence."""
    value = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        path = Path(args.api_key_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        value = value or path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("No CM-57P10 API key configured.")
    return value


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the production provider only after all live guards pass."""
    from openai import AsyncOpenAI  # noqa: I001
    from wellplot.agent.providers.openai_compat_v2 import (  # noqa: I001
        OpenAICompatibleBackendV2,
    )

    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=_api_key(args), base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def run_shared_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str | None,
) -> dict[str, object]:
    """Run one P then RC pair against the same case and backend."""
    row = {
        **frozen_provenance(),
        "authorized_checkpoint": authorized_checkpoint,
        "case_id": case["case_id"],
        "family": case["family"],
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(str(case["request"])),
        "expected_report_capabilities": list(case["expected_report_capabilities"]),
        "expected_sections": [list(section) for section in case["expected_sections"]],
        "expected_unresolved_count": case["expected_unresolved_count"],
        "arms": {},
    }
    for arm in ARMS:
        result = await p5.run_arm(
            case,
            arm=arm,
            delegate=delegate,
            registry=registry,
        )
        result["response_schema_sha256"] = _schema_sha256()
        row["arms"][arm] = result
    return row


def _ensure_empty_evidence(path: Path) -> None:
    """Reject an existing non-empty population before provider construction."""
    if path.exists() and path.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {path}.")


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the final frozen P then RC matrix once and flush each row."""
    _ensure_empty_evidence(OUTPUT_PATH)
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract(require_p9c=True)
    api_key = _api_key(args)
    pre = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=api_key,
    )
    Path(args.endpoint_fingerprint_pre).write_text(
        json.dumps(pre, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    cases = load_case_definitions()
    registry = create_builtin_registry()
    backend = _provider_configuration(args)
    rows: list[dict[str, object]] = []
    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        for case in cases:
            for attempt_index in range(ATTEMPTS):
                row = await run_shared_row(
                    case,
                    attempt_index=attempt_index,
                    delegate=backend,
                    registry=registry,
                    authorized_checkpoint=checkpoint,
                )
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
    post = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=api_key,
    )
    Path(args.endpoint_fingerprint_post).write_text(
        json.dumps(post, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "MATRIX_COMPLETE", "rows": len(rows)}, indent=2))


def _load_fingerprint(path: Path) -> dict[str, object]:
    """Load and validate one v2 endpoint fingerprint."""
    value = json.loads(path.read_text(encoding="utf-8"))
    valid, reasons = fingerprint.validate_endpoint_fingerprint_v2(value)
    if not valid:
        raise RuntimeError(f"Invalid endpoint fingerprint: {', '.join(reasons)}")
    return value


def finalize(
    *,
    checkpoint: str,
    evidence_path: Path,
    pre_path: Path,
    post_path: Path,
) -> dict[str, object]:
    """Finalize P10 evidence without constructing a provider."""
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract(require_p9c=True)
    rows = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return summarize_population(
        rows,
        load_case_definitions(),
        authorized_checkpoint=checkpoint,
        pre_fingerprint=_load_fingerprint(pre_path),
        post_fingerprint=_load_fingerprint(post_path),
    )


def _parser() -> argparse.ArgumentParser:
    """Build provider-free, live, and finalization CLI modes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    parser.add_argument("--evidence", default=str(OUTPUT_PATH))
    parser.add_argument("--endpoint-fingerprint-pre", default="/tmp/cm57p10-endpoint-pre.json")
    parser.add_argument("--endpoint-fingerprint-post", default="/tmp/cm57p10-endpoint-post.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run provider-free validation unless explicit future mode is selected."""
    args = _parser().parse_args(argv)
    if args.finalize:
        if not args.authorized_checkpoint:
            raise SystemExit("CM-57P10 finalization requires --authorized-checkpoint.")
        print(
            json.dumps(
                finalize(
                    checkpoint=args.authorized_checkpoint,
                    evidence_path=Path(args.evidence),
                    pre_path=Path(args.endpoint_fingerprint_pre),
                    post_path=Path(args.endpoint_fingerprint_post),
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.live_authorized:
        print(json.dumps(prelive_report(), indent=2, sort_keys=True))
        return 0
    if not args.authorized_checkpoint or not args.base_url:
        raise SystemExit("CM-57P10 live mode requires checkpoint and base URL.")
    asyncio.run(_run_live(args, args.authorized_checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

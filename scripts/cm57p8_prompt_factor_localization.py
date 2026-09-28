"""CM-57P8 provider-free prompt-factor localization harness.

P8 isolates the report-boundary and section-composition prompt factors while
running the production SemanticPlanner and production response schema. The
default command performs deterministic validation only; live execution is
explicitly gated for a later authorization.
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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p4_prompt_interaction_bisect as p4  # noqa: E402
from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from scripts import cm57p7_fresh_promotion as p7  # noqa: E402
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
    PlannerSemanticFailure,
    SemanticPlan,
    SemanticPlanner,
)
from wellplot.agent.providers.base import (  # noqa: E402
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p8_prompt_factor_cases.json"
P7_CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json"
P7_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p7_fresh_promotion.py"
P7_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P7-live-summary.json"
P5_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p5_fresh_holdout.py"
P4_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p4_prompt_interaction_bisect.py"
OUTPUT_PATH = Path("/tmp/cm57p8-prompt-factor-qwen.jsonl")
P7_RAW_PATH = Path("/tmp/cm57p7-fresh-promotion-qwen.jsonl")

BASELINE_SHA = "ac68fcdc5ec527aa0be4007e4188bdfda1e1c3ac"
EXPERIMENT_VERSION = "CM-57P8"
MANIFEST_VERSION = "cm57p8.prompt-factor.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
ARMS: tuple[str, ...] = ("P", "R", "C", "RC")
Arm = Literal["P", "R", "C", "RC"]
SCHEMA_TARGETS = {"p7-separated-curves-13", "p7-temperature-image-pair-12"}
PROTECTED_REFERENCE_TARGET = "p7-dossier-gamma-17"
POSITIVE_REFERENCE_CONTROLS = {
    "p7-depth-conductivity-06",
    "p7-reference-density-image-10",
    "p7-temperature-image-pair-12",
}

EXPECTED_P7_CORPUS_SHA256 = "4aebee0d2734cb272c6ae002aec277e58427dd5dce44e38e5fdf1a14a4dccd12"
EXPECTED_P7_RAW_SHA256 = "b4cb75aaf6a5ffe8c7f88c6e730d32247d973ea974269132a76b814633ff4d2f"
EXPECTED_P7_SCRIPT_SHA256 = "52809176e6fbe75cf30cf419af15943e7c98e0ccfbf7646a85bdd445b0d6f0a8"
EXPECTED_P7_SUMMARY_SHA256 = "c10e909384a6a1d75f11d74979a3804a6f13b8505e56de5a638af3a29032300c"
EXPECTED_P5_SCRIPT_SHA256 = "3170c970d2ad4298f87c09cb106237d015356e4a5854095e3f889ba139bc600e"
EXPECTED_P4_SCRIPT_SHA256 = "fe7684ff610a14151784cd4272b65ba45e91b56c54b3eda2230e4fff6d2a9693"
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_PROVIDER_BASE_SHA256 = "4c14afc1e6e53faef1ef99266059b7b88b6c4dec4bfb5a4768ca5b36efc3f049"
EXPECTED_CAPABILITY_BASE_SHA256 = "5a34859a54b4a34b8f079995c348ababb83e8cdf3bf0d8136dfa6636bd86b052"
EXPECTED_CAPABILITY_REGISTRY_SHA256 = (
    "7b8029020b21a6bc83a2373443791f60d8cd6250d7336f9e5ae7173078ea0314"
)
EXPECTED_BUILTINS_SHA256 = "2290d9656bf69cea130e97c39da4c572449a0bbb3bcd6aff61463f25b2702cac"
EXPECTED_BASE_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_R_INSTRUCTION_SHA256 = "12fd2c40e407cb7d5d0e21effd66493e20e99468e3a97b89ac0186b40648c5b5"
EXPECTED_C_INSTRUCTION_SHA256 = "b69c47063b6da13e4f5857609708efe0becc901b989a1a65c503dd277cdc8205"
EXPECTED_R_PROMPT_SHA256 = "fe8db9c9cba4cf7bf13d79c3e838eaa53e19770fbf6dd764cdcf93020008c563"
EXPECTED_C_PROMPT_SHA256 = "b140a019889502f247335e34aee6283e0b06848957d9f89f5755170967e4a85e"
EXPECTED_RC_PROMPT_SHA256 = "e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34"
EXPECTED_SCHEMA_SHA256 = "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3"
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")

REPORT_BOUNDARY_INSTRUCTION = p4.REPORT_BOUNDARY_INSTRUCTION
SECTION_COMPOSITION_INSTRUCTION = p4.SECTION_COMPOSITION_INSTRUCTION
FIXED_SOURCE_SUMMARY = p5.FIXED_SOURCE_SUMMARY
FIXED_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
}


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text."""
    return sha256_bytes(value.encode("utf-8"))


def artifact_sha256(path: Path) -> str:
    """Hash an artifact by exact bytes."""
    return sha256_bytes(path.read_bytes())


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def composed_prompt(arm: Arm) -> str:
    """Return one of the four exact factorial prompt compositions."""
    if arm == "P":
        return _PLANNER_SYSTEM_PROMPT
    if arm == "R":
        return p4.composed_prompt("R")
    if arm == "C":
        return _PLANNER_SYSTEM_PROMPT + "\n" + SECTION_COMPOSITION_INSTRUCTION
    return p4.composed_prompt("RC")


PROMPT_SHA256 = {arm: sha256_text(composed_prompt(arm)) for arm in ARMS}


def _gold_sha(case: dict[str, object]) -> str:
    """Hash the P7 gold fields without copying them into the P8 manifest."""
    gold = {
        "family": case["family"],
        "expected_report_capabilities": case["expected_report_capabilities"],
        "expected_sections": case["expected_sections"],
        "expected_unresolved_count": case["expected_unresolved_count"],
    }
    return sha256_text(canonical_json(gold))


def _schema_sha256() -> str:
    """Return the production SemanticPlan schema hash."""
    return p7.p6.schema_sha256(SemanticPlan)


def _registry_ids(registry: CapabilityRegistry) -> set[str]:
    """Return canonical capability IDs from a registry."""
    return {spec.capability_id for spec in registry}


def load_manifest() -> tuple[dict[str, object], ...]:
    """Load the compact P8 manifest and resolve its cases from frozen P7."""
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != MANIFEST_VERSION:
        raise ValueError("Unexpected CM-57P8 manifest version.")
    if payload.get("p7_corpus_sha256") != EXPECTED_P7_CORPUS_SHA256:
        raise ValueError("CM-57P8 P7 corpus hash is incorrect.")
    if payload.get("p7_raw_sha256") != EXPECTED_P7_RAW_SHA256:
        raise ValueError("CM-57P8 P7 raw evidence hash is incorrect.")
    selected = payload.get("cases")
    if not isinstance(selected, list) or len(selected) != 12:
        raise ValueError("CM-57P8 requires exactly 12 selected P7 cases.")
    p7_cases = {str(case["case_id"]): case for case in p7.load_case_definitions(P7_CASE_PATH)}
    manifest_ids: set[str] = set()
    resolved: list[dict[str, object]] = []
    for item in selected:
        if not isinstance(item, dict):
            raise ValueError("CM-57P8 manifest entries must be objects.")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or case_id in manifest_ids or case_id not in p7_cases:
            raise ValueError(f"Invalid or duplicate CM-57P8 case: {case_id!r}.")
        case = p7_cases[case_id]
        if item.get("request_sha256") != sha256_text(str(case["request"])):
            raise ValueError(f"Request hash drift for {case_id!r}.")
        if item.get("gold_sha256") != _gold_sha(case):
            raise ValueError(f"Gold hash drift for {case_id!r}.")
        if not isinstance(item.get("role"), str) or not isinstance(item.get("historical"), dict):
            raise ValueError(f"Missing bounded anchor data for {case_id!r}.")
        for attempt in range(ATTEMPTS):
            anchor = item["historical"].get(str(attempt))
            if not isinstance(anchor, dict) or set(anchor) != {"P", "RC"}:
                raise ValueError(
                    f"Historical P/RC anchor missing for {case_id!r} attempt {attempt}."
                )
        resolved.append({**case, "role": item["role"], "historical": item["historical"]})
        manifest_ids.add(case_id)
    return tuple(resolved)


def derive_historical_anchors(
    raw_path: Path = P7_RAW_PATH,
) -> dict[tuple[str, int], dict[str, object]]:
    """Derive bounded P/RC anchors only from the verified P7 raw artifact."""
    if not raw_path.exists() or artifact_sha256(raw_path) != EXPECTED_P7_RAW_SHA256:
        raise RuntimeError("CM-57P8 requires the exact verified P7 raw evidence SHA.")
    rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 48:
        raise RuntimeError("CM-57P8 requires exactly 48 P7 raw rows for derivation.")
    selected_ids = {str(case["case_id"]) for case in load_manifest()}
    anchors: dict[tuple[str, int], dict[str, object]] = {}
    for row in rows:
        key = (str(row["case_id"]), int(row["attempt_index"]))
        if key[0] not in selected_ids:
            continue
        anchors[key] = {
            arm: {
                field: row["arms"][arm].get(field)
                for field in (
                    "final_planner_success",
                    "final_classification",
                    "final_error_code",
                    "provider_calls",
                    "call_trace",
                )
            }
            for arm in ("P", "RC")
        }
    if len(anchors) != len(selected_ids) * ATTEMPTS:
        raise RuntimeError("CM-57P8 selected P7 anchor population is incomplete.")
    return anchors


def _frozen_provenance() -> dict[str, object]:
    """Return provenance placed on every future live row."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "manifest_sha256": artifact_sha256(MANIFEST_PATH),
        "p7_corpus_sha256": EXPECTED_P7_CORPUS_SHA256,
        "p7_raw_sha256": EXPECTED_P7_RAW_SHA256,
        "p7_script_sha256": EXPECTED_P7_SCRIPT_SHA256,
        "p7_summary_sha256": EXPECTED_P7_SUMMARY_SHA256,
        "p5_script_sha256": EXPECTED_P5_SCRIPT_SHA256,
        "p4_script_sha256": EXPECTED_P4_SCRIPT_SHA256,
        "planner_source_sha256": EXPECTED_PLANNER_SOURCE_SHA256,
        "provider_base_sha256": EXPECTED_PROVIDER_BASE_SHA256,
        "capability_base_sha256": EXPECTED_CAPABILITY_BASE_SHA256,
        "capability_registry_sha256": EXPECTED_CAPABILITY_REGISTRY_SHA256,
        "builtins_sha256": EXPECTED_BUILTINS_SHA256,
        "base_prompt_sha256": EXPECTED_BASE_PROMPT_SHA256,
        "report_instruction_sha256": EXPECTED_R_INSTRUCTION_SHA256,
        "section_instruction_sha256": EXPECTED_C_INSTRUCTION_SHA256,
        "P_prompt_sha256": PROMPT_SHA256["P"],
        "R_prompt_sha256": PROMPT_SHA256["R"],
        "C_prompt_sha256": PROMPT_SHA256["C"],
        "RC_prompt_sha256": PROMPT_SHA256["RC"],
        "production_schema_sha256": _schema_sha256(),
        "source_summary_sha256": sha256_text(canonical_json(FIXED_SOURCE_SUMMARY)),
        "execution_controls": dict(FIXED_EXECUTION_CONTROLS),
    }


@dataclass
class PromptFactorBackend(ModelBackendProtocol):
    """Substitute only the system prompt at the provider boundary."""

    delegate: ModelBackendProtocol
    arm: Arm

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Forward the unchanged request with one frozen factor prompt."""
        if request.system_prompt != _PLANNER_SYSTEM_PROMPT:
            raise RuntimeError("CM-57P8 received unexpected production planner prompt.")
        forwarded = replace(request, system_prompt=composed_prompt(self.arm))
        return await self.delegate.generate_structured(forwarded, response_model=response_model)

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker execution."""
        raise AssertionError("CM-57P8 must not invoke program generation.")


@dataclass
class RecordingBackend(ModelBackendProtocol):
    """Record bounded calls while preserving production provider behavior."""

    delegate: ModelBackendProtocol
    calls: list[dict[str, object]]
    plans: list[tuple[str, SemanticPlan]]
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Record call type and bounded output shape without provider prose."""
        if not self.calls:
            call_kind = "INITIAL"
        elif "Correction context:" in request.user_prompt:
            call_kind = "SEMANTIC_CORRECTION"
        else:
            call_kind = "INVALID_RESPONSE_RETRY"
        record: dict[str, object] = {"call_kind": call_kind}
        try:
            result = await self.delegate.generate_structured(request, response_model=response_model)
        except ProviderRequestError as error:
            record.update(
                {
                    "outcome": "provider_failure",
                    "provider_category": error.category.value,
                }
            )
            self.calls.append(record)
            raise
        except ValidationError:
            record["outcome"] = "structured_output_failure"
            self.calls.append(record)
            raise
        record["outcome"] = "structured_success"
        record["metrics"] = result.metrics.public_metadata()
        if isinstance(result.value, SemanticPlan):
            self.plans.append((call_kind, result.value))
            record["plan"] = p7.p5.p2._plan_projection(result.value)
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Fail closed if a planner run reaches a worker."""
        self.program_calls += 1
        raise AssertionError("CM-57P8 must stop before worker execution.")


def _provider_classification(error: ProviderRequestError) -> str:
    """Classify provider failures without treating invalid responses as infra."""
    if error.category in {
        ProviderFailureCategory.INVALID_RESPONSE,
        ProviderFailureCategory.VALIDATION,
    }:
        return "PLANNER_SCHEMA_FAILURE"
    return "PROVIDER_INFRA_FAILURE"


def _plan_facts(
    plan: SemanticPlan | None, case: dict[str, object], registry: CapabilityRegistry
) -> dict[str, object] | None:
    """Project accepted P7 planner facts when a plan exists."""
    return p7._plan_facts(plan, case, registry) if plan is not None else None


def _reference_projection(
    facts: dict[str, object] | None, case: dict[str, object]
) -> dict[str, object]:
    """Project reference presence without manufacturing terminal facts."""
    required = any("track.reference" in section for section in case["expected_sections"])
    if not isinstance(facts, dict):
        return {
            "expected_reference_required": required,
            "final_plan_available": False,
            "actual_reference_present": None,
            "unexpected_reference": None,
            "missing_required_reference": None,
        }
    sections = facts.get("section_capability_signatures") or []
    actual = any("track.reference" in section for section in sections)
    return {
        "expected_reference_required": required,
        "final_plan_available": True,
        "actual_reference_present": actual,
        "unexpected_reference": actual and not required,
        "missing_required_reference": required and not actual,
    }


async def run_arm(
    case: dict[str, object],
    *,
    arm: Arm,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Run one production SemanticPlanner under one prompt factor."""
    calls: list[dict[str, object]] = []
    plans: list[tuple[str, SemanticPlan]] = []
    recorder = RecordingBackend(
        delegate=PromptFactorBackend(delegate=delegate, arm=arm),
        calls=calls,
        plans=plans,
    )
    planner = SemanticPlanner(backend=recorder, registry=registry)
    final_plan: SemanticPlan | None = None
    error_type: str | None = None
    error_code: str | None = None
    final_classification: str | None = None
    provider_infrastructure_failure = False
    try:
        final_plan = await planner.plan(
            request=str(case["request"]),
            mode="reconstruct",
            current_document_summary={},
            source_summary=FIXED_SOURCE_SUMMARY,
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except ProviderRequestError as error:
        error_type = "ProviderRequestError"
        error_code = error.category.value
        final_classification = _provider_classification(error)
        provider_infrastructure_failure = final_classification == "PROVIDER_INFRA_FAILURE"
    except PlannerSemanticFailure as error:
        error_type = "PlannerSemanticFailure"
        error_code = error.code
        final_classification = "PLANNER_SEMANTIC_FAILURE"
    except ValidationError:
        error_type = "ValidationError"
        final_classification = "PLANNER_SCHEMA_FAILURE"
    initial_plan = next((plan for kind, plan in plans if kind == "INITIAL"), None)
    initial_facts = _plan_facts(initial_plan, case, registry)
    final_facts = _plan_facts(final_plan, case, registry)
    if final_plan is not None:
        final_classification = p7.p5.classify_facts(final_facts or {})
    if final_classification is None:
        raise AssertionError("CM-57P8 arm ended without a terminal result.")
    return {
        "arm": arm,
        "prompt_sha256": PROMPT_SHA256[arm],
        "response_schema_sha256": _schema_sha256(),
        "planner_call_count": len(calls),
        "program_call_count": recorder.program_calls,
        "call_trace": calls,
        "initial_plan_available": initial_plan is not None,
        "initial_facts": initial_facts,
        "final_plan_available": final_plan is not None,
        "final_facts": final_facts,
        "final_planner_success": final_plan is not None,
        "final_classification": final_classification,
        "final_error_type": error_type,
        "final_error_code": error_code,
        "provider_infrastructure_failure": provider_infrastructure_failure,
        "invalid_response_retry_used": any(
            call.get("call_kind") == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "semantic_correction_used": any(
            call.get("call_kind") == "SEMANTIC_CORRECTION" for call in calls
        ),
        "reference": _reference_projection(final_facts, case),
        "final_contract_ok": final_plan is not None and p7.p5.final_contract_ok(final_facts or {}),
    }


async def run_shared_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Run all four factors against one unchanged P7 request."""
    return {
        **_frozen_provenance(),
        "authorized_checkpoint": authorized_checkpoint,
        "case_id": case["case_id"],
        "role": case["role"],
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(str(case["request"])),
        "gold_sha256": _gold_sha(case),
        "arms": {
            arm: await run_arm(case, arm=arm, delegate=delegate, registry=registry) for arm in ARMS
        },
    }


def _arm(row: dict[str, object], arm: str) -> dict[str, object]:
    """Return one bounded arm result."""
    arms = row.get("arms")
    value = arms.get(arm) if isinstance(arms, dict) else None
    return value if isinstance(value, dict) else {}


def _historical_anchor_matches(result: dict[str, object], anchor: dict[str, object]) -> bool:
    """Compare only the bounded historical facts frozen in the manifest."""
    facts = result.get("final_facts")
    return {
        "final_planner_success": result.get("final_planner_success"),
        "final_classification": result.get("final_classification"),
        "report_task_present": facts.get("report_task_present")
        if isinstance(facts, dict)
        else None,
        "report_capability_ids": facts.get("report_capability_ids")
        if isinstance(facts, dict)
        else None,
        "section_capability_signatures": facts.get("section_capability_signatures")
        if isinstance(facts, dict)
        else None,
        "final_contract_ok": result.get("final_contract_ok"),
        "provider_failure_category": result.get("final_error_code"),
        "provider_calls": result.get("planner_call_count"),
        "call_kinds": [call.get("call_kind") for call in result.get("call_trace", [])],
    } == {
        key: anchor.get(key)
        for key in (
            "final_planner_success",
            "final_classification",
            "report_task_present",
            "report_capability_ids",
            "section_capability_signatures",
            "final_contract_ok",
            "provider_failure_category",
            "provider_calls",
            "call_kinds",
        )
    }


def historical_anchor_reproduction(
    rows: list[dict[str, object]], cases: tuple[dict[str, object], ...]
) -> dict[str, object]:
    """Check all selected anchors and the two independent localization axes."""
    by_case = {str(case["case_id"]): case for case in cases}

    def check(case_ids: set[str]) -> dict[str, object]:
        mismatches: list[str] = []
        checked = 0
        for row in rows:
            case_id = str(row["case_id"])
            if case_id not in case_ids:
                continue
            case = by_case[case_id]
            historical = case["historical"][str(row["attempt_index"])]
            for arm in ("P", "RC"):
                checked += 1
                if not _historical_anchor_matches(_arm(row, arm), historical[arm]):
                    mismatches.append(f"{case_id}/attempt_{row['attempt_index']}/{arm}")
        return {"checked": checked, "mismatches": mismatches, "reproduced": not mismatches}

    all_case_ids = set(by_case)
    return {
        "all": check(all_case_ids),
        "reference": check({PROTECTED_REFERENCE_TARGET}),
        "schema": check(set(SCHEMA_TARGETS)),
    }


def _reference_localization(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    anchors: dict[str, object],
) -> dict[str, object]:
    """Classify the protected reference target and report bounded matrices."""
    if not anchors["reference"]["reproduced"]:
        return {"classification": "INCONCLUSIVE_REFERENCE_LOCALIZATION", "stable": False}
    target = [row for row in rows if row["case_id"] == PROTECTED_REFERENCE_TARGET]
    values: dict[str, list[bool | None]] = {arm: [] for arm in ARMS}
    for row in target:
        for arm in ARMS:
            values[arm].append(_arm(row, arm)["reference"]["unexpected_reference"])
    if any(len(set(entries)) != 1 for entries in values.values()):
        return {"classification": "REFERENCE_FACTOR_UNSTABLE", "stable": False, "target": values}
    pattern = tuple(values[arm][0] for arm in ("R", "C", "RC"))
    labels = {
        (False, True, True): "REFERENCE_SECTION_COMPOSITION_SUFFICIENT",
        (True, False, True): "REFERENCE_REPORT_BOUNDARY_SUFFICIENT",
        (False, False, True): "REFERENCE_RC_INTERACTION_REQUIRED",
        (True, True, True): "REFERENCE_MULTIPLE_FACTORS_SUFFICIENT",
    }
    classification = labels.get(pattern, "INCONCLUSIVE_REFERENCE_LOCALIZATION")
    matrix = {
        str(row["case_id"]): {arm: _arm(row, arm)["reference"] for arm in ARMS}
        for row in rows
        if row["case_id"] in {str(case["case_id"]) for case in cases}
    }
    return {
        "classification": classification,
        "stable": classification not in {"INCONCLUSIVE_REFERENCE_LOCALIZATION"},
        "target": values,
        "matrix": matrix,
    }


def _schema_localization(
    rows: list[dict[str, object]], anchors: dict[str, object]
) -> dict[str, object]:
    """Classify structured-plan availability on the two schema targets."""
    if not anchors["schema"]["reproduced"]:
        return {"classification": "INCONCLUSIVE_SCHEMA_LOCALIZATION", "stable": False}
    by_case: dict[str, dict[str, list[bool]]] = {}
    for case_id in SCHEMA_TARGETS:
        by_case[case_id] = {arm: [] for arm in ARMS}
        for row in rows:
            if row["case_id"] == case_id:
                for arm in ARMS:
                    by_case[case_id][arm].append(bool(_arm(row, arm)["final_plan_available"]))
    if any(len(set(values)) != 1 for case in by_case.values() for values in case.values()):
        return {"classification": "SCHEMA_FACTOR_UNSTABLE", "stable": False, "targets": by_case}
    patterns = []
    for values in by_case.values():
        pattern = (values["R"][0], values["C"][0], values["RC"][0])
        patterns.append(pattern)
    if len(set(patterns)) > 1:
        classification = "SCHEMA_STABILIZATION_CASE_DEPENDENT"
    else:
        labels = {
            (False, True, True): "SCHEMA_SECTION_COMPOSITION_SUFFICIENT",
            (True, False, True): "SCHEMA_REPORT_BOUNDARY_SUFFICIENT",
            (False, False, True): "SCHEMA_RC_INTERACTION_REQUIRED",
            (True, True, True): "SCHEMA_MULTIPLE_FACTORS_SUFFICIENT",
        }
        classification = labels.get(patterns[0], "SCHEMA_STABILIZATION_CASE_DEPENDENT")
    return {
        "classification": classification,
        "stable": classification != "SCHEMA_FACTOR_UNSTABLE",
        "targets": by_case,
    }


def positive_reference_controls(rows: list[dict[str, object]]) -> dict[str, object]:
    """Report whether factor arms retain required reference tracks."""
    output: dict[str, object] = {}
    for case_id in sorted(POSITIVE_REFERENCE_CONTROLS):
        case_rows = [row for row in rows if row.get("case_id") == case_id]
        output[case_id] = {}
        for arm in ARMS:
            missing = [
                int(row["attempt_index"])
                for row in case_rows
                if _arm(row, arm)["reference"].get("missing_required_reference") is True
            ]
            output[case_id][arm] = {
                "missing_required_reference_attempts": missing,
                "reference_positive_control_regression": bool(missing),
            }
    return output


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on population, provenance, and execution drift."""
    reasons: list[str] = []
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.append("wrong_row_count")
    expected_ids = {str(case["case_id"]) for case in cases}
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(set(pairs)) != len(pairs):
        reasons.append("duplicate_case_attempt")
    if {case_id for case_id, _ in pairs} != expected_ids:
        reasons.append("case_set_mismatch")
    by_case: dict[str, set[object]] = {}
    for case_id, attempt in pairs:
        by_case.setdefault(case_id, set()).add(attempt)
    if any(attempts != set(range(ATTEMPTS)) for attempts in by_case.values()):
        reasons.append("attempt_index_mismatch")
    if any(not isinstance(row.get("arms"), dict) or set(row["arms"]) != set(ARMS) for row in rows):
        reasons.append("arm_set_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.append("authorized_checkpoint_mismatch")
    provenance = _frozen_provenance()
    for row in rows:
        for field, expected in provenance.items():
            if row.get(field) != expected:
                reasons.append(f"{field}_mismatch")
        case = next((case for case in cases if case["case_id"] == row.get("case_id")), None)
        if case is None or row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.append("request_hash_mismatch")
        if case is None or row.get("gold_sha256") != _gold_sha(case):
            reasons.append("gold_hash_mismatch")
        for arm in ARMS:
            result = _arm(row, arm)
            if result.get("prompt_sha256") != PROMPT_SHA256[arm]:
                reasons.append(f"{arm}_prompt_mismatch")
            if result.get("response_schema_sha256") != EXPECTED_SCHEMA_SHA256:
                reasons.append(f"{arm}_schema_mismatch")
            if int(result.get("program_call_count", 0)) != 0:
                reasons.append("worker_program_call")
    return not reasons, sorted(set(reasons))


def _arm_metrics(rows: list[dict[str, object]], arm: str) -> dict[str, int]:
    """Aggregate bounded planner outcomes."""
    results = [_arm(row, arm) for row in rows]
    return {
        "planner_executions": len(results),
        "provider_calls": sum(int(item.get("planner_call_count", 0)) for item in results),
        "initial_structured_successes": sum(
            bool(item.get("initial_plan_available")) for item in results
        ),
        "final_plan_available": sum(bool(item.get("final_plan_available")) for item in results),
        "invalid_response_retries": sum(
            bool(item.get("invalid_response_retry_used")) for item in results
        ),
        "semantic_corrections": sum(bool(item.get("semantic_correction_used")) for item in results),
        "terminal_schema_failures": sum(
            item.get("final_classification") == "PLANNER_SCHEMA_FAILURE" for item in results
        ),
        "terminal_semantic_failures": sum(
            item.get("final_classification") == "PLANNER_SEMANTIC_FAILURE" for item in results
        ),
        "infrastructure_failures": sum(
            bool(item.get("provider_infrastructure_failure")) for item in results
        ),
        "program_calls": sum(int(item.get("program_call_count", 0)) for item in results),
    }


def repeatability(rows: list[dict[str, object]]) -> dict[str, object]:
    """Report stable, unstable, and unavailable arm facts by case."""
    output: dict[str, dict[str, list[str]]] = {
        arm: {"stable": [], "unstable": [], "unavailable": []} for arm in ARMS
    }
    for case_id in sorted({str(row["case_id"]) for row in rows}):
        pair = sorted(
            (row for row in rows if row["case_id"] == case_id), key=lambda row: row["attempt_index"]
        )
        for arm in ARMS:
            values = [_arm(row, arm) for row in pair]
            key = "stable"
            projections = [
                (
                    value.get("final_plan_available"),
                    value.get("final_classification"),
                    value["reference"],
                )
                for value in values
            ]
            if len(values) != ATTEMPTS or any(
                value.get("final_plan_available") is False
                and value.get("final_classification") is None
                for value in values
            ):
                key = "unavailable"
            elif projections[0] != projections[1]:
                key = "unstable"
            output[arm][key].append(case_id)
    return output


def decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> dict[str, object]:
    """Apply the three frozen top-level P8 decisions."""
    complete, reasons = population_integrity(rows, cases, expected_checkpoint=expected_checkpoint)
    anchors = historical_anchor_reproduction(rows, cases)
    reference = _reference_localization(rows, cases, anchors)
    schema = _schema_localization(rows, anchors)
    infra = any(
        bool(_arm(row, arm).get("provider_infrastructure_failure")) for row in rows for arm in ARMS
    )
    workers = any(int(_arm(row, arm).get("program_call_count", 0)) for row in rows for arm in ARMS)
    valid_reference = reference["classification"] not in {
        "INCONCLUSIVE_REFERENCE_LOCALIZATION",
        "REFERENCE_FACTOR_UNSTABLE",
    }
    valid_schema = schema["classification"] not in {
        "INCONCLUSIVE_SCHEMA_LOCALIZATION",
        "SCHEMA_FACTOR_UNSTABLE",
    }
    if not complete or infra or workers:
        top = "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION"
    elif valid_reference and valid_schema:
        top = "PROMPT_FACTOR_LOCALIZATION_COMPLETE"
    elif valid_reference or valid_schema:
        top = "PROMPT_FACTOR_LOCALIZATION_PARTIAL"
    else:
        top = "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION"
    return {
        "decision": top,
        "population_reasons": reasons,
        "historical_anchor_reproduction": anchors,
        "reference_localization": reference,
        "schema_localization": schema,
    }


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
) -> dict[str, object]:
    """Build bounded aggregate evidence for a future completed matrix."""
    result = decision(rows, cases, expected_checkpoint=authorized_checkpoint)
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_checkpoint": authorized_checkpoint,
        "decision": result["decision"],
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "attempts_per_case": ATTEMPTS,
            "arms_per_row": len(ARMS),
            "planner_executions": len(cases) * ATTEMPTS * len(ARMS),
            "complete": not result["population_reasons"],
            "reasons": result["population_reasons"],
        },
        "historical_anchor_reproduction": result["historical_anchor_reproduction"],
        "reference_localization": result["reference_localization"],
        "schema_localization": result["schema_localization"],
        "positive_reference_controls": positive_reference_controls(rows),
        "arm_metrics": {arm: _arm_metrics(rows, arm) for arm in ARMS},
        "repeatability": repeatability(rows),
        "prompt_hashes": dict(PROMPT_SHA256),
        "response_schema_sha256": EXPECTED_SCHEMA_SHA256,
        "provider_calls_total": sum(
            int(_arm(row, arm).get("planner_call_count", 0)) for row in rows for arm in ARMS
        ),
        "worker_program_calls": sum(
            int(_arm(row, arm).get("program_call_count", 0)) for row in rows for arm in ARMS
        ),
        "controls": dict(FIXED_EXECUTION_CONTROLS),
        "production_adoption": "NOT_AUTHORIZED",
        "CM57D": "BLOCKED",
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require exact reviewed bytes before any future provider construction."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P8 checkout does not match the authorized checkpoint.")
    guarded = (
        "scripts/cm57p8_prompt_factor_localization.py",
        "tests/fixtures/typed_worker/cm57p8_prompt_factor_cases.json",
        "scripts/cm57p7_fresh_promotion.py",
        "scripts/cm57p5_fresh_holdout.py",
        "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json",
        "scripts/cm57p4_prompt_interaction_bisect.py",
        "docs/evaluations/agent-code-mode/CM-57P7-live-summary.json",
        "src/wellplot/agent/code_mode/planner.py",
        "src/wellplot/agent/providers/base.py",
        "src/wellplot/capabilities/base.py",
        "src/wellplot/capabilities/registry.py",
        "src/wellplot/capabilities/builtins.py",
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if path.read_bytes() != _git_output("show", f"{checkpoint}:{relative_path}"):
            raise RuntimeError(f"CM-57P8 guarded artifact drifted: {relative_path}")


def verify_frozen_contract() -> dict[str, object]:
    """Verify all P7/P4 and production artifacts without provider construction."""
    cases = load_manifest()
    checks = {
        P7_CASE_PATH: EXPECTED_P7_CORPUS_SHA256,
        P7_SCRIPT_PATH: EXPECTED_P7_SCRIPT_SHA256,
        P7_SUMMARY_PATH: EXPECTED_P7_SUMMARY_SHA256,
        P5_SCRIPT_PATH: EXPECTED_P5_SCRIPT_SHA256,
        P4_SCRIPT_PATH: EXPECTED_P4_SCRIPT_SHA256,
        REPO_ROOT / "src/wellplot/agent/code_mode/planner.py": EXPECTED_PLANNER_SOURCE_SHA256,
        REPO_ROOT / "src/wellplot/agent/providers/base.py": EXPECTED_PROVIDER_BASE_SHA256,
        REPO_ROOT / "src/wellplot/capabilities/base.py": EXPECTED_CAPABILITY_BASE_SHA256,
        REPO_ROOT / "src/wellplot/capabilities/registry.py": EXPECTED_CAPABILITY_REGISTRY_SHA256,
        REPO_ROOT / "src/wellplot/capabilities/builtins.py": EXPECTED_BUILTINS_SHA256,
    }
    for path, expected in checks.items():
        if artifact_sha256(path) != expected:
            raise RuntimeError(f"CM-57P8 frozen artifact drifted: {path}")
    registry = create_builtin_registry()
    if _schema_sha256() != EXPECTED_SCHEMA_SHA256:
        raise RuntimeError("CM-57P8 production response schema drifted.")
    if sha256_text(_PLANNER_SYSTEM_PROMPT) != EXPECTED_BASE_PROMPT_SHA256:
        raise RuntimeError("CM-57P8 production prompt drifted.")
    if sha256_text(REPORT_BOUNDARY_INSTRUCTION) != EXPECTED_R_INSTRUCTION_SHA256:
        raise RuntimeError("CM-57P8 report instruction drifted.")
    if sha256_text(SECTION_COMPOSITION_INSTRUCTION) != EXPECTED_C_INSTRUCTION_SHA256:
        raise RuntimeError("CM-57P8 section instruction drifted.")
    if PROMPT_SHA256 != {
        "P": EXPECTED_BASE_PROMPT_SHA256,
        "R": EXPECTED_R_PROMPT_SHA256,
        "C": EXPECTED_C_PROMPT_SHA256,
        "RC": EXPECTED_RC_PROMPT_SHA256,
    }:
        raise RuntimeError("CM-57P8 prompt factor hash drifted.")
    if sha256_text(canonical_json(FIXED_SOURCE_SUMMARY)) != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("CM-57P8 source summary drifted.")
    if not _registry_ids(registry):
        raise RuntimeError("CM-57P8 capability registry is empty.")
    return {
        "manifest_version": MANIFEST_VERSION,
        "manifest_sha256": artifact_sha256(MANIFEST_PATH),
        "p7_corpus_sha256": EXPECTED_P7_CORPUS_SHA256,
        "p7_summary_sha256": EXPECTED_P7_SUMMARY_SHA256,
        "p7_raw_sha256": EXPECTED_P7_RAW_SHA256,
        "p7_script_sha256": EXPECTED_P7_SCRIPT_SHA256,
        "p5_script_sha256": EXPECTED_P5_SCRIPT_SHA256,
        "p4_script_sha256": EXPECTED_P4_SCRIPT_SHA256,
        "P_prompt_sha256": PROMPT_SHA256["P"],
        "R_prompt_sha256": PROMPT_SHA256["R"],
        "C_prompt_sha256": PROMPT_SHA256["C"],
        "RC_prompt_sha256": PROMPT_SHA256["RC"],
        "production_schema_sha256": EXPECTED_SCHEMA_SHA256,
        "provider_base_sha256": EXPECTED_PROVIDER_BASE_SHA256,
        "source_summary_sha256": EXPECTED_SOURCE_SUMMARY_SHA256,
        "selected_cases": len(cases),
        "historical_anchor_derivation": "FROZEN_FROM_VERIFIED_P7_RAW",
    }


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the provider only after all future live guards pass."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    api_key = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        path = Path(args.api_key_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        api_key = api_key or path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No CM-57P8 API key configured.")
    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the future 24-row matrix once and flush every completed row."""
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    cases = load_manifest()
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
    print(json.dumps(summarize_population(rows, cases, authorized_checkpoint=checkpoint), indent=2))


def prelive_report() -> dict[str, object]:
    """Run provider-free guards and describe the future matrix."""
    contract = verify_frozen_contract()
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
        "arms": list(ARMS),
        "cases": 12,
        "attempts": ATTEMPTS,
        "shared_rows": 12 * ATTEMPTS,
        "planner_executions": 12 * ATTEMPTS * len(ARMS),
        "provider_calls_min": 12 * ATTEMPTS * len(ARMS),
        "provider_calls_max": 12 * ATTEMPTS * len(ARMS) * 2,
        **contract,
    }


def _parser() -> argparse.ArgumentParser:
    """Build the provider-free default and explicitly gated live CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run provider-free validation unless explicit live flags are supplied."""
    args = _parser().parse_args(argv)
    if not args.live_authorized:
        print(json.dumps(prelive_report(), indent=2, sort_keys=True))
        return 0
    if not args.authorized_checkpoint or not args.base_url:
        raise SystemExit("Live CM-57P8 requires --authorized-checkpoint and --base-url.")
    asyncio.run(_run_live(args, args.authorized_checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

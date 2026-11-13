"""CM-57P8 historical harness and A10-SEM-C1 revision comparison.

The active P8 comparison runs the exact P-current and C1 planner revisions in
fresh processes. The former four-arm prompt-substitution live mode is retired.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


P8_REVISION_ARM_ENV = "WELLPLOT_P8_REVISION_ARM"
P8_COMPARE_ARMS = ("P-current", "C1")
P8_NATIVE_CALL_CAP = 2
P8_ARM_REVISIONS = {
    "P-current": "1b9ead3c4acdf70dea0bce6475150f6219421988",
    "C1": "3a2cfbe3e9d61acdde2a072828e2256f59abcc4b",
}
P8_EXPECTED_PLANNER_SHA256 = {
    "P-current": "390bdeae3c6b8d60742123813410c430fff9417c5748e54c97e3ec2bba4c9186",
    "C1": "eab757657a035eed1416536db443bab776e4f77fa9c60f26cb08e68524621824",
}
P8_EXPECTED_SCHEMA_SHA256 = "b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb"
P8_EXPECTED_PROMPT_SHA256 = {
    "P-current": "8b680726fb3d10bc7e7243cc1aa56cb0677d706884416132b8310019a4e84981",
    "C1": "4bb8005845dc8bd78ea5797e8887f35ea5afe085dace71ffcf31de0f1d2b9483",
}
P8_PLANNER_PATH = "src/wellplot/agent/code_mode/planner.py"
P8_SMOKE_CASE_ID = "B01"
P8_SMOKE_REQUEST = "Plot Gamma Ray."
P8_SMOKE_REQUEST_SHA256 = "404a98eb0f9e40014aaf8312e53aea8a3267ea076963bff7420f1827196d7517"
P8_RAW_IO_RECORD_LIMIT = 1_048_576
P8_RAW_IO_FILE_LIMIT = 6 * P8_RAW_IO_RECORD_LIMIT


def _bootstrap_p8_planner_arm() -> None:
    """Install the selected committed planner before importing planner consumers."""
    arm = os.environ.get(P8_REVISION_ARM_ENV)
    if arm is None:
        return
    if arm not in P8_ARM_REVISIONS:
        raise RuntimeError("Unknown P8 planner revision arm.")

    revision = P8_ARM_REVISIONS[arm]
    source = subprocess.run(
        ["git", "show", f"{revision}:{P8_PLANNER_PATH}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    source_sha256 = hashlib.sha256(source).hexdigest()
    if source_sha256 != P8_EXPECTED_PLANNER_SHA256[arm]:
        raise RuntimeError("P8 planner blob does not match its frozen arm identity.")

    if arm == "P-current":
        importlib.import_module("wellplot.agent.code_mode")
        module_name = "wellplot.agent.code_mode.planner"
        spec = importlib.machinery.ModuleSpec(
            module_name,
            loader=None,
            origin=f"git:{revision}:{P8_PLANNER_PATH}",
        )
        module = importlib.util.module_from_spec(spec)
        module.__p8_source_sha256__ = source_sha256
        sys.modules[module_name] = module
        exec(compile(source, spec.origin, "exec"), module.__dict__)


_bootstrap_p8_planner_arm()


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
from wellplot.project_config import ProjectConfig, load_project_config  # noqa: E402


class _P8SchemaValidWireCaptured(Exception):
    """Stop smoke execution immediately after production wire validation."""


def _capture_planner_trace(
    event: dict[str, object],
    trace: list[dict[str, object]],
    *,
    stop_after_schema_valid_wire: bool,
) -> None:
    """Retain bounded planner events and stop the smoke at the wire boundary."""
    trace.append(
        {
            key: event.get(key)
            for key in ("event", "attempt", "code", "response_schema")
            if key in event
        }
    )
    if stop_after_schema_valid_wire and event.get("event") == "PLANNER_GENERATION_PASS":
        raise _P8SchemaValidWireCaptured


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


def _p8_planner_identity(arm: str) -> dict[str, object]:
    """Verify the imported canonical planner and its unchanged wire schema."""
    if arm not in P8_COMPARE_ARMS:
        raise RuntimeError("Invalid P8 planner arm.")
    planner_module = importlib.import_module("wellplot.agent.code_mode.planner")
    if arm == "P-current":
        source_sha256 = getattr(planner_module, "__p8_source_sha256__", None)
        module_origin = getattr(planner_module.__spec__, "origin", None)
    else:
        source_path = Path(planner_module.__file__).resolve()
        source_sha256 = artifact_sha256(source_path)
        module_origin = str(source_path)
    if source_sha256 != P8_EXPECTED_PLANNER_SHA256[arm]:
        raise RuntimeError("Imported P8 planner differs from the frozen arm.")

    from wellplot.agent.code_mode.planner import _PLANNER_SYSTEM_PROMPT, _PlannerWirePlan

    schema_sha256 = sha256_text(canonical_json(_PlannerWirePlan.model_json_schema()))
    if schema_sha256 != P8_EXPECTED_SCHEMA_SHA256:
        raise RuntimeError("P8 planner wire schema differs between frozen arms.")
    prompt_sha256 = sha256_text(_PLANNER_SYSTEM_PROMPT)
    if prompt_sha256 != P8_EXPECTED_PROMPT_SHA256[arm]:
        raise RuntimeError("P8 planner prompt differs from its frozen arm identity.")
    return {
        "arm": arm,
        "revision": P8_ARM_REVISIONS[arm],
        "planner_sha256": source_sha256,
        "planner_module": "wellplot.agent.code_mode.planner",
        "module_origin": module_origin,
        "wire_schema_sha256": schema_sha256,
        "prompt_sha256": prompt_sha256,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "pydantic_version": importlib.metadata.version("pydantic"),
        "openai_version": importlib.metadata.version("openai"),
        "httpx_version": importlib.metadata.version("httpx"),
        "pid": os.getpid(),
    }


def _p8_project_config() -> ProjectConfig:
    """Load and enforce the one canonical non-secret provider configuration."""
    config = load_project_config(REPO_ROOT)
    if (
        config.provider.name != "openai_compat"
        or config.provider.model != FROZEN_MODEL
        or config.provider.timeout_seconds != TIMEOUT_SECONDS
        or config.runtime.structured_output != "json_schema"
    ):
        raise RuntimeError("Canonical project provider configuration differs from frozen P8.")
    return config


def _p8_smoke_inputs() -> dict[str, object]:
    """Load the approved B01 request and metadata-only source context."""
    from scripts import nlp_d5_live_semantic_qualification as d5

    benchmark_path = REPO_ROOT / d5.A10_SEM_01_BENCHMARK
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    cases = benchmark.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("P8 smoke benchmark case inventory is invalid.")
    matches = [
        case for case in cases if isinstance(case, dict) and case.get("id") == P8_SMOKE_CASE_ID
    ]
    if len(matches) != 1:
        raise RuntimeError("P8 smoke B01 case is missing or duplicated.")
    source_case = matches[0]
    request = source_case.get("request")
    if (
        request != P8_SMOKE_REQUEST
        or sha256_text(str(request)) != P8_SMOKE_REQUEST_SHA256
        or source_case.get("source") != "approved_las"
    ):
        raise RuntimeError("P8 smoke request or approved source identity drifted.")

    case = {
        "case_id": P8_SMOKE_CASE_ID,
        "request": P8_SMOKE_REQUEST,
        "source_key": d5.A10_SEM_02_SMOKE_SOURCE_KEY,
        "source_path": d5.A10_SEM_02_SMOKE_SOURCE_PATH,
        "source_format": "las",
        "source_sha256": d5.A10_SEM_02_SMOKE_SOURCE_SHA256,
    }
    context = d5._build_planner_smoke_inputs(REPO_ROOT, case)
    if context.get("numeric_sample_apis_invoked") is not False:
        raise RuntimeError("P8 smoke context unexpectedly loaded numerical samples.")
    return {
        "case": case,
        "benchmark_sha256": artifact_sha256(benchmark_path),
        "document_summary": context["document_summary"],
        "source_summary": context["source_summary"],
        "document_summary_sha256": sha256_text(canonical_json(context["document_summary"])),
        "source_summary_sha256": sha256_text(canonical_json(context["source_summary"])),
        "source_asset_identity": context["source_asset_identity"],
        "source_sha256_before": context["source_sha256_before"],
        "source_sha256_after_inspection": context["source_sha256_after_inspection"],
        "source_revision_before": context["source_revision_before"],
        "source_revision_after_inspection": context["source_revision_after_inspection"],
        "source_channel_count": context["source_channel_count"],
        "numeric_sample_apis_invoked": False,
    }


def _append_private_json_line(path: Path, record: dict[str, object]) -> None:
    """Append one raw-I/O custody record to a new private file."""
    encoded = (json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded) > P8_RAW_IO_RECORD_LIMIT:
        raise RuntimeError("P8 raw-I/O record exceeds its private custody limit.")
    current_size = path.stat().st_size if path.exists() else 0
    if current_size + len(encoded) > P8_RAW_IO_FILE_LIMIT:
        raise RuntimeError("P8 raw-I/O artifact exceeds its private custody limit.")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass
class RevisionCaptureBackend(ModelBackendProtocol):
    """Capture wire candidates and reuse the canonical physical-attempt observer."""

    delegate: ModelBackendProtocol
    observer: object
    raw_io_path: Path
    call_records: list[dict[str, object]]
    wire_plans: list[dict[str, object]]
    physical_attempts: int = 0

    def __post_init__(self) -> None:
        """Bind the existing observer callbacks to this arm's private custody file."""
        self.observer.bind_model_io(
            lambda record: _append_private_json_line(self.raw_io_path, record)
        )
        self.observer.bind_physical_attempt(self._physical_attempt)

    def _physical_attempt(self, _logical_index: int) -> None:
        self.physical_attempts += 1

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Forward one canonical request and retain typed output before lowering."""
        call_index = len(self.call_records) + 1
        if call_index == 1:
            call_kind = "INITIAL"
        elif "Schema correction context:" in request.user_prompt:
            call_kind = "SCHEMA_CORRECTION"
        else:
            call_kind = "SEMANTIC_CORRECTION"
        self.observer.logical_call_started(
            {
                "index": call_index,
                "generation_role": "planner",
                "generation_purpose": call_kind.casefold(),
                "model": getattr(self.delegate, "model", FROZEN_MODEL),
            }
        )
        try:
            result = await self.delegate.generate_structured(
                request,
                response_model=response_model,
            )
        except ProviderRequestError as error:
            validation_shape = getattr(error, "validation_shape", None)
            response_reason = getattr(error, "response_reason", None)
            if hasattr(response_reason, "value"):
                response_reason = response_reason.value
            self.observer.logical_call_completed(
                {
                    "index": call_index,
                    "generation_role": "planner",
                    "generation_purpose": call_kind.casefold(),
                    "model": getattr(self.delegate, "model", FROZEN_MODEL),
                    "outcome": "failure",
                    "failure_category": error.category.value,
                    "response_reason": response_reason,
                    "validation_shape": validation_shape,
                }
            )
            self.call_records.append(
                {
                    "call_index": call_index,
                    "call_kind": call_kind,
                    "outcome": "provider_failure",
                    "category": error.category.value,
                    "response_reason": response_reason,
                    "validation_shape": (
                        validation_shape.to_json()
                        if callable(getattr(validation_shape, "to_json", None))
                        else None
                    ),
                }
            )
            raise
        self.observer.logical_call_completed(
            {
                "index": call_index,
                "generation_role": "planner",
                "generation_purpose": call_kind.casefold(),
                "model": getattr(self.delegate, "model", FROZEN_MODEL),
                "outcome": "success",
            }
        )
        value = result.value
        if response_model.__name__ != "_PlannerWirePlan":
            raise RuntimeError("P8 response model is not the canonical _PlannerWirePlan.")
        self.wire_plans.append(value.model_dump(mode="json"))
        self.call_records.append(
            {
                "call_index": call_index,
                "call_kind": call_kind,
                "outcome": "structured_success",
                "response_model": response_model.__name__,
            }
        )
        return result

    async def generate_program(self, request: object) -> object:
        """Reject any attempt to enter a worker during planner evaluation."""
        raise AssertionError(f"P8 planner evaluation cannot generate programs: {request!r}")


def _p8_case_by_id(case_id: str) -> dict[str, object]:
    """Load one frozen P7-backed request without exposing P8 gold to the child."""
    matches = [case for case in load_manifest() if case.get("case_id") == case_id]
    if len(matches) != 1:
        raise RuntimeError("P8 case identity is absent or duplicated in the frozen manifest.")
    return matches[0]


async def _run_p8_child(args: argparse.Namespace) -> dict[str, object]:
    """Run exactly one case in a fresh process using its committed planner arm."""
    arm = args.p8_arm
    if arm not in P8_COMPARE_ARMS or os.environ.get(P8_REVISION_ARM_ENV) != arm:
        raise RuntimeError("P8 child arm does not match its pre-import revision selection.")
    identity = _p8_planner_identity(arm)
    smoke_mode = bool(args.p8_smoke_child_b01)
    smoke_inputs = _p8_smoke_inputs() if smoke_mode else None
    case = smoke_inputs["case"] if smoke_inputs else _p8_case_by_id(args.p8_child_case)
    raw_io_path = Path(args.p8_raw_io).resolve()
    raw_io_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if raw_io_path.exists():
        raise RuntimeError("P8 raw-I/O custody path already exists.")
    raw_io_path.touch(mode=0o600, exist_ok=False)

    from scripts import nlp_d5_live_semantic_qualification as d5

    observer = d5._PhysicalAttemptObserver()
    observer.set_active_turn(f"{case['case_id']}:{arm}")
    observer.callback = lambda _logical_index: None
    import httpx
    from openai import AsyncOpenAI

    project_config = _p8_project_config()
    api_key = _read_p8_api_key()
    http_client = httpx.AsyncClient(
        event_hooks={"request": [observer.on_request], "response": [observer.on_response]}
    )
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=project_config.openai_compat_base_url,
        timeout=project_config.provider.timeout_seconds,
        max_retries=0,
        http_client=http_client,
    )
    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    delegate = OpenAICompatibleBackendV2(
        model=project_config.provider.model,
        client=client,
        structured_output=project_config.runtime.structured_output,
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )
    backend = RevisionCaptureBackend(
        delegate=delegate,
        observer=observer,
        raw_io_path=raw_io_path,
        call_records=[],
        wire_plans=[],
    )
    from wellplot.agent.code_mode.planner import PlannerSemanticFailure, SemanticPlanner
    from wellplot.agent.providers.base import ProviderRequestError
    from wellplot.capabilities import create_builtin_registry

    trace: list[dict[str, object]] = []

    def capture_trace(event: dict[str, object]) -> None:
        _capture_planner_trace(
            event,
            trace,
            stop_after_schema_valid_wire=smoke_mode,
        )

    planner = SemanticPlanner(
        backend=backend,
        registry=create_builtin_registry(),
        trace_callback=capture_trace,
    )
    started = time.monotonic()
    terminal: dict[str, object] = {"kind": "success"}
    try:
        plan = await planner.plan(
            request=str(case["request"]),
            mode="revise" if smoke_mode else "reconstruct",
            current_document_summary=(smoke_inputs["document_summary"] if smoke_inputs else {}),
            source_summary=(
                smoke_inputs["source_summary"] if smoke_inputs else FIXED_SOURCE_SUMMARY
            ),
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        terminal["planner_returned"] = plan is not None
    except _P8SchemaValidWireCaptured:
        terminal = {"kind": "schema_valid_wire_captured"}
    except PlannerSemanticFailure as error:
        terminal = {"kind": "planner_semantic_failure", "code": error.code}
    except ProviderRequestError as error:
        terminal = {
            "kind": "provider_failure",
            "category": error.category.value,
            "response_reason": getattr(error, "response_reason", None),
        }
    finally:
        await client.close()

    if len(backend.call_records) > P8_NATIVE_CALL_CAP:
        raise RuntimeError("Canonical planner exceeded the two-call correction budget.")
    if backend.physical_attempts > P8_NATIVE_CALL_CAP:
        raise RuntimeError("P8 provider transport exceeded the bounded physical-attempt budget.")
    return {
        "case_id": str(case["case_id"]),
        "arm": arm,
        "request_sha256": sha256_text(str(case["request"])),
        "planner_identity": identity,
        "provider_client_constructed": True,
        "structured_backend_constructed": True,
        "project_config_fingerprint_sha256": project_config.fingerprint_sha256,
        "wire_schema_sha256": P8_EXPECTED_SCHEMA_SHA256,
        "call_records": backend.call_records,
        "call_count": len(backend.call_records),
        "physical_attempt_count": backend.physical_attempts,
        "wire_plan": backend.wire_plans[-1] if backend.wire_plans else None,
        "wire_plan_count": len(backend.wire_plans),
        "wire_plans": backend.wire_plans,
        "terminal": terminal,
        "planner_trace": trace,
        "raw_io_relative_path": str(Path(args.p8_raw_io).relative_to(REPO_ROOT)),
        "elapsed_seconds": time.monotonic() - started,
        "smoke": (
            {
                "benchmark_sha256": smoke_inputs["benchmark_sha256"],
                "source_asset_identity": smoke_inputs["source_asset_identity"],
                "source_sha256_before": smoke_inputs["source_sha256_before"],
                "source_sha256_after_inspection": smoke_inputs["source_sha256_after_inspection"],
                "source_revision_before": smoke_inputs["source_revision_before"],
                "source_revision_after_inspection": smoke_inputs[
                    "source_revision_after_inspection"
                ],
                "source_channel_count": smoke_inputs["source_channel_count"],
                "document_summary_sha256": smoke_inputs["document_summary_sha256"],
                "source_summary_sha256": smoke_inputs["source_summary_sha256"],
                "numeric_sample_apis_invoked": False,
                "downstream_stage_calls": {
                    "report_worker": 0,
                    "section_worker": 0,
                    "reconciliation": 0,
                    "execution": 0,
                    "persistence": 0,
                    "rendering": 0,
                    "preview": 0,
                    "scientific_grading": 0,
                },
            }
            if smoke_inputs
            else None
        ),
    }


def _read_p8_api_key() -> str:
    """Read the canonical machine-local credential without disclosing it."""
    path = REPO_ROOT / "LLAMA_CPP_API_KEY.txt"
    if not path.is_file() or not os.access(path, os.R_OK):
        raise RuntimeError("The canonical local P8 credential is unavailable.")
    api_key = path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("The canonical local P8 credential is empty.")
    return api_key


def _p8_credential_available() -> bool:
    """Check canonical credential readability without reading or revealing its value."""
    path = REPO_ROOT / "LLAMA_CPP_API_KEY.txt"
    return path.is_file() and os.access(path, os.R_OK) and path.stat().st_size > 0


def _run_identity_probe(arm: str) -> dict[str, object]:
    """Return canonical planner identity in this fresh verification process."""
    if os.environ.get(P8_REVISION_ARM_ENV) != arm:
        raise RuntimeError("P8 identity probe environment does not match requested arm.")
    return _p8_planner_identity(arm)


def _score_p8_child(
    case: object,
    child: dict[str, object],
) -> dict[str, object]:
    """Score a completed child result downstream with the accepted adapter."""
    from scripts import a10_semantic_corpus_adapter as adapter
    from wellplot.agent.code_mode.planner import _PlannerWirePlan

    raw_plan = child.get("wire_plan")
    plan = _PlannerWirePlan.model_validate(raw_plan) if isinstance(raw_plan, dict) else None
    score = adapter.score_plan(case, plan)
    raw_plans = child.get("wire_plans", [])
    candidate_scores = [
        adapter.score_plan(case, _PlannerWirePlan.model_validate(raw_candidate))
        for raw_candidate in raw_plans
        if isinstance(raw_candidate, dict)
    ]
    terminal = child.get("terminal")
    terminal_kind = terminal.get("kind") if isinstance(terminal, dict) else None
    response_reason = terminal.get("response_reason") if isinstance(terminal, dict) else None
    provider_category = terminal.get("category") if isinstance(terminal, dict) else None
    call_records = child.get("call_records", [])
    first_provider_failure = next(
        (
            call
            for call in call_records
            if isinstance(call, dict) and call.get("outcome") == "provider_failure"
        ),
        None,
    )
    first_reason = (
        first_provider_failure.get("response_reason")
        if isinstance(first_provider_failure, dict)
        else response_reason
    )
    first_category = (
        first_provider_failure.get("category")
        if isinstance(first_provider_failure, dict)
        else provider_category
    )
    boundaries = {
        "transport": "FAIL"
        if first_provider_failure is not None
        and first_category not in {"invalid_response", "validation"}
        else "PASS",
        "structured_decode": "FAIL"
        if first_reason in {"invalid_json", "unusable_choice", "missing_content"}
        else "PASS",
        "provider_schema": "PASS",
        "pydantic_validation": "FAIL" if first_reason == "schema_validation" else "PASS",
        "planner_semantic": "FAIL"
        if terminal_kind == "planner_semantic_failure"
        or any(
            str(event.get("event", "")).endswith("_FAIL")
            and str(event.get("event", "")) != "PLANNER_GENERATION_FAIL"
            for event in child.get("planner_trace", [])
            if isinstance(event, dict)
        )
        or (candidate_scores and not candidate_scores[0].passed)
        or not score.passed
        else "PASS",
        "host_resolution": "PASS",
        "host_safety": "PASS",
    }
    detail, historical = adapter.classify_first_divergence(boundaries)
    return {
        "passed": score.passed and terminal_kind == "success",
        "disposition": score.disposition,
        "findings": list(score.findings),
        "candidate_score_passes": [candidate_score.passed for candidate_score in candidate_scores],
        "first_divergence": detail,
        "historical_first_divergence": historical,
        "operation_target_comparison": score.operation_target_comparison,
        "source_identity_comparison": score.source_identity_comparison,
        "operation_observations": [
            observation.__dict__ for observation in score.operation_observations
        ],
        "terminal": terminal,
        "boundaries": boundaries,
        "raw_io_relative_path": child["raw_io_relative_path"],
        "calls": call_records,
    }


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


def _p8_child_command(
    case_id: str,
    arm: str,
    raw_io_path: Path,
) -> tuple[list[str], dict[str, str]]:
    """Build one fresh-interpreter invocation for a single immutable pair."""
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--p8-child-case",
        case_id,
        "--p8-arm",
        arm,
        "--p8-raw-io",
        str(raw_io_path),
    ]
    child_env = dict(os.environ)
    child_env[P8_REVISION_ARM_ENV] = arm
    return command, child_env


def _p8_smoke_child_command(arm: str, raw_io_path: Path) -> tuple[list[str], dict[str, str]]:
    """Build one B01 smoke child invocation in a fresh canonical interpreter."""
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--p8-smoke-child-b01",
        "--p8-arm",
        arm,
        "--p8-raw-io",
        str(raw_io_path),
    ]
    child_env = dict(os.environ)
    child_env[P8_REVISION_ARM_ENV] = arm
    child_env["WELLPLOT_P8_SMOKE_CHILD"] = "B01"
    return command, child_env


def _p8_smoke_downstream_zero(child: dict[str, object]) -> bool:
    """Require the planner-only smoke to stop before every downstream stage."""
    smoke = child.get("smoke")
    if not isinstance(smoke, dict):
        return False
    calls = smoke.get("downstream_stage_calls")
    return (
        isinstance(calls, dict)
        and set(calls)
        == {
            "report_worker",
            "section_worker",
            "reconciliation",
            "execution",
            "persistence",
            "rendering",
            "preview",
            "scientific_grading",
        }
        and all(value == 0 for value in calls.values())
        and smoke.get("numeric_sample_apis_invoked") is False
    )


def _p8_raw_io_events(path: Path) -> list[dict[str, object]]:
    """Read complete request/response custody records from one arm artifact."""
    if not path.is_file():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError("P8 raw-I/O custody record is not an object.")
            events.append(value)
    return events


def _seal_p8_smoke_namespace(output_dir: Path) -> None:
    """Write the immutable digest manifest for the completed smoke record."""
    hashes = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            hashes.append(f"{artifact_sha256(path)}  {path.relative_to(output_dir).as_posix()}")
    _write_private_bytes(output_dir / "SHA256SUMS", ("\n".join(hashes) + "\n").encode())


def _run_p8_b01_smoke(args: argparse.Namespace) -> dict[str, object]:
    """Run one B01 planner-only smoke in each immutable P8 planner arm."""
    from scripts import a10_semantic_corpus_adapter as adapter
    from scripts import nlp_d5_live_semantic_qualification as d5
    from wellplot.file_revision import file_revision_token

    canonical_root = Path("/home/user/projects/well_log_os").resolve()
    if (
        Path.cwd().resolve() != canonical_root
        or REPO_ROOT.resolve() != canonical_root
        or Path(
            subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=canonical_root)
            .decode()
            .strip()
        ).resolve()
        != canonical_root
    ):
        raise RuntimeError("P8 smoke must run from the canonical checkout.")
    if current_checkout_sha() != args.authorized_checkpoint:
        raise RuntimeError("P8 smoke checkpoint differs from explicit smoke authority.")
    if _git_output("branch", "--show-current").decode().strip() != (
        "engineering-d5-binding-path-repair"
    ):
        raise RuntimeError("P8 smoke branch differs from the authorized branch.")
    d5._require_exact_planner_worktree(
        canonical_root,
        d5.A10_SEM_02_EXPECTED_WORKTREE_PORCELAIN,
    )

    output_dir = Path(args.p8_smoke_output_dir).resolve()
    evaluations_root = (canonical_root / "workspace/evaluations").resolve()
    if not output_dir.is_relative_to(evaluations_root) or output_dir.exists():
        raise RuntimeError("P8 smoke namespace must be fresh under workspace/evaluations.")

    smoke_inputs = _p8_smoke_inputs()
    source_path = canonical_root / d5.A10_SEM_02_SMOKE_SOURCE_PATH
    source_revision_at_admission = file_revision_token(source_path)
    source_sha_at_admission = artifact_sha256(source_path)
    if (
        source_revision_at_admission != smoke_inputs["source_revision_after_inspection"]
        or source_sha_at_admission != d5.A10_SEM_02_SMOKE_SOURCE_SHA256
    ):
        raise RuntimeError("P8 smoke source changed after metadata preflight.")
    project_config = _p8_project_config()
    api_key = _read_p8_api_key()
    closure = adapter.verify_planner_revision_closure(canonical_root)
    identity_reports = _verify_p8_revision_arms()
    preflight = p8_smoke_preflight()
    if preflight["request_sha256"] != P8_SMOKE_REQUEST_SHA256:
        raise RuntimeError("P8 smoke B01 request did not pass its frozen identity check.")

    output_dir.mkdir(parents=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    _write_private_json(
        output_dir / "smoke-preflight.json",
        {
            "checkpoint": current_checkout_sha(),
            "branch": _git_output("branch", "--show-current").decode().strip(),
            "request": P8_SMOKE_REQUEST,
            "request_sha256": P8_SMOKE_REQUEST_SHA256,
            "source_asset_identity": smoke_inputs["source_asset_identity"],
            "source_sha256_before": smoke_inputs["source_sha256_before"],
            "source_sha256_after_inspection": smoke_inputs["source_sha256_after_inspection"],
            "source_revision_before": smoke_inputs["source_revision_before"],
            "source_revision_after_inspection": smoke_inputs["source_revision_after_inspection"],
            "source_revision_at_admission": source_revision_at_admission,
            "source_sha256_at_admission": source_sha_at_admission,
            "source_channel_count": smoke_inputs["source_channel_count"],
            "document_summary_sha256": smoke_inputs["document_summary_sha256"],
            "source_summary_sha256": smoke_inputs["source_summary_sha256"],
            "numeric_sample_apis_invoked": False,
            "planner_revision_closure": closure,
            "arm_identity_processes": identity_reports,
            "wire_schema_sha256": P8_EXPECTED_SCHEMA_SHA256,
            "project_config_fingerprint_sha256": project_config.fingerprint_sha256,
            "logical_invocations": 2,
            "native_call_cap_per_arm": P8_NATIVE_CALL_CAP,
            "physical_generation_cap_total": 4,
            "holdout_access": "NOT_ACCESSED",
            "semantic_scoring": "NOT_PERFORMED",
        },
    )

    try:
        readiness = _p8_live_readiness(project_config, api_key)
    except Exception as error:
        failure = {
            "terminal": "A10_SEM_C1_P8_SMOKE_INCONCLUSIVE — ENVIRONMENT_OR_HARNESS",
            "classification": "READINESS_FAILED",
            "exception_type": type(error).__name__,
            "provider_calls": 0,
            "model_calls": 0,
            "generation_calls": 0,
        }
        _write_private_json(output_dir / "readiness-failure.json", failure)
        _seal_p8_smoke_namespace(output_dir)
        return failure
    _write_private_json(output_dir / "readiness.json", readiness)

    arm_results: dict[str, dict[str, object]] = {}
    physical_generation_count = 0
    logical_invocations_started = 0
    harness_failure = False
    arm_failure = False
    for arm in P8_COMPARE_ARMS:
        arm_dir = output_dir / "B01" / arm
        arm_dir.mkdir(parents=True, mode=0o700)
        os.chmod(arm_dir.parent, 0o700)
        os.chmod(arm_dir, 0o700)
        raw_io_path = arm_dir / "model-io.jsonl"
        command, child_env = _p8_smoke_child_command(arm, raw_io_path)
        logical_invocations_started += 1
        try:
            completed = subprocess.run(
                command,
                cwd=canonical_root,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=2 * TIMEOUT_SECONDS + 30,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raw_events = _p8_raw_io_events(raw_io_path)
            observed_requests = sum(
                event.get("event") == "physical_request" for event in raw_events
            )
            physical_generation_count += observed_requests
            source_identity_after_child = {
                "sha256": artifact_sha256(source_path),
                "revision": file_revision_token(source_path),
            }
            _write_private_json(
                arm_dir / "process-failure.json",
                {
                    "arm": arm,
                    "failure": "child_timeout",
                    "timeout_seconds": 2 * TIMEOUT_SECONDS + 30,
                    "stdout_sha256": sha256_text(error.stdout or ""),
                    "stderr_sha256": sha256_text(error.stderr or ""),
                    "source_identity_after_child": source_identity_after_child,
                },
            )
            harness_failure = True
            arm_results[arm] = {
                "status": "INCONCLUSIVE_CHILD_TIMEOUT",
                "provider_calls": observed_requests,
                "source_identity_after_child": source_identity_after_child,
            }
            continue

        raw_events = _p8_raw_io_events(raw_io_path)
        request_events = [event for event in raw_events if event.get("event") == "physical_request"]
        response_events = [
            event for event in raw_events if event.get("event") == "physical_response"
        ]
        physical_generation_count += len(request_events)
        source_identity_after_child = {
            "sha256": artifact_sha256(source_path),
            "revision": file_revision_token(source_path),
        }
        source_unchanged = (
            source_identity_after_child["sha256"] == d5.A10_SEM_02_SMOKE_SOURCE_SHA256
            and source_identity_after_child["revision"] == source_revision_at_admission
        )
        if completed.returncode != 0:
            _write_private_json(
                arm_dir / "process-failure.json",
                {
                    "arm": arm,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                    "stdout_sha256": sha256_text(completed.stdout),
                    "source_identity_after_child": source_identity_after_child,
                },
            )
            harness_failure = True
            arm_results[arm] = {
                "status": "CHILD_PROCESS_FAILURE",
                "provider_calls": len(request_events),
                "source_identity_after_child": source_identity_after_child,
            }
            continue

        child = json.loads(completed.stdout)
        if child.get("case_id") != P8_SMOKE_CASE_ID or child.get("arm") != arm:
            harness_failure = True
            arm_results[arm] = {"status": "CHILD_IDENTITY_MISMATCH"}
            continue
        identity = child.get("planner_identity")
        if not isinstance(identity, dict):
            harness_failure = True
            arm_results[arm] = {"status": "PLANNER_IDENTITY_MISSING"}
            continue
        expected_identity = identity_reports[arm]
        if any(
            identity.get(key) != value for key, value in expected_identity.items() if key != "pid"
        ):
            harness_failure = True
            arm_results[arm] = {"status": "PLANNER_IDENTITY_MISMATCH"}
            continue
        wire_plans = child.get("wire_plans", [])
        logical_calls = int(child.get("call_count", 0))
        observed_physical_calls = int(child.get("physical_attempt_count", 0))
        call_cap_ok = (
            logical_calls <= P8_NATIVE_CALL_CAP
            and observed_physical_calls <= P8_NATIVE_CALL_CAP
            and len(request_events) <= P8_NATIVE_CALL_CAP
        )
        successful = (
            child.get("terminal", {}).get("kind") == "schema_valid_wire_captured"
            and child.get("request_sha256") == P8_SMOKE_REQUEST_SHA256
            and child.get("smoke", {}).get("document_summary_sha256")
            == smoke_inputs["document_summary_sha256"]
            and child.get("smoke", {}).get("source_summary_sha256")
            == smoke_inputs["source_summary_sha256"]
            and 1 <= logical_calls <= P8_NATIVE_CALL_CAP
            and 1 <= observed_physical_calls <= P8_NATIVE_CALL_CAP
            and observed_physical_calls == len(request_events)
            and len(response_events) == len(request_events)
            and isinstance(wire_plans, list)
            and bool(wire_plans)
            and _p8_smoke_downstream_zero(child)
            and raw_io_path.stat().st_mode & 0o077 == 0
            and source_unchanged
        )
        arm_result = {
            **child,
            "schema_valid_wire_output": bool(wire_plans),
            "logical_planner_invocations": 1,
            "provider_calls": len(request_events),
            "response_count": len(response_events),
            "source_identity_after_child": source_identity_after_child,
            "smoke_pass": successful,
        }
        _write_private_json(arm_dir / "arm-result.json", arm_result)
        arm_results[arm] = {
            "status": (
                "INCONCLUSIVE_CALL_CAP"
                if not call_cap_ok
                else "INCONCLUSIVE_SOURCE_CUSTODY"
                if not source_unchanged
                else "PASS"
                if successful
                else "FAIL"
            ),
            "process_id": identity["pid"],
            "logical_planner_invocations": 1,
            "provider_calls": len(request_events),
            "source_identity_after_child": source_identity_after_child,
            "wire_schema_sha256": child.get("wire_schema_sha256"),
            "prompt_sha256": identity.get("prompt_sha256"),
            "raw_io_relative_path": child.get("raw_io_relative_path"),
            "downstream_stage_calls": child.get("smoke", {}).get("downstream_stage_calls"),
        }
        if not call_cap_ok or not source_unchanged:
            harness_failure = True
        elif not successful:
            arm_failure = True

    summary = {
        "terminal": (
            "A10_SEM_C1_P8_SMOKE_INCONCLUSIVE — ENVIRONMENT_OR_HARNESS"
            if harness_failure
            else "A10_SEM_C1_P8_SMOKE_FAIL — P8_NOT_AUTHORIZED"
            if arm_failure
            else "A10_SEM_C1_P8_SMOKE_PASS — INDEPENDENT_ACCEPTANCE_REQUIRED"
        ),
        "checkpoint": current_checkout_sha(),
        "request": P8_SMOKE_REQUEST,
        "request_sha256": P8_SMOKE_REQUEST_SHA256,
        "arms": arm_results,
        "logical_planner_invocations_started": logical_invocations_started,
        "physical_generations": physical_generation_count,
        "physical_generation_limit": 4,
        "provider_calls": physical_generation_count,
        "source_identity_at_admission": {
            "sha256": source_sha_at_admission,
            "revision": source_revision_at_admission,
        },
        "source_identity_after_smoke": {},
        "holdout_access": "NOT_ACCESSED",
        "semantic_scoring": "NOT_PERFORMED",
        "downstream_stage_calls": {
            "report_worker": 0,
            "section_worker": 0,
            "reconciliation": 0,
            "execution": 0,
            "persistence": 0,
            "rendering": 0,
            "preview": 0,
            "scientific_grading": 0,
        },
    }
    source_identity_after_smoke = {
        "sha256": artifact_sha256(source_path),
        "revision": file_revision_token(source_path),
    }
    summary["source_identity_after_smoke"] = source_identity_after_smoke
    if (
        source_identity_after_smoke["sha256"] != d5.A10_SEM_02_SMOKE_SOURCE_SHA256
        or source_identity_after_smoke["revision"] != source_revision_at_admission
    ):
        summary["terminal"] = "A10_SEM_C1_P8_SMOKE_INCONCLUSIVE — ENVIRONMENT_OR_HARNESS"
    if physical_generation_count > 4:
        summary["terminal"] = "A10_SEM_C1_P8_SMOKE_INCONCLUSIVE — ENVIRONMENT_OR_HARNESS"
        summary["call_cap_violation"] = True
    _write_private_json(output_dir / "smoke-summary.json", summary)
    _seal_p8_smoke_namespace(output_dir)
    return summary


def _write_private_json(path: Path, value: object) -> None:
    """Create one private JSON evidence file without overwriting prior evidence."""
    payload = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    """Write a private evidence payload completely, handling short OS writes."""
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("short evidence write")
        remaining = remaining[written:]


def _verify_p8_revision_arms() -> dict[str, object]:
    """Verify each planner arm in a separate child before any inference."""
    reports: dict[str, dict[str, object]] = {}
    for arm in P8_COMPARE_ARMS:
        env = dict(os.environ)
        env[P8_REVISION_ARM_ENV] = arm
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--p8-verify-arm", arm],
            cwd=REPO_ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        reports[arm] = json.loads(completed.stdout)
    if reports["P-current"]["pid"] == reports["C1"]["pid"]:
        raise RuntimeError("P8 revision verification reused an interpreter process.")
    if reports["P-current"]["wire_schema_sha256"] != reports["C1"]["wire_schema_sha256"]:
        raise RuntimeError("P8 wire schema differs across the immutable planner arms.")
    return reports


def p8_revision_preflight() -> dict[str, object]:
    """Qualify the frozen 12-by-2 plan without provider construction or holdout reads."""
    from scripts import a10_semantic_corpus_adapter as adapter

    closure = adapter.verify_planner_revision_closure(REPO_ROOT)
    identities = _verify_p8_revision_arms()
    project_config = _p8_project_config()
    pairs = adapter.p8_pair_population(REPO_ROOT)
    if len(pairs) != 24 or len({case_id for case_id, _ in pairs}) != 12:
        raise RuntimeError("P8 preflight did not produce the exact canary population.")
    if any(arm not in P8_COMPARE_ARMS for _, arm in pairs):
        raise RuntimeError("P8 preflight included an unapproved arm.")
    return {
        "status": "P8_PROVIDER_FREE_PREFLIGHT_PASS",
        "provider_calls": 0,
        "model_calls": 0,
        "holdout_access": "NOT_ACCESSED",
        "population": {
            "case_count": 12,
            "arm_count": 2,
            "planner_invocations": len(pairs),
            "pairs": [{"case_id": case_id, "arm": arm} for case_id, arm in pairs],
        },
        "planner_revision_closure": closure,
        "isolated_arm_identity_processes": identities,
        "wire_schema_sha256": P8_EXPECTED_SCHEMA_SHA256,
        "project_config": {
            "fingerprint_sha256": project_config.fingerprint_sha256,
            "provider": project_config.provider.name,
            "model": project_config.provider.model,
            "server_origin": project_config.server_origin,
            "timeout_seconds": project_config.provider.timeout_seconds,
            "configured_max_retries": project_config.provider.max_retries,
            "effective_sdk_retries": 0,
            "structured_output": project_config.runtime.structured_output,
        },
        "canonical_credential_file_readable": _p8_credential_available(),
        "native_call_cap_per_invocation": 2,
        "physical_call_cap_total": 48,
        "raw_io_custody": "one_private_model-io.jsonl_per_case_and_arm",
        "scoring": "downstream_parent_after_child_exit",
    }


def p8_smoke_preflight() -> dict[str, object]:
    """Qualify B01 smoke inputs and both arms without constructing a provider."""
    from scripts import a10_semantic_corpus_adapter as adapter

    smoke_inputs = _p8_smoke_inputs()
    closure = adapter.verify_planner_revision_closure(REPO_ROOT)
    identities = _verify_p8_revision_arms()
    project_config = _p8_project_config()
    return {
        "status": "P8_B01_SMOKE_PROVIDER_FREE_PREFLIGHT_PASS",
        "provider_calls": 0,
        "model_calls": 0,
        "case_id": P8_SMOKE_CASE_ID,
        "request_sha256": P8_SMOKE_REQUEST_SHA256,
        "benchmark_sha256": smoke_inputs["benchmark_sha256"],
        "source_asset_identity": smoke_inputs["source_asset_identity"],
        "source_revision_before": smoke_inputs["source_revision_before"],
        "source_revision_after_inspection": smoke_inputs["source_revision_after_inspection"],
        "source_channel_count": smoke_inputs["source_channel_count"],
        "document_summary_sha256": smoke_inputs["document_summary_sha256"],
        "source_summary_sha256": smoke_inputs["source_summary_sha256"],
        "numeric_sample_apis_invoked": False,
        "planner_revision_closure": closure,
        "isolated_arm_identity_processes": identities,
        "wire_schema_sha256": P8_EXPECTED_SCHEMA_SHA256,
        "project_config": {
            "fingerprint_sha256": project_config.fingerprint_sha256,
            "provider": project_config.provider.name,
            "model": project_config.provider.model,
            "server_origin": project_config.server_origin,
            "timeout_seconds": project_config.provider.timeout_seconds,
            "configured_max_retries": project_config.provider.max_retries,
            "effective_sdk_retries": 0,
            "structured_output": project_config.runtime.structured_output,
        },
        "canonical_credential_file_readable": _p8_credential_available(),
        "logical_invocations": 2,
        "native_call_cap_per_arm": P8_NATIVE_CALL_CAP,
        "physical_generation_cap_total": 4,
        "downstream_stages": "FORBIDDEN",
        "holdout_access": "NOT_ACCESSED",
        "semantic_scoring": "NOT_PERFORMED",
    }


def _p8_live_readiness(project_config: ProjectConfig, api_key: str) -> dict[str, object]:
    """Perform bounded authenticated GET readiness checks without generation."""
    import httpx

    endpoints = (
        ("/v1/models", project_config.model_catalog_url),
        ("/props", project_config.props_url),
    )
    results: dict[str, object] = {}
    with httpx.Client(timeout=10.0, headers={"Authorization": f"Bearer {api_key}"}) as client:
        for name, url in endpoints:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total_bytes = 0
                for chunk in response.iter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > 1_048_576:
                        raise RuntimeError(f"P8 smoke readiness response too large: {name}")
                    chunks.append(chunk)
                payload = json.loads(b"".join(chunks))
                if name == "/v1/models":
                    data = payload.get("data") if isinstance(payload, dict) else None
                    model_ids = [
                        item.get("id")
                        for item in data or []
                        if isinstance(item, dict) and isinstance(item.get("id"), str)
                    ]
                    if FROZEN_MODEL not in model_ids:
                        raise RuntimeError("P8 smoke readiness model identity mismatch.")
                    results[name] = {"http_status": response.status_code, "model_ids": model_ids}
                else:
                    alias = payload.get("model_alias") if isinstance(payload, dict) else None
                    if alias != FROZEN_MODEL:
                        raise RuntimeError("P8 smoke runtime model alias mismatch.")
                    results[name] = {
                        "http_status": response.status_code,
                        "model_alias": alias,
                        "context_tokens": payload.get("default_generation_settings", {}).get(
                            "n_ctx"
                        ),
                        "total_slots": payload.get("total_slots"),
                        "is_sleeping": payload.get("is_sleeping"),
                    }
    return results


def _validate_p8_child_budget(child: dict[str, object]) -> None:
    """Reject a child result that exceeds the one-initial/one-correction bound."""
    if int(child.get("call_count", 0)) > 2:
        raise RuntimeError("P8 arm exceeded its native one-correction call budget.")
    if int(child.get("physical_attempt_count", 0)) > 2:
        raise RuntimeError("P8 arm exceeded its physical-attempt budget.")


def _run_p8_revision_comparison(args: argparse.Namespace) -> dict[str, object]:
    """Run the bounded 12-case paired comparison through fresh canonical processes."""
    from scripts import a10_semantic_corpus_adapter as adapter

    output_dir = Path(args.p8_output_dir).resolve()
    if not output_dir.is_relative_to(REPO_ROOT) or output_dir.exists():
        raise RuntimeError("P8 output namespace must be new and inside the canonical checkout.")
    if (
        Path.cwd().resolve() != REPO_ROOT
        or Path(
            subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=REPO_ROOT)
            .decode()
            .strip()
        ).resolve()
        != REPO_ROOT
    ):
        raise RuntimeError("P8 execution must run from the canonical repository root.")

    if not _p8_credential_available():
        raise RuntimeError("Canonical P8 credential preflight failed before namespace admission.")

    closure = adapter.verify_planner_revision_closure(REPO_ROOT)
    identity_reports = _verify_p8_revision_arms()
    project_config = _p8_project_config()
    index = adapter.load_corpus_index(REPO_ROOT)
    cases = index.canary_cases
    pairs = adapter.p8_pair_population(REPO_ROOT)
    if len(pairs) != 24 or len(cases) != 12:
        raise RuntimeError("P8 paired population is not exactly 12 cases by 2 arms.")
    case_map = {case.case_id: case for case in cases}
    output_dir.mkdir(parents=True, mode=0o700)
    os.chmod(output_dir, 0o700)

    pair_results: dict[str, dict[str, object]] = {case.case_id: {} for case in cases}
    child_pids: list[int] = []
    physical_attempts = 0
    for case_id, arm in pairs:
        pair_dir = output_dir / case_id / arm
        pair_dir.mkdir(parents=True, mode=0o700)
        os.chmod(pair_dir.parent, 0o700)
        os.chmod(pair_dir, 0o700)
        raw_io_path = pair_dir / "model-io.jsonl"
        command, child_env = _p8_child_command(case_id, arm, raw_io_path)
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=2 * TIMEOUT_SECONDS + 30,
            check=False,
        )
        if completed.returncode != 0:
            _write_private_json(
                pair_dir / "process-failure.json",
                {
                    "case_id": case_id,
                    "arm": arm,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                    "stdout_sha256": sha256_text(completed.stdout),
                },
            )
            raise RuntimeError(f"P8 child failed before producing a result: {case_id}/{arm}")
        child = json.loads(completed.stdout)
        if child.get("case_id") != case_id or child.get("arm") != arm:
            raise RuntimeError("P8 child result identity differs from its invocation.")
        if child.get("request_sha256") != case_map[case_id].request_sha256:
            raise RuntimeError("P8 child request bytes differ from the frozen canary.")
        if child.get("project_config_fingerprint_sha256") != project_config.fingerprint_sha256:
            raise RuntimeError("P8 child project configuration drifted during the matrix.")
        planner_identity = child.get("planner_identity")
        if not isinstance(planner_identity, dict) or planner_identity.get("pid") in child_pids:
            raise RuntimeError("P8 case/arm did not receive a fresh interpreter.")
        child_pids.append(int(planner_identity["pid"]))
        physical_attempts += int(child.get("physical_attempt_count", 0))
        _validate_p8_child_budget(child)
        if not raw_io_path.is_file() or raw_io_path.stat().st_size == 0:
            raise RuntimeError("P8 arm has no case-scoped raw-I/O custody artifact.")
        if raw_io_path.stat().st_mode & 0o077:
            raise RuntimeError("P8 raw-I/O custody permissions are broader than 0600.")
        expected_identity = identity_reports[arm]
        for key, value in expected_identity.items():
            if key != "pid" and planner_identity.get(key) != value:
                raise RuntimeError("P8 child loaded a planner different from its frozen arm.")
        if planner_identity.get("planner_sha256") != P8_EXPECTED_PLANNER_SHA256[arm]:
            raise RuntimeError("P8 child planner hash differs from the frozen arm.")
        scored = _score_p8_child(case_map[case_id], child)
        _write_private_json(pair_dir / "arm-result.json", {**child, "score": scored})
        pair_results[case_id][arm] = scored

    if len(set(child_pids)) != 24:
        raise RuntimeError("P8 matrix reused a child interpreter.")
    paired_rows: list[dict[str, object]] = []
    for case in cases:
        p_result = pair_results[case.case_id]["P-current"]
        c_result = pair_results[case.case_id]["C1"]
        p_pass = bool(p_result["passed"])
        c_pass = bool(c_result["passed"])
        p_failure = str(p_result["first_divergence"])
        c_failure = str(c_result["first_divergence"])
        if c_pass and not p_pass:
            delta = "C1_IMPROVEMENT"
        elif p_pass and not c_pass:
            delta = "C1_REGRESSION"
        elif p_pass and c_pass:
            delta = "SAFE_MATCH"
        elif p_failure == c_failure:
            delta = "SAME_FAILURE_CLASS"
        else:
            delta = "C1_FAILURE_CLASS_CHANGE"
        paired_rows.append(
            {
                "case_id": case.case_id,
                "role": case.protected_role,
                "source_fixture": case.source_fixture,
                "source_checkpoint": case.source_checkpoint,
                "source_blob_sha256": case.source_blob_sha256,
                "request_sha256": case.request_sha256,
                "P-current": p_result,
                "C1": c_result,
                "paired_disposition": delta,
            }
        )

    infrastructure_failure = any(
        result.get("first_divergence") == "TRANSPORT"
        for row in paired_rows
        for result in (row["P-current"], row["C1"])
    )
    c1_regressions = [
        row["case_id"] for row in paired_rows if row["paired_disposition"] == "C1_REGRESSION"
    ]
    failure_class_changes = [
        row["case_id"]
        for row in paired_rows
        if row["paired_disposition"] == "C1_FAILURE_CLASS_CHANGE"
    ]
    terminal = (
        "A10_SEM_C1_P8_HARNESS_FAIL"
        if infrastructure_failure
        else "A10_SEM_C1_CANARY_FAIL"
        if c1_regressions or failure_class_changes
        else "A10_SEM_C1_P8_PASS - HISTORICAL_DEVELOPMENT_EVALUATION_AUTHORIZED"
    )
    summary = {
        "terminal": terminal,
        "population": {"cases": 12, "arms": list(P8_COMPARE_ARMS), "planner_invocations": 24},
        "planner_revision_closure": closure,
        "identity_probe_processes": identity_reports,
        "case_child_pids": child_pids,
        "provider_calls_max": 48,
        "provider_calls_observed": physical_attempts,
        "native_calls_per_invocation_max": P8_NATIVE_CALL_CAP,
        "execution_controls": {
            "model": FROZEN_MODEL,
            "temperature": PLANNER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "timeout_seconds_per_call": TIMEOUT_SECONDS,
            "sdk_retries": 0,
        },
        "project_config_fingerprint_sha256": project_config.fingerprint_sha256,
        "source_summary_sha256": sha256_text(canonical_json(FIXED_SOURCE_SUMMARY)),
        "prompt_sha256_by_arm": dict(P8_EXPECTED_PROMPT_SHA256),
        "wire_schema_sha256": P8_EXPECTED_SCHEMA_SHA256,
        "c1_regression_case_ids": c1_regressions,
        "c1_failure_class_change_case_ids": failure_class_changes,
        "holdout_access": "NOT_ACCESSED",
        "production_adoption": "NOT_AUTHORIZED",
        "paired_results": paired_rows,
    }
    _write_private_json(output_dir / "paired-results.json", paired_rows)
    _write_private_json(output_dir / "summary.json", summary)
    hashes = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            digest = artifact_sha256(path)
            hashes.append(f"{digest}  {path.relative_to(output_dir).as_posix()}")
    _write_private_bytes(output_dir / "SHA256SUMS", ("\n".join(hashes) + "\n").encode())
    return summary


def _write_private_bytes(path: Path, payload: bytes) -> None:
    """Create a private immutable evidence artifact."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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
    parser.add_argument("--p8-compare-authorized", action="store_true")
    parser.add_argument("--p8-preflight", action="store_true")
    parser.add_argument("--p8-smoke-preflight", action="store_true")
    parser.add_argument("--p8-smoke-authorized", action="store_true")
    parser.add_argument("--p8-smoke-output-dir")
    parser.add_argument("--p8-smoke-child-b01", action="store_true")
    parser.add_argument("--p8-output-dir")
    parser.add_argument("--p8-child-case")
    parser.add_argument("--p8-arm", choices=P8_COMPARE_ARMS)
    parser.add_argument("--p8-raw-io")
    parser.add_argument("--p8-verify-arm", choices=P8_COMPARE_ARMS)
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run provider-free validation unless explicit live flags are supplied."""
    args = _parser().parse_args(argv)
    if args.p8_verify_arm:
        print(json.dumps(_run_identity_probe(args.p8_verify_arm), sort_keys=True))
        return 0
    if args.p8_preflight:
        print(json.dumps(p8_revision_preflight(), indent=2, sort_keys=True))
        return 0
    if args.p8_smoke_preflight:
        print(json.dumps(p8_smoke_preflight(), indent=2, sort_keys=True))
        return 0
    if args.p8_smoke_child_b01:
        if os.environ.get("WELLPLOT_P8_SMOKE_CHILD") != "B01":
            raise SystemExit("B01 smoke child can only be launched by its coordinator.")
        if not args.p8_arm or not args.p8_raw_io:
            raise SystemExit("B01 smoke child requires arm and raw-I/O custody path.")
        print(json.dumps(asyncio.run(_run_p8_child(args)), sort_keys=True, ensure_ascii=False))
        return 0
    if args.p8_smoke_authorized:
        if not args.p8_smoke_output_dir or not args.authorized_checkpoint:
            raise SystemExit("P8 smoke requires a fresh namespace and authorized checkpoint.")
        print(json.dumps(_run_p8_b01_smoke(args), indent=2, sort_keys=True))
        return 0
    if args.p8_child_case:
        if not args.p8_arm or not args.p8_raw_io:
            raise SystemExit("P8 child requires case, arm and raw-I/O path.")
        print(json.dumps(asyncio.run(_run_p8_child(args)), sort_keys=True, ensure_ascii=False))
        return 0
    if args.p8_compare_authorized:
        if not args.p8_output_dir:
            raise SystemExit("P8 comparison requires --p8-output-dir.")
        print(json.dumps(_run_p8_revision_comparison(args), indent=2, sort_keys=True))
        return 0
    if args.live_authorized:
        raise SystemExit("The historical CM-57P8 prompt-factor live mode is retired.")
    if not args.live_authorized:
        print(json.dumps(p8_revision_preflight(), indent=2, sort_keys=True))
        return 0
    raise SystemExit("Unsupported CM-57P8 invocation.")


if __name__ == "__main__":
    raise SystemExit(main())

"""Provider-free D5-5G historical-claim revalidation harness.

This module prepares and verifies bounded A/B/C study mechanics around the
existing canonical WellPlot path. It does not call a provider, execute a
model, or implement an alternate semantic engine.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx

from scripts import nlp_d5_live_semantic_qualification as d5
from wellplot.agent.code_mode.planner import (
    PlannerSemanticError,
    SemanticPlan,
    _correction_request,
    _planning_request,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.project_config import load_project_config

D5_5G_AUTHORITY = "WELLPLOT-D5-5G-INSPECTABLE-HISTORICAL-CLAIM-REVALIDATION-IMPLEMENTATION-AUTH-001"
D5_5G_DESIGN_CHECKPOINT = "5e530db90babf50c9992f3829d1a11d3cc79e433"
D5_5G_SINGLE_ENGINE_ENTRYPOINT = "wellplot.agent.composition:create_canonical_compile_facade"
D5_5G_LIVE_AUTHORITY_PREFIX = "WELLPLOT-D5-5G-LIVE-REVALIDATION-AUTH-"
PROVIDER_MODEL_CALLS = 0
PROTECTED_SUBTREES = (
    "target_identity",
    "source_clue",
    "scale",
    "presentation",
)
FIRST_DIVERGENCE_ORDER = (
    "PROVIDER_OR_STRUCTURED",
    "PLANNER_SHAPE",
    "TARGET_OR_SOURCE_LINKING",
    "SEMANTIC_FIELD",
    "CAPABILITY_CLOSURE",
    "HOST_SAFETY",
    "DETERMINISTIC_GRADING",
    "HARNESS",
)
INSPECTION_SECTIONS = (
    "case_expected_semantics",
    "model_input_state",
    "exact_model_facing_request",
    "exact_raw_model_response",
    "structured_output_boundary",
    "canonical_wellplot_boundary",
    "resulting_semantics",
    "evaluation",
    "first_divergence",
)


def _sha256_json(value: object) -> str:
    """Hash one deterministic JSON-compatible value."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git(repo_root: Path, *arguments: str) -> str:
    """Read one Git fact without changing the checkout."""
    return subprocess.check_output(["git", *arguments], cwd=repo_root, text=True).strip()


def _section_task_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical SectionTask schema from SemanticPlan's schema."""
    definitions = schema.get("$defs")
    if not isinstance(definitions, Mapping):
        raise ValueError("canonical SemanticPlan schema has no definitions")
    section = definitions.get("SectionTask")
    if not isinstance(section, dict):
        raise ValueError("canonical SemanticPlan schema has no SectionTask definition")
    return section


def canonical_provider_schema(required_section_hint: bool) -> dict[str, Any]:
    """Derive one provider-facing schema view from the canonical model schema."""
    schema = copy.deepcopy(SemanticPlan.model_json_schema())
    section = _section_task_schema(schema)
    required = [str(item) for item in section.get("required", ())]
    if required_section_hint and "existing_section_hint" not in required:
        required.append("existing_section_hint")
    if not required_section_hint:
        required = [item for item in required if item != "existing_section_hint"]
    section["required"] = required
    return schema


def _schema_differences(left: object, right: object, path: str = "$") -> list[str]:
    """Return deterministic JSON paths whose schema values differ."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        paths: list[str] = []
        for key in sorted(set(left) | set(right), key=str):
            child = f"{path}.{key}"
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(_schema_differences(left[key], right[key], child))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        if left == right:
            return []
        return [path]
    return [] if left == right else [path]


def _json_differences(left: object, right: object, path: str = "$") -> list[str]:
    """Return deterministic paths whose JSON-compatible values differ."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        paths: list[str] = []
        for key in sorted(set(left) | set(right), key=str):
            child = f"{path}.{key}"
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(_json_differences(left[key], right[key], child))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [path]
        paths: list[str] = []
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            paths.extend(_json_differences(left_item, right_item, f"{path}[{index}]"))
        return paths
    return [] if left == right else [path]


def _request_controls(request: object) -> dict[str, Any]:
    """Project provider-neutral controls from one canonical request."""
    return {
        "timeout_seconds": request.timeout_seconds,
        "temperature": request.temperature,
        "max_output_tokens": request.max_output_tokens,
    }


def _planning_context(*, capability_contract: object | None = None) -> dict[str, Any]:
    """Build one fresh semantic input shared by all provider-facing arms."""
    context: dict[str, Any] = {
        "request": (
            "Revise one selected section and preserve the other available section. "
            "Use the source identified by the request."
        ),
        "mode": "revise",
        "current_document_summary": {
            "sections": [
                {"title": "Copper Ridge", "semantic_id": "section-copper-ridge"},
                {"title": "Silver Meadow", "semantic_id": "section-silver-meadow"},
            ],
            "selected_source_candidates": ["source-ember", "source-flint"],
        },
        "source_summary": {
            "candidates": [
                {"identity": "source-ember", "channels": ["GR", "ILD"]},
                {"identity": "source-flint", "channels": ["GR", "RT"]},
            ]
        },
        "capabilities": [
            {
                "id": descriptor["id"],
                "category": descriptor["category"],
                "description": descriptor["description"],
                "allowed_parents": descriptor.get("allowed_parents", []),
                "planning_hints": descriptor.get("planning_hints", []),
                "schema_version": descriptor.get("schema_version", "1"),
            }
            for descriptor in create_builtin_registry().planning_catalog()
        ],
    }
    if capability_contract is not None:
        context["capability_local_contract"] = capability_contract
    return context


def canonical_revision_plan(*, include_hint: bool) -> dict[str, Any]:
    """Build one fresh semantic plan used by provider-facing arm proofs."""
    task: dict[str, Any] = {
        "goal": "Revise the Copper Ridge section using the selected source",
        "capability_ids": ["section.log_plot"],
        "source_hints": ["source-ember"],
        "requirements": ["preserve the requested scale"],
        "constraints": ["do not change unrelated presentation"],
    }
    if include_hint:
        task["existing_section_hint"] = "Copper Ridge"
    return {
        "summary": "Apply the bounded revision request",
        "section_tasks": [task],
        "unresolved_requirements": ["address the reported capability defect"],
    }


def validate_canonical_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate through the existing canonical planner response model."""
    plan = SemanticPlan.model_validate(payload)
    return plan.model_dump(mode="json")


def compare_requiredness_arms() -> dict[str, Any]:
    """Materialize A0/A1 with identical input and one schema delta."""
    a0 = canonical_provider_schema(required_section_hint=False)
    a1 = canonical_provider_schema(required_section_hint=True)
    differences = _schema_differences(a0, a1)
    expected_path = "$.$defs.SectionTask.required"
    if differences != [expected_path]:
        raise AssertionError(f"requiredness arm changed unexpected schema paths: {differences}")
    context = _planning_context()
    request = _planning_request(
        context=context,
        timeout_seconds=900.0,
        temperature=0.0,
        max_output_tokens=None,
    )
    controls = _request_controls(request)
    common = {
        "system_prompt": request.system_prompt,
        "user_payload": request.user_prompt,
        "controls": controls,
        "semantic_input_sha256": _sha256_json(context),
    }
    arms = {
        "A0": {**common, "response_schema": a0},
        "A1": {**common, "response_schema": a1},
    }
    arm_differences = _json_differences(arms["A0"], arms["A1"])
    if arm_differences != ["$.response_schema.$defs.SectionTask.required"]:
        raise AssertionError(f"A arms changed unexpected request paths: {arm_differences}")
    canonical = validate_canonical_plan(canonical_revision_plan(include_hint=True))
    if len(context["current_document_summary"]["sections"]) != 2:
        raise AssertionError("Axis A must expose two plausible revision targets")
    return {
        "axis": "A",
        "arms": ["A0", "A1"],
        "schema_difference_paths": differences,
        "request_difference_paths": arm_differences,
        "request_hashes": {arm: _sha256_json(payload) for arm, payload in arms.items()},
        "identical_model_input": True,
        "plausible_target_count": len(context["current_document_summary"]["sections"]),
        "canonical_plan_hash": _sha256_json(canonical),
        "canonical_model": f"{SemanticPlan.__module__}.{SemanticPlan.__name__}",
        "downstream_validation": "SHARED",
        "provider_model_calls": 0,
    }


def capability_contract(arm: str) -> dict[str, Any]:
    """Return generic capability-local contracts for the two study families."""
    if arm == "B0":
        return {"version": "d5-5g-capability-contract.v1", "mappings": []}
    if arm == "B1":
        return {
            "version": "d5-5g-capability-contract.v1",
            "mappings": [
                {
                    "family": "revision_target_mapping",
                    "semantic_field": "existing_section_hint",
                    "allowed_value_domain": "inspected section titles",
                    "language_patterns": ["revise the named section"],
                    "positive_example": "Revise the Copper Ridge section",
                    "negative_example": "Do not revise the Silver Meadow section",
                },
                {
                    "family": "source_channel_closure",
                    "semantic_field": "source_hints",
                    "allowed_value_domain": "inspected source identities",
                    "language_patterns": ["use the named source"],
                    "positive_example": "Use source-ember for the selected section",
                    "negative_example": "Do not use an uninspected source",
                },
            ],
        }
    raise ValueError(f"unknown capability-contract arm: {arm}")


def compare_capability_contract_arms() -> dict[str, Any]:
    """Materialize B0/B1 requests with one controlled contract difference."""
    b0 = capability_contract("B0")
    b1 = capability_contract("B1")
    if b0["version"] != b1["version"]:
        raise AssertionError("capability-contract arms changed contract version")
    if b0["mappings"] or len(b1["mappings"]) != 2:
        raise AssertionError("capability-contract arm shape drifted")
    serialized = json.dumps(b1["mappings"], sort_keys=True).casefold()
    forbidden = ("formation integrity", "cbl", "las", "nphi", "d4-")
    if any(marker in serialized for marker in forbidden):
        raise AssertionError("capability contract contains qualification-specific answers")
    requests: dict[str, dict[str, Any]] = {}
    for arm, contract in (("B0", b0), ("B1", b1)):
        context = _planning_context(capability_contract=contract)
        request = _planning_request(
            context=context,
            timeout_seconds=900.0,
            temperature=0.0,
            max_output_tokens=None,
        )
        requests[arm] = {
            "system_prompt": request.system_prompt,
            "user_payload": request.user_prompt,
            "response_schema": canonical_provider_schema(required_section_hint=True),
            "controls": _request_controls(request),
        }
    differences = _json_differences(requests["B0"], requests["B1"])
    allowed_prefix = "$.user_payload"
    if not differences or any(not path.startswith(allowed_prefix) for path in differences):
        raise AssertionError(f"B arms changed outside capability-local request text: {differences}")
    base_context = _planning_context(capability_contract=b0)
    contract_context = _planning_context(capability_contract=b1)
    for key in ("request", "mode", "current_document_summary", "source_summary", "capabilities"):
        if base_context[key] != contract_context[key]:
            raise AssertionError(f"B arms changed shared semantic input: {key}")
    return {
        "axis": "B",
        "arms": ["B0", "B1"],
        "changed_surface": "capability_local_contract_text",
        "request_difference_paths": differences,
        "request_hashes": {arm: _sha256_json(payload) for arm, payload in requests.items()},
        "families": ["revision_target_mapping", "source_channel_closure"],
        "schema_context_evaluator": "SHARED",
        "synthetic_examples": "GENERIC",
        "provider_model_calls": 0,
    }


def _canonical_revision_request(plan: SemanticPlan) -> dict[str, Any]:
    """Build the actual canonical correction request without calling a model."""
    request = _correction_request(
        mode="revise",
        request="Revise the Copper Ridge section using source-ember.",
        previous_plan=plan,
        diagnostic=PlannerSemanticError(
            "missing_section_capability",
            "The selected section needs one registered section capability.",
        ),
        registry=create_builtin_registry(),
        timeout_seconds=900.0,
        temperature=None,
        max_output_tokens=None,
    )
    return {
        "system_prompt_sha256": hashlib.sha256(request.system_prompt.encode()).hexdigest(),
        "user_prompt_sha256": hashlib.sha256(request.user_prompt.encode()).hexdigest(),
        "response_contract": SemanticPlan.__name__,
    }


def _protected_projection(plan: SemanticPlan) -> dict[str, Any]:
    """Project protected semantic subtrees without creating a second model."""
    task = plan.section_tasks[0]
    return {
        "target_identity": task.existing_section_hint,
        "source_clue": list(task.source_hints),
        "scale": list(task.requirements),
        "presentation": list(task.constraints),
    }


def classify_protected_subtrees(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    resolution_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Classify protected subtrees without inferring identity from shape alone."""
    result: dict[str, str] = {}
    evidence = resolution_evidence or {}
    for key in PROTECTED_SUBTREES:
        if key not in before or key not in after:
            result[key] = "AMBIGUOUS"
        elif before[key] == after[key]:
            result[key] = "PRESERVED"
        elif after[key] is None:
            result[key] = "DROPPED"
        elif isinstance(before[key], list) and isinstance(after[key], list):
            same_identity = evidence.get(key, {}).get("same_canonical_identity") is True
            result[key] = "RE_RESOLVED" if same_identity else "AMBIGUOUS"
        else:
            result[key] = "CHANGED"
    return result


def observe_canonical_correction_result(
    before: SemanticPlan,
    after: SemanticPlan,
    *,
    resolution_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify one actual canonical correction result supplied by live custody."""
    before_projection = _protected_projection(before)
    after_projection = _protected_projection(after)
    classifications = classify_protected_subtrees(
        before_projection,
        after_projection,
        resolution_evidence=resolution_evidence,
    )
    return {
        "before_projection": before_projection,
        "after_projection": after_projection,
        "before_projection_sha256": _sha256_json(before_projection),
        "after_projection_sha256": _sha256_json(after_projection),
        "protected_subtrees": classifications,
        "preservation_observed": True,
        "first_divergence": (
            "SEMANTIC_FIELD"
            if any(value not in {"PRESERVED", "RE_RESOLVED"} for value in classifications.values())
            else None
        ),
    }


def observe_canonical_correction() -> dict[str, Any]:
    """Prove C0 request/projection mechanics without fabricating a post-plan."""
    before = SemanticPlan.model_validate(canonical_revision_plan(include_hint=True))
    before_projection = _protected_projection(before)
    request_facts = _canonical_revision_request(before)
    return {
        "axis": "C",
        "condition": "C0",
        "correction_path": "existing_canonical_correction_request_builder",
        "alternative_correction_paths": 0,
        "request_facts": request_facts,
        "before_projection_sha256": _sha256_json(before_projection),
        "protected_subtrees": "NOT_OBSERVED_PROVIDER_FREE",
        "preservation_evidence": "REQUIRES_ACTUAL_CANONICAL_CORRECTION_RESULT",
        "canonical_model": f"{SemanticPlan.__module__}.{SemanticPlan.__name__}",
        "provider_model_calls": 0,
    }


def classify_first_divergence(boundaries: Mapping[str, str]) -> str | None:
    """Return only the earliest failed boundary from the frozen taxonomy."""
    for boundary in FIRST_DIVERGENCE_ORDER:
        outcome = boundaries.get(boundary, "PASS")
        if outcome != "PASS":
            if outcome != boundary:
                raise ValueError(f"boundary {boundary} has invalid outcome {outcome!r}")
            return boundary
    return None


def field_level_diff(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> list[str]:
    """Return deterministic semantic field paths that differ."""
    return _json_differences(expected, observed)


def inspection_record(
    *,
    axis: str,
    case_id: str,
    expected: Mapping[str, Any],
    model_input: Mapping[str, Any],
    request: Mapping[str, Any],
    response: Mapping[str, Any] | None,
    structured_boundary: Mapping[str, Any],
    canonical_boundary: Mapping[str, Any],
    observed: Mapping[str, Any],
    boundaries: Mapping[str, str],
) -> dict[str, Any]:
    """Build one redacted eight-section inspection record."""
    first = classify_first_divergence(boundaries)
    record = {
        "axis": axis,
        "case_id": case_id,
        "attempt_index": 1,
        "model": "FUTURE_AUTHORIZED_MODEL",
        "provider_boundary": "openai_compat",
        "implementation_checkpoint": "FUTURE_AUTHORIZED_CHECKPOINT",
        "input_hashes": {"model_input": _sha256_json(model_input)},
        "schema_hash": _sha256_json(request.get("response_schema")),
        "prompt_hashes": {
            "system": hashlib.sha256(str(request.get("system_prompt", "")).encode()).hexdigest(),
            "user": hashlib.sha256(str(request.get("user_payload", "")).encode()).hexdigest(),
        },
        "response_hash": _sha256_json(response) if response is not None else None,
        "terminal_status": "PROVIDER_FREE_SYNTHETIC",
        "provider_calls": 0,
        "model_calls": 0,
        "sections": {
            "case_expected_semantics": {"case_id": case_id, "expected": dict(expected)},
            "model_input_state": dict(model_input),
            "exact_model_facing_request": dict(request),
            "exact_raw_model_response": response,
            "structured_output_boundary": dict(structured_boundary),
            "canonical_wellplot_boundary": dict(canonical_boundary),
            "resulting_semantics": dict(observed),
            "evaluation": {
                "field_level_diff": field_level_diff(expected, observed),
                "boundaries": dict(boundaries),
            },
            "first_divergence": first,
        },
    }
    if tuple(record["sections"]) != INSPECTION_SECTIONS:
        raise AssertionError("inspection record section order drifted")
    return record


def synthetic_inspection_artifact() -> dict[str, Any]:
    """Return a deterministic provider-free artifact covering all inspection sections."""
    expected = {"target_identity": "Copper Ridge", "source_identity": "source-ember"}
    model_input = {
        "targets": ["Copper Ridge", "Silver Meadow"],
        "sources": ["source-ember", "source-flint"],
    }
    request = {
        "system_prompt": "canonical planner system contract",
        "user_payload": "synthetic provider-free request",
        "response_schema": canonical_provider_schema(required_section_hint=True),
        "controls": {"temperature": 0.0, "max_output_tokens": None},
    }
    record = inspection_record(
        axis="A",
        case_id="D5-5G-SYNTHETIC-01",
        expected=expected,
        model_input=model_input,
        request=request,
        response={"structured": "synthetic-only"},
        structured_boundary={"json_decode": "PASS", "schema_validation": "PASS"},
        canonical_boundary={"target_resolution": "PASS", "source_resolution": "PASS"},
        observed=expected,
        boundaries=dict.fromkeys(FIRST_DIVERGENCE_ORDER, "PASS"),
    )
    return {
        "artifact": "D5-5G provider-free synthetic inspection",
        "provider_model_calls": 0,
        "sections": list(INSPECTION_SECTIONS),
        "records": [record],
    }


def write_synthetic_inspection_artifact(path: Path) -> None:
    """Write the deterministic inspection artifact without external I/O."""
    path.write_text(
        json.dumps(synthetic_inspection_artifact(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _committed_production_changes(repo_root: Path, current: str) -> list[str]:
    """Compute committed production changes from the accepted design checkpoint."""
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", D5_5G_DESIGN_CHECKPOINT, current],
            cwd=repo_root,
            check=False,
        ).returncode
        != 0
    ):
        raise ValueError("accepted D5-5G design checkpoint is not an ancestor")
    output = _git(
        repo_root,
        "diff",
        "--name-only",
        f"{D5_5G_DESIGN_CHECKPOINT}..{current}",
        "--",
        "src/wellplot",
    )
    return [line for line in output.splitlines() if line]


def future_live_authority_status(authorization: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the explicit future live boundary without contacting anything."""
    authority = str(authorization.get("authorization_id", ""))
    if not authority.startswith(D5_5G_LIVE_AUTHORITY_PREFIX):
        raise PermissionError("D5-5G live authority is absent or not recognized")
    if authorization.get("live_execution") is not True:
        raise PermissionError("D5-5G live execution is not explicitly enabled")
    required = ("implementation_checkpoint", "campaign_id", "artifact_root", "model")
    missing = [key for key in required if not authorization.get(key)]
    if missing:
        raise ValueError(f"future live authority is missing: {missing!r}")
    return {
        "status": "AUTHORIZED_FOR_FUTURE_LIVE_ONLY",
        "authorization_id": authority,
        "campaign_id": str(authorization["campaign_id"]),
        "provider_boundary": "openai_compat",
        "model": str(authorization["model"]),
        "provider_model_calls": 0,
    }


def execute_authorized_live_revalidation(
    repo_root: Path,
    authorization: Mapping[str, Any],
    *,
    executor: Callable[..., object] | None = None,
) -> object:
    """Enter the future live path only with explicit authority and shared D5 runner."""
    future_live_authority_status(authorization)
    current = _git(repo_root, "rev-parse", "HEAD")
    if current != str(authorization["implementation_checkpoint"]):
        raise ValueError("future live authority checkpoint does not match checkout")
    if _committed_production_changes(repo_root, current):
        raise ValueError("future live path cannot run with production-source changes")
    runner = executor or d5.execute_live_campaign
    d5_authorization = d5.D5Authorization.from_mapping(authorization)
    artifact_root = Path(str(authorization["artifact_root"]))
    if not artifact_root.is_absolute():
        artifact_root = repo_root / artifact_root
    return runner(
        repo_root=repo_root,
        authorization=d5_authorization,
        artifact_root=artifact_root,
    )


def _readiness() -> d5.D5ReadinessProjection:
    """Build sanitized readiness facts for the provider-free custody probe."""
    return d5.D5ReadinessProjection(
        model_catalog=("provider-free-contract-probe",),
        model_path_basename="NOT_APPLICABLE",
        model_path_fingerprint_sha256="NOT_APPLICABLE",
        context_size=32768,
        build_info="provider-free D5-5G custody probe",
        total_slots=1,
        chat_template_sha256="NOT_APPLICABLE",
        runtime_defaults_sha256="NOT_APPLICABLE",
        thinking_off=True,
        structured_output_contract="json_schema",
    )


def capture_wire_custody_probe(repo_root: Path, root: Path) -> dict[str, Any]:
    """Exercise the accepted wire observer and campaign custody without I/O."""
    campaign_id = "d5-5g-provider-free-custody"
    authorization = d5.D5Authorization(
        implementation_checkpoint=_git(repo_root, "rev-parse", "HEAD"),
        authorization_id="d5-5g-provider-free-custody-auth",
        campaign_id=campaign_id,
        project_config_fingerprint_sha256=load_project_config(repo_root).fingerprint_sha256,
        provider="openai_compat",
        model="provider-free-contract-probe",
        artifact_root=str(root),
    )
    paths = d5.EvidencePaths(root, campaign_id)
    custody = d5.D5CampaignCustody.start(
        paths,
        authorization=authorization,
        provenance={
            "axis": "custody",
            "implementation_checkpoint": authorization.implementation_checkpoint,
        },
        readiness=_readiness(),
        live=False,
        endpoint_call_count=0,
    )
    observer = d5._PhysicalAttemptObserver()
    observer.callback = custody.record_physical_attempt
    observer.bind_model_io(custody.record_model_io)
    turn_id = "D5-5G-CUSTODY-01"
    custody.begin_turn(turn_id)
    observer.set_active_turn(turn_id)
    event = {
        "event": "logical_call_started",
        "index": 1,
        "generation_role": "planner",
        "provider": "openai_compat",
        "model": authorization.model,
    }
    custody.record_call_started(event)
    observer.logical_call_started(event)
    request_body = json.dumps(
        {
            "model": authorization.model,
            "messages": [{"role": "user", "content": "synthetic contract probe"}],
            "response_format": {"type": "json_schema"},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    response_body = b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'
    request = httpx.Request(
        "POST",
        "https://provider-free.invalid/v1/chat/completions",
        content=request_body,
        headers={"Authorization": "Bearer intentionally-not-recorded"},
    )
    response = httpx.Response(200, content=response_body, request=request)
    asyncio.run(observer.on_request(request))
    asyncio.run(observer.on_response(response))
    custody.record_call_completed(
        {
            "index": 1,
            "generation_role": "planner",
            "provider": authorization.provider,
            "model": authorization.model,
            "outcome": "success",
        }
    )
    custody.append_turn(
        {
            "axis": "custody",
            "case_id": "D5-5G-CUSTODY-01",
            "first_divergence": None,
            "provider_calls": 0,
            "model_calls": 0,
        }
    )
    terminal = custody.finish("PASS", attribution="PROVIDER_FREE_CUSTODY", rows=[{}])
    digests = d5.verify_custody_artifacts(paths)
    model_io = paths.model_io.read_text(encoding="utf-8")
    if "Authorization" in model_io or "intentionally-not-recorded" in model_io:
        raise AssertionError("wire custody captured forbidden credential/header material")
    return {
        "campaign_id": campaign_id,
        "model_io_sha256": digests["model_io_sha256"],
        "terminal_model_io_sha256": terminal["model_io_sha256"],
        "request_sha256_present": "request_sha256" in model_io,
        "response_sha256_present": "response_sha256" in model_io,
        "headers_captured": False,
        "credentials_captured": False,
        "provider_model_calls": 0,
    }


def verify_provider_free(repo_root: Path) -> dict[str, Any]:
    """Run all D5-5G provider-free implementation and custody proofs."""
    current = _git(repo_root, "rev-parse", "HEAD")
    committed_source_changes = _committed_production_changes(repo_root, current)
    if committed_source_changes:
        raise ValueError("D5-5G changed production source")
    subprocess.run(
        [
            "python",
            "scripts/d5_single_engine_attestation.py",
            "--repo-root",
            str(repo_root),
            "--check",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    with TemporaryDirectory(dir=repo_root) as temporary:
        custody = capture_wire_custody_probe(repo_root, Path(temporary))
        inspection_path = Path(temporary) / "D5_5G_SYNTHETIC_INSPECTION_ARTIFACT.json"
        write_synthetic_inspection_artifact(inspection_path)
        inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    divergence_proof = {
        boundary: classify_first_divergence(
            {
                candidate: (candidate if candidate == boundary else "PASS")
                for candidate in FIRST_DIVERGENCE_ORDER
            }
        )
        for boundary in FIRST_DIVERGENCE_ORDER
    }
    return {
        "authority": D5_5G_AUTHORITY,
        "implementation_checkpoint": current,
        "single_engine_attestation": "PASS",
        "axis_a": compare_requiredness_arms(),
        "axis_b": compare_capability_contract_arms(),
        "axis_c": observe_canonical_correction(),
        "wire_custody": custody,
        "first_divergence_taxonomy": {
            "classes": list(FIRST_DIVERGENCE_ORDER),
            "synthetic_earliest_boundary_proof": divergence_proof,
        },
        "inspection_artifact": {
            "status": "PASS",
            "sections": inspection["sections"],
            "record_count": len(inspection["records"]),
        },
        "future_live_harness": {
            "implemented": True,
            "authority_gated": True,
            "disabled_in_provider_free_mode": True,
            "shared_runner": "scripts.nlp_d5_live_semantic_qualification.execute_live_campaign",
        },
        "canonical_engine": D5_5G_SINGLE_ENGINE_ENTRYPOINT,
        "provider_model_calls": PROVIDER_MODEL_CALLS,
        "source_changes": len(committed_source_changes),
        "production_changes": len(committed_source_changes),
    }


def main() -> int:
    """Run provider-free proofs or an explicitly authorized future live path."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--provider-free", action="store_true")
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--authorization-json", type=Path)
    args = parser.parse_args()
    if args.provider_free == args.execute_live:
        parser.error("choose exactly one of --provider-free or --execute-live")
    repo_root = args.repo_root.resolve()
    if args.provider_free:
        print(json.dumps(verify_provider_free(repo_root), indent=2, sort_keys=True))
        return 0
    if args.execute_live:
        if args.authorization_json is None:
            parser.error("--execute-live requires --authorization-json")
        authorization = json.loads(args.authorization_json.read_text(encoding="utf-8"))
        result = execute_authorized_live_revalidation(repo_root, authorization)
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

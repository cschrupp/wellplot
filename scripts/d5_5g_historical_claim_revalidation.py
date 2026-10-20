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
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx

from scripts import nlp_d5_live_semantic_qualification as d5
from wellplot.agent.code_mode.planner import (
    PlannerSemanticError,
    SemanticPlan,
    _correction_request,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.project_config import load_project_config

D5_5G_AUTHORITY = "WELLPLOT-D5-5G-INSPECTABLE-HISTORICAL-CLAIM-REVALIDATION-IMPLEMENTATION-AUTH-001"
D5_5G_DESIGN_CHECKPOINT = "5e530db90babf50c9992f3829d1a11d3cc79e433"
D5_5G_SINGLE_ENGINE_ENTRYPOINT = "wellplot.agent.composition:create_canonical_compile_facade"
PROVIDER_MODEL_CALLS = 0
PROTECTED_SUBTREES = (
    "target_identity",
    "source_clue",
    "scale",
    "presentation",
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


def canonical_revision_plan(*, include_hint: bool) -> dict[str, Any]:
    """Build one generic semantic plan used by both requiredness arms."""
    task: dict[str, Any] = {
        "goal": "Revise the North Star section using the selected source",
        "capability_ids": ["section.log_plot"],
        "source_hints": ["source-alpha"],
        "requirements": ["preserve the requested scale"],
        "constraints": ["do not change unrelated presentation"],
    }
    if include_hint:
        task["existing_section_hint"] = "North Star"
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
    """Prove A0/A1 differ only in the provider-facing requiredness field."""
    a0 = canonical_provider_schema(required_section_hint=False)
    a1 = canonical_provider_schema(required_section_hint=True)
    differences = _schema_differences(a0, a1)
    expected_path = "$.$defs.SectionTask.required"
    if differences != [expected_path]:
        raise AssertionError(f"requiredness arm changed unexpected schema paths: {differences}")
    a0_plan = validate_canonical_plan(canonical_revision_plan(include_hint=False))
    a1_plan = validate_canonical_plan(canonical_revision_plan(include_hint=True))
    if a0_plan["summary"] != a1_plan["summary"]:
        raise AssertionError("requiredness arms changed canonical semantic summary")
    if (
        a0_plan["section_tasks"][0]["capability_ids"]
        != a1_plan["section_tasks"][0]["capability_ids"]
    ):
        raise AssertionError("requiredness arms changed canonical downstream semantics")
    return {
        "axis": "A",
        "arms": ["A0", "A1"],
        "schema_difference_paths": differences,
        "canonical_model": f"{SemanticPlan.__module__}.{SemanticPlan.__name__}",
        "downstream_validation": "SHARED",
        "provider_model_calls": 0,
    }


def capability_contract(arm: str) -> dict[str, Any]:
    """Return a generic capability-local contract input for one study arm."""
    if arm == "B0":
        return {"version": "d5-5g-capability-contract.v1", "mappings": []}
    if arm == "B1":
        return {
            "version": "d5-5g-capability-contract.v1",
            "mappings": [
                {
                    "concept": "track width",
                    "language_patterns": ["width of the selected track"],
                    "targets": ["track.width_mm"],
                    "positive_example": "Set the selected track width to 18 mm",
                    "negative_example": "Do not change the selected track color",
                }
            ],
        }
    raise ValueError(f"unknown capability-contract arm: {arm}")


def compare_capability_contract_arms() -> dict[str, Any]:
    """Prove B0/B1 vary only generic capability-local contract text."""
    b0 = capability_contract("B0")
    b1 = capability_contract("B1")
    if b0["version"] != b1["version"]:
        raise AssertionError("capability-contract arms changed contract version")
    if b0["mappings"] or len(b1["mappings"]) != 1:
        raise AssertionError("capability-contract arm shape drifted")
    serialized = json.dumps(b1["mappings"], sort_keys=True).casefold()
    forbidden = ("formation integrity", "cbl", "las", "nphi", "d4-", "d5-")
    if any(marker in serialized for marker in forbidden):
        raise AssertionError("capability contract contains qualification-specific answers")
    return {
        "axis": "B",
        "arms": ["B0", "B1"],
        "changed_surface": "capability_local_contract_text",
        "schema_context_evaluator": "SHARED",
        "synthetic_examples": "GENERIC",
        "provider_model_calls": 0,
    }


def _canonical_revision_request(plan: SemanticPlan) -> dict[str, Any]:
    """Build the actual canonical correction request without calling a model."""
    request = _correction_request(
        mode="revise",
        request="Revise the North Star section using source-alpha.",
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
) -> dict[str, str]:
    """Classify each protected subtree after canonical correction."""
    result: dict[str, str] = {}
    for key in PROTECTED_SUBTREES:
        if key not in before or key not in after:
            result[key] = "AMBIGUOUS"
        elif before[key] == after[key]:
            result[key] = "PRESERVED"
        elif after[key] is None:
            result[key] = "DROPPED"
        elif isinstance(before[key], list) and isinstance(after[key], list):
            result[key] = "RE_RESOLVED" if len(before[key]) == len(after[key]) else "CHANGED"
        else:
            result[key] = "CHANGED"
    return result


def observe_canonical_correction() -> dict[str, Any]:
    """Observe C0 projections around the existing canonical correction builder."""
    before = SemanticPlan.model_validate(canonical_revision_plan(include_hint=True))
    after_payload = canonical_revision_plan(include_hint=True)
    after_payload["unresolved_requirements"] = []
    after = SemanticPlan.model_validate(after_payload)
    before_projection = _protected_projection(before)
    after_projection = _protected_projection(after)
    classifications = classify_protected_subtrees(before_projection, after_projection)
    request_facts = _canonical_revision_request(before)
    if any(value != "PRESERVED" for value in classifications.values()):
        raise AssertionError("provider-free C0 fixture changed a protected subtree")
    return {
        "axis": "C",
        "condition": "C0",
        "correction_path": "existing_canonical_correction_builder",
        "alternative_correction_paths": 0,
        "request_facts": request_facts,
        "protected_subtrees": classifications,
        "canonical_model": f"{SemanticPlan.__module__}.{SemanticPlan.__name__}",
        "provider_model_calls": 0,
    }


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
    """Run all D5-5G provider-free implementation proofs."""
    current = _git(repo_root, "rev-parse", "HEAD")
    ancestor = (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", D5_5G_DESIGN_CHECKPOINT, current],
            cwd=repo_root,
            check=False,
        ).returncode
        == 0
    )
    if current != D5_5G_DESIGN_CHECKPOINT and not ancestor:
        raise ValueError("D5-5G implementation is not based on the accepted design")
    if subprocess.run(
        ["git", "diff", "--name-only", "--", "src/wellplot"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip():
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
    return {
        "authority": D5_5G_AUTHORITY,
        "implementation_checkpoint": current,
        "single_engine_attestation": "PASS",
        "axis_a": compare_requiredness_arms(),
        "axis_b": compare_capability_contract_arms(),
        "axis_c": observe_canonical_correction(),
        "wire_custody": custody,
        "canonical_engine": D5_5G_SINGLE_ENGINE_ENTRYPOINT,
        "provider_model_calls": PROVIDER_MODEL_CALLS,
        "source_changes": 0,
        "production_changes": 0,
    }


def main() -> int:
    """Run only the provider-free D5-5G implementation proof."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--provider-free", action="store_true")
    args = parser.parse_args()
    if not args.provider_free:
        parser.error("D5-5G live execution is not part of this implementation")
    print(json.dumps(verify_provider_free(args.repo_root.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

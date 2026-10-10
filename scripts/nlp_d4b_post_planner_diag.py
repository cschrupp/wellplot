"""Bounded post-planner diagnosis for the frozen D4 CBL request."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

from scripts import nlp_d4_live_acceptance as d4
from wellplot.agent.code_mode.capability_safety import enforce_capability_safety
from wellplot.agent.code_mode.enrichment import (
    EnrichedSemanticContext,
    SemanticEnricher,
    SourceCandidate,
)
from wellplot.agent.code_mode.planner import SemanticPlan, SemanticPlanner
from wellplot.agent.code_mode.report_boundary_safety import enforce_report_boundary_safety
from wellplot.agent.code_mode.section_leaf_safety import enforce_section_leaf_safety
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.direct_notebook import (
    _load_document_context,
    _NotebookDocumentContext,
    _provider_backend,
)
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import create_builtin_registry


def _case(repo_root: Path) -> dict[str, Any]:
    """Load the one frozen CBL turn without retaining its request in evidence."""
    return next(item for item in d4.load_cases(repo_root) if item["turn_id"] == "D4-C01:C01")


def _plan_facts(plan: SemanticPlan) -> dict[str, Any]:
    """Project only bounded structural facts from one validated semantic plan."""
    report = plan.report_task
    return {
        "summary_length": len(plan.summary),
        "report_task_present": report is not None,
        "report_capability_ids": [] if report is None else list(report.capability_ids),
        "report_requirements_count": 0 if report is None else len(report.requirements),
        "report_constraints_count": 0 if report is None else len(report.constraints),
        "section_task_count": len(plan.section_tasks),
        "section_tasks": [
            {
                "index": index,
                "capability_ids": list(task.capability_ids),
                "existing_section_hint": task.existing_section_hint,
                "source_hints": list(task.source_hints),
                "requirements_count": len(task.requirements),
                "constraints_count": len(task.constraints),
            }
            for index, task in enumerate(plan.section_tasks)
        ],
        "unresolved_requirements_count": len(plan.unresolved_requirements),
    }


def _source_summary(context: _NotebookDocumentContext) -> dict[str, Any]:
    """Build the same provider-safe source summary used by the real graph."""
    return {
        "version": "cm56r3.source-summary.v1",
        "sources": [
            {"labels": list(source.labels), "channels": []} for source in context.source_candidates
        ],
    }


def _dispatch_facts(plan: SemanticPlan, context: EnrichedSemanticContext) -> dict[str, Any]:
    """Validate dispatch pairing without invoking either worker backend."""
    if len(context.sections) != len(plan.section_tasks):
        raise ValueError("enriched section context does not match semantic plan")
    for index, section_context in enumerate(context.sections):
        if section_context.task_index != index:
            raise ValueError("enriched section context order does not match plan")
    return {
        "report_worker_units": int(plan.report_task is not None),
        "section_worker_units": len(plan.section_tasks),
        "worker_model_calls": 0,
    }


async def _run(repo_root: Path) -> dict[str, Any]:
    """Run one live planner call sequence and replay it deterministically."""
    case = _case(repo_root)
    api_key = os.environ.get("OPENAI_COMPAT_API_KEY")
    if not api_key:
        return {"stage_b": "NOT_RUN", "failure_stage": "credential_unavailable"}

    with TemporaryDirectory(dir=repo_root) as temporary:
        artifact_root = Path(temporary)
        session_stub = SimpleNamespace(provider=d4.EXPECTED_PROVIDER, model=d4.EXPECTED_MODEL)
        adapter = d4.D4CampaignAdapter(
            repo_root=repo_root,
            artifact_root=artifact_root,
            session=session_stub,
            call_source=d4.CampaignCallSource(backends=(), calls=[]),
        )
        scaffold = artifact_root / "cbl-scaffold.log.yaml"
        adapter._write_cbl_scaffold(scaffold)
        context = _load_document_context(scaffold, root=repo_root)
        registry = create_builtin_registry()
        backend, _credential_source = _provider_backend(
            provider=d4.EXPECTED_PROVIDER,
            model=d4.EXPECTED_MODEL,
            root=repo_root,
            api_key=api_key,
            base_url=d4.OPENAI_COMPAT_BASE_URL,
            timeout=d4.LIVE_GENERATION_TIMEOUT_SECONDS,
        )
        calls: list[d4.LogicalCall] = []
        counted = d4.CountingBackend(
            delegate=backend,
            provider=d4.EXPECTED_PROVIDER,
            model=d4.EXPECTED_MODEL,
            max_calls=2,
            calls=calls,
            ledger=d4.LogicalCallLedger(max_calls=2),
        )
        planner = SemanticPlanner(backend=counted, registry=registry)
        summary = AuthoringInspectionFacade(context.document).document_summary()
        try:
            plan = await planner.plan(
                request=str(case["request"]),
                mode="reconstruct",
                current_document_summary=summary.model_dump(mode="json"),
                source_summary=_source_summary(context),
                timeout_seconds=d4.LIVE_GENERATION_TIMEOUT_SECONDS,
                temperature=0.0,
                max_output_tokens=None,
            )
        except Exception as error:
            return {
                "stage_b": "FAIL",
                "failure_stage": "planner",
                "exception_class": type(error).__name__,
                "logical_calls": len(calls),
                "worker_model_calls": 0,
            }

        result: dict[str, Any] = {
            "stage_b": "PASS",
            "planner_call_count": len(calls),
            "planner_calls": [
                {
                    "index": call.index,
                    "operation": call.operation,
                    "outcome": call.outcome,
                    "failure_category": call.category,
                    "latency_ms": call.metrics.get("latency_ms"),
                    "input_tokens": call.metrics.get("input_tokens"),
                    "output_tokens": call.metrics.get("output_tokens"),
                    "total_tokens": call.metrics.get("total_tokens"),
                }
                for call in calls
            ],
            "validated_plan": _plan_facts(plan),
            "worker_model_calls": 0,
        }
        replay_stage = "planner_complete"
        try:
            capability = enforce_capability_safety(
                request=str(case["request"]), plan=plan, registry=registry
            )
            replay_stage = "capability_safety_complete"
            report = enforce_report_boundary_safety(
                request=str(case["request"]), plan=capability.safe_plan, registry=registry
            )
            replay_stage = "report_boundary_safety_complete"
            leaf = enforce_section_leaf_safety(
                request=str(case["request"]), plan=report.safe_plan, registry=registry
            )
            replay_stage = "section_leaf_safety_complete"
            source_candidates = tuple(
                SourceCandidate.model_validate(source.model_dump(mode="json"))
                for source in context.source_candidates
            )
            enriched = SemanticEnricher(
                loader=LogfileSourceLoader(), allowed_roots={"server": repo_root}
            ).enrich(
                plan=leaf.safe_plan,
                document=context.document,
                source_candidates=source_candidates,
                mode="reconstruct",
            )
            replay_stage = "enrichment_complete"
            result["dispatch"] = _dispatch_facts(leaf.safe_plan, enriched)
            result["last_completed_stage"] = "dispatch_construction_complete"
            result["failing_stage"] = None
            result["failure_domain"] = None
        except Exception as error:
            result["stage_b"] = "FAIL"
            result["last_completed_stage"] = replay_stage
            result["failing_stage"] = replay_stage
            result["failure_domain"] = type(error).__name__
            result["failure_code"] = getattr(error, "code", None)
        return result


def main() -> int:
    """Run the bounded diagnostic and print sanitized structural evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.repo_root.resolve())), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

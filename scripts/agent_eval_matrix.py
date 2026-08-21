"""Fixture resolution and evidence aggregation for agent evaluations.

This module deliberately does not contact providers.  It makes live execution
data-driven and turns one-provider evidence files into a comparable matrix.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.agent_eval_support import redact
except ModuleNotFoundError:
    from agent_eval_support import redact  # type: ignore[no-redef]


@dataclass(frozen=True)
class FixtureSpec:
    """One task fixture and its canonical input artifacts."""

    fixture_id: str
    root: Path
    starter_logfile: Path | None
    initial_document: Path | None
    baseline_document: Path | None
    description: str

    @property
    def missing_paths(self) -> tuple[Path, ...]:
        """Return declared artifacts that are absent from this checkout."""
        candidates = (
            self.root,
            self.starter_logfile,
            self.initial_document,
            self.baseline_document,
        )
        return tuple(path for path in candidates if path is not None and not path.exists())


def _relative_path(root: Path, raw_value: object, *, field_name: str) -> Path | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"Fixture field {field_name!r} must be a relative path or null.")
    raw_path = Path(raw_value)
    if raw_path.is_absolute():
        raise ValueError(f"Fixture field {field_name!r} must be relative to the fixture root.")
    resolved = (root / raw_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Fixture field {field_name!r} escapes the fixture root.") from exc
    return resolved


def load_fixture_catalog(path: str | Path, *, repo_root: str | Path) -> dict[str, FixtureSpec]:
    """Load and validate the repository-relative fixture catalog."""
    catalog_path = Path(path).resolve()
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("Fixture catalog must be a JSON object with version 1.")
    raw_root = payload.get("root")
    raw_fixtures = payload.get("fixtures")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ValueError("Fixture catalog must define a non-empty root.")
    if not isinstance(raw_fixtures, dict) or not raw_fixtures:
        raise ValueError("Fixture catalog must define a non-empty fixtures object.")

    repository = Path(repo_root).resolve()
    fixture_root = (repository / raw_root).resolve()
    try:
        fixture_root.relative_to(repository)
    except ValueError as exc:
        raise ValueError("Fixture catalog root must remain inside repo_root.") from exc

    fixtures: dict[str, FixtureSpec] = {}
    for fixture_id, raw_fixture in raw_fixtures.items():
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("Fixture ids must be non-empty strings.")
        if not isinstance(raw_fixture, dict):
            raise ValueError(f"Fixture {fixture_id!r} must be an object.")
        fixture_dir = (fixture_root / fixture_id).resolve()
        try:
            fixture_dir.relative_to(fixture_root)
        except ValueError as exc:
            raise ValueError(f"Fixture id {fixture_id!r} escapes the fixture root.") from exc
        fixtures[fixture_id] = FixtureSpec(
            fixture_id=fixture_id,
            root=fixture_dir,
            starter_logfile=_relative_path(
                fixture_dir,
                raw_fixture.get("starter_logfile"),
                field_name="starter_logfile",
            ),
            initial_document=_relative_path(
                fixture_dir,
                raw_fixture.get("initial_document"),
                field_name="initial_document",
            ),
            baseline_document=_relative_path(
                fixture_dir,
                raw_fixture.get("baseline_document"),
                field_name="baseline_document",
            ),
            description=str(raw_fixture.get("description", "")),
        )
    return fixtures


def classify_failure(result: dict[str, Any]) -> str:
    """Assign one remediation category to a failed evidence result."""
    text = " ".join(
        str(value)
        for key in ("errors", "warnings", "reason")
        for value in (result.get(key) or [])
        if value is not None
    ).lower()
    if any(term in text for term in ("validation", "schema", "required field", "unknown tool")):
        return "contract/schema"
    if any(
        term in text for term in ("unknown section", "unknown track", "postcondition", "invariant")
    ):
        return "state invariant"
    if any(term in text for term in ("unavailable", "unsupported", "missing capability")):
        return "missing capability"
    if any(term in text for term in ("timeout", "connection", "incomplete read", "transport")):
        return "transient infrastructure"
    if any(term in text for term in ("host", "fallback", "scope")):
        return "host policy interference"
    if any(term in text for term in ("context", "token", "round")):
        return "resource/context overload"
    if any(term in text for term in ("server", "mcp")):
        return "server semantics"
    return "provider reasoning"


def aggregate_matrix(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate one or more redacted provider reports without false greens."""
    cases: list[dict[str, Any]] = []
    provider_totals: dict[str, Counter[str]] = {}
    failure_categories: Counter[str] = Counter()
    for report in reports:
        provider = str(report.get("provider") or "unknown")
        model = report.get("model")
        for task in report.get("tasks", []):
            if not isinstance(task, dict):
                continue
            status = str(task.get("status", "not_run"))
            provider_totals.setdefault(provider, Counter())[status] += 1
            case = {
                "provider": provider,
                "model": model,
                "task_id": task.get("task_id"),
                "fixture": task.get("fixture"),
                "status": status,
            }
            if status == "failed":
                category = classify_failure(task)
                failure_categories[category] += 1
                case["failure_category"] = category
            if status == "not_run":
                case["reason"] = task.get("reason", "not run")
            cases.append(case)

    providers: dict[str, dict[str, Any]] = {}
    for provider, counts in sorted(provider_totals.items()):
        eligible = counts.get("passed", 0) + counts.get("failed", 0)
        providers[provider] = {
            "passed": counts.get("passed", 0),
            "failed": counts.get("failed", 0),
            "not_run": counts.get("not_run", 0),
            "eligible_cases": eligible,
            "pass_at_1": (counts.get("passed", 0) / eligible) if eligible else None,
        }
    return redact(
        {
            "mode": "matrix",
            "live_execution": False,
            "providers": providers,
            "cases": cases,
            "failure_categories": dict(sorted(failure_categories.items())),
            "not_run_cases": sum(1 for case in cases if case["status"] == "not_run"),
        }
    )

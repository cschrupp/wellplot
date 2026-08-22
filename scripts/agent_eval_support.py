"""Shared helpers for the opt-in MCP/agent capability evaluation scripts."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wellplot.authoring import load_authoring_document

_MISSING = object()
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|authorization|password|secret|token)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"((?:api[_-]?key|access[_-]?token|authorization|password|secret|token)"
    r"\s*[:=]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_QUERY = re.compile(
    r"([?&](?:api[_-]?key|access[_-]?token|authorization|secret|token)="
    r")[^&\s]+",
    re.IGNORECASE,
)
_SUPPORTED_TASK_KINDS = frozenset({"run", "revise"})
_SUPPORTED_TASK_STATUSES = frozenset({"active", "deferred"})
_SUPPORTED_ASSERTION_OPERATORS = frozenset(
    {
        "contains",
        "contains_ci",
        "contains_object",
        "equals",
        "exists",
        "length",
        "length_at_least",
        "not_contains_object",
    }
)


@dataclass(frozen=True)
class EvalTask:
    """One data-driven capability task."""

    task_id: str
    kind: str
    status: str
    initial_state: dict[str, Any]
    goal: str | None
    feedback: str | None
    expected: tuple[dict[str, Any], ...]
    allowed_change_paths: tuple[str, ...]
    prohibited_change_paths: tuple[str, ...]
    expected_outcome: dict[str, Any]


def load_task_suite(path: str | Path) -> tuple[str, tuple[EvalTask, ...]]:
    """Load and validate the JSON task suite used by the evaluation runner."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Evaluation suite must contain a JSON object.")
    suite_name = payload.get("suite")
    raw_tasks = payload.get("tasks")
    if not isinstance(suite_name, str) or not suite_name.strip():
        raise ValueError("Evaluation suite must define a non-empty 'suite'.")
    if not isinstance(raw_tasks, list):
        raise ValueError("Evaluation suite must define a 'tasks' list.")

    tasks: list[EvalTask] = []
    seen_ids: set[str] = set()
    for raw_task in raw_tasks:
        if not isinstance(raw_task, Mapping):
            raise ValueError("Every evaluation task must be an object.")
        task_id = raw_task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("Every evaluation task must define a non-empty 'id'.")
        if task_id in seen_ids:
            raise ValueError(f"Duplicate evaluation task id: {task_id}")
        seen_ids.add(task_id)
        kind = raw_task.get("kind")
        status = raw_task.get("status")
        initial_state = raw_task.get("initial_state")
        expected = raw_task.get("expected")
        allowed_change_paths = raw_task.get("allowed_change_paths")
        prohibited_change_paths = raw_task.get("prohibited_change_paths")
        expected_outcome = raw_task.get("expected_outcome", {})
        goal = raw_task.get("goal")
        feedback = raw_task.get("feedback")
        if kind not in _SUPPORTED_TASK_KINDS:
            raise ValueError(f"Task {task_id} has unsupported kind {kind!r}.")
        if status not in _SUPPORTED_TASK_STATUSES:
            raise ValueError(f"Task {task_id} has unsupported status {status!r}.")
        if not isinstance(initial_state, Mapping):
            raise ValueError(f"Task {task_id} must define an initial_state object.")
        fixture = initial_state.get("fixture")
        preconditions = initial_state.get("preconditions")
        if not isinstance(fixture, str) or not fixture.strip():
            raise ValueError(f"Task {task_id} initial_state requires a fixture name.")
        if not isinstance(preconditions, list) or not preconditions:
            raise ValueError(f"Task {task_id} initial_state requires preconditions.")
        if not all(isinstance(item, Mapping) for item in preconditions):
            raise ValueError(f"Task {task_id} has invalid initial-state preconditions.")
        if kind == "run" and (not isinstance(goal, str) or not goal.strip()):
            raise ValueError(f"Run task {task_id} requires a non-empty goal.")
        if kind == "revise" and (not isinstance(feedback, str) or not feedback.strip()):
            raise ValueError(f"Revise task {task_id} requires non-empty feedback.")
        if not isinstance(expected, list) or not all(
            isinstance(item, Mapping) for item in expected
        ):
            raise ValueError(f"Task {task_id} has invalid expected assertions.")
        if not expected:
            raise ValueError(f"Task {task_id} requires expected final-state assertions.")
        if not isinstance(allowed_change_paths, list) or not all(
            isinstance(item, str) for item in allowed_change_paths
        ):
            raise ValueError(f"Task {task_id} has invalid allowed_change_paths.")
        if not isinstance(prohibited_change_paths, list) or not all(
            isinstance(item, str) for item in prohibited_change_paths
        ):
            raise ValueError(f"Task {task_id} has invalid prohibited_change_paths.")
        if not isinstance(expected_outcome, Mapping):
            raise ValueError(f"Task {task_id} has invalid expected_outcome.")
        _validate_assertions(task_id, preconditions)
        _validate_assertions(task_id, expected)
        _validate_paths(task_id, "allowed_change_paths", allowed_change_paths)
        _validate_paths(task_id, "prohibited_change_paths", prohibited_change_paths)
        if _paths_overlap(allowed_change_paths, prohibited_change_paths):
            raise ValueError(f"Task {task_id} allows and prohibits overlapping change paths.")
        tasks.append(
            EvalTask(
                task_id=task_id,
                kind=kind,
                status=status,
                initial_state=dict(initial_state),
                goal=goal if isinstance(goal, str) else None,
                feedback=feedback if isinstance(feedback, str) else None,
                expected=tuple(dict(item) for item in expected),
                allowed_change_paths=tuple(allowed_change_paths),
                prohibited_change_paths=tuple(prohibited_change_paths),
                expected_outcome=dict(expected_outcome),
            )
        )
    return suite_name, tuple(tasks)


def redact(value: object) -> object:
    """Redact credential-like values before they enter evaluation evidence."""
    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = _SECRET_ASSIGNMENT.sub(r"\1<redacted>", value)
        return _SECRET_QUERY.sub(r"\1<redacted>", value)
    return value


def _decode_pointer_part(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def get_json_pointer(document: object, pointer: str) -> object:
    """Read one RFC 6901-style JSON pointer, returning a missing sentinel."""
    if pointer in {"", "/"}:
        return document
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer}")
    current = document
    for raw_part in pointer[1:].split("/"):
        part = _decode_pointer_part(raw_part)
        if isinstance(current, Mapping):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            try:
                current = current[int(part)]
            except (IndexError, TypeError, ValueError):
                return _MISSING
        else:
            return _MISSING
    return current


def _validate_paths(task_id: str, field_name: str, paths: Sequence[str]) -> None:
    for path in paths:
        if path != "" and not path.startswith("/"):
            raise ValueError(f"Task {task_id} {field_name} contains invalid pointer {path!r}.")


def _validate_assertions(task_id: str, assertions: Sequence[Mapping[str, Any]]) -> None:
    for assertion in assertions:
        path = assertion.get("path")
        operator = assertion.get("operator", "equals")
        if not isinstance(path, str) or (path != "" and not path.startswith("/")):
            raise ValueError(f"Task {task_id} assertion has invalid path {path!r}.")
        if operator not in _SUPPORTED_ASSERTION_OPERATORS:
            raise ValueError(f"Task {task_id} uses unsupported operator {operator!r}.")
        if operator in {"contains_object", "not_contains_object"} and not isinstance(
            assertion.get("value"), Mapping
        ):
            raise ValueError(f"Task {task_id} {operator} requires an object value.")


def _path_is_within(path: str, prefix: str) -> bool:
    if prefix in {"", "/"}:
        return True
    return path == prefix or path.startswith(f"{prefix}/")


def _paths_overlap(first: Sequence[str], second: Sequence[str]) -> bool:
    return any(
        _path_is_within(first_path, second_path) or _path_is_within(second_path, first_path)
        for first_path in first
        for second_path in second
    )


def _flatten(value: object, path: str = "") -> dict[str, object]:
    if isinstance(value, Mapping):
        if not value:
            return {path or "/": {}}
        result: dict[str, object] = {}
        for key, child in value.items():
            child_path = f"{path}/{str(key).replace('~', '~0').replace('/', '~1')}"
            result.update(_flatten(child, child_path))
        return result
    if isinstance(value, list):
        if not value:
            return {path or "/": []}
        result: dict[str, object] = {}
        for index, child in enumerate(value):
            result.update(_flatten(child, f"{path}/{index}"))
        return result
    return {path or "/": value}


def canonical_diff(before: object, after: object) -> list[dict[str, object]]:
    """Return redacted leaf-level differences between two JSON-like values."""
    before_flat = _flatten(before)
    after_flat = _flatten(after)
    changes: list[dict[str, object]] = []
    for path in sorted(set(before_flat) | set(after_flat)):
        old = before_flat.get(path, _MISSING)
        new = after_flat.get(path, _MISSING)
        if old == new:
            continue
        changes.append(
            {
                "path": path,
                "before": None if old is _MISSING else redact(old),
                "after": None if new is _MISSING else redact(new),
            }
        )
    return changes


def _matches_subset(actual: object, expected: object) -> bool:
    """Return whether an expected semantic object is present in an actual object."""
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        return all(
            key in actual and _matches_subset(actual[key], expected_value)
            for key, expected_value in expected.items()
        )
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes, bytearray)):
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes, bytearray)):
            return False
        unmatched = list(actual)
        for expected_item in expected:
            match_index = next(
                (
                    index
                    for index, actual_item in enumerate(unmatched)
                    if _matches_subset(actual_item, expected_item)
                ),
                None,
            )
            if match_index is None:
                return False
            unmatched.pop(match_index)
        return True
    return actual == expected


def _contains_text(value: object, expected: str) -> bool:
    if isinstance(value, str):
        return expected.casefold() in value.casefold()
    if isinstance(value, Mapping):
        return any(_contains_text(item, expected) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_text(item, expected) for item in value)
    return False


def _check_assertion(document: object, assertion: Mapping[str, Any]) -> str | None:
    path = assertion.get("path")
    operator = assertion.get("operator", "equals")
    if not isinstance(path, str) or not isinstance(operator, str):
        return "assertion requires string path and operator"
    actual = get_json_pointer(document, path)
    if operator == "exists":
        expected = bool(assertion.get("value", True))
        if (actual is not _MISSING) != expected:
            return f"{path}: exists expected {expected}, got {actual is not _MISSING}"
        return None
    if actual is _MISSING:
        return f"{path}: value is missing"
    expected = assertion.get("value")
    if operator == "equals" and actual != expected:
        return f"{path}: expected {expected!r}, got {actual!r}"
    if operator == "contains":
        if (isinstance(actual, str) and isinstance(expected, str)) or isinstance(actual, list):
            matched = expected in actual
        else:
            matched = False
        if not matched:
            return f"{path}: expected to contain {expected!r}"
    elif operator == "contains_ci":
        if not isinstance(expected, str):
            return f"{path}: case-insensitive containment requires a string value"
        if not _contains_text(actual, expected):
            return f"{path}: expected to contain {expected!r} (case-insensitive)"
    elif operator == "contains_object":
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes, bytearray)):
            return f"{path}: object containment requires a collection"
        if not any(_matches_subset(item, expected) for item in actual):
            return f"{path}: expected to contain object {expected!r}"
    elif operator == "not_contains_object":
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes, bytearray)):
            return f"{path}: object exclusion requires a collection"
        if any(_matches_subset(item, expected) for item in actual):
            return f"{path}: expected not to contain object {expected!r}"
    elif operator == "length":
        if not isinstance(actual, (str, list, tuple, Mapping)):
            return f"{path}: value has no length"
        if len(actual) != expected:
            return f"{path}: expected length {expected!r}, got {len(actual)}"
    elif operator == "length_at_least":
        if not isinstance(actual, (str, list, tuple, Mapping)):
            return f"{path}: value has no length"
        if not isinstance(expected, int) or len(actual) < expected:
            return f"{path}: expected length of at least {expected!r}, got {len(actual)}"
    elif operator not in {"equals", "contains", "contains_ci"}:
        return f"{path}: unsupported assertion operator {operator!r}"
    return None


def grade_document(
    document_path: str | Path | None,
    task: EvalTask,
    *,
    baseline_path: str | Path | None = None,
    outcome: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Grade one persisted document against canonical task postconditions."""
    result: dict[str, Any] = {
        "task_id": task.task_id,
        "kind": task.kind,
        "status": "not_run",
        "errors": [],
        "canonical_diff": [],
    }
    if task.status != "active":
        result["reason"] = f"task is marked {task.status}"
        return result
    if document_path is None:
        result["reason"] = "no persisted document was provided"
        return result
    path = Path(document_path)
    if not path.exists():
        result["reason"] = f"document does not exist: {path}"
        return result
    try:
        document = load_authoring_document(path)
        payload = document.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - evidence must contain validation failures.
        result["status"] = "failed"
        result["errors"] = [f"document validation failed: {exc}"]
        return redact(result)

    errors = [
        error
        for assertion in task.expected
        if (error := _check_assertion(payload, assertion)) is not None
    ]
    if task.expected_outcome:
        if outcome is None:
            errors.append("expected agent outcome was not provided")
        else:
            for key, expected_value in task.expected_outcome.items():
                actual_value = outcome.get(key, _MISSING)
                if actual_value != expected_value:
                    errors.append(
                        f"agent outcome {key!r}: expected {expected_value!r}, "
                        f"got {None if actual_value is _MISSING else actual_value!r}"
                    )
    if baseline_path is None:
        errors.append("baseline document is required for initial-state and isolation checks")
    else:
        try:
            baseline = load_authoring_document(baseline_path).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - report the baseline defect.
            errors.append(f"baseline validation failed: {exc}")
        else:
            errors.extend(
                f"initial state {error}"
                for assertion in task.initial_state["preconditions"]
                if (error := _check_assertion(baseline, assertion)) is not None
            )
            for path_value in task.prohibited_change_paths:
                before = get_json_pointer(baseline, path_value)
                after = get_json_pointer(payload, path_value)
                if before != after:
                    errors.append(f"{path_value}: prohibited unrelated mutation")
            for change in canonical_diff(baseline, payload):
                change_path = str(change["path"])
                if task.allowed_change_paths and not any(
                    _path_is_within(change_path, allowed_path)
                    for allowed_path in task.allowed_change_paths
                ):
                    errors.append(f"{change_path}: mutation falls outside allowed change paths")
                if not task.allowed_change_paths:
                    errors.append(f"{change_path}: task does not allow persisted mutations")
    result["status"] = "passed" if not errors else "failed"
    result["errors"] = errors
    result["canonical_document"] = str(path)
    if baseline_path is not None and Path(baseline_path).exists():
        baseline_payload = load_authoring_document(baseline_path).model_dump(mode="json")
        result["canonical_diff"] = canonical_diff(baseline_payload, payload)
    return redact(result)


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def _git_output(repo_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def collect_architecture_metrics(repo_root: str | Path) -> dict[str, Any]:
    """Collect stable, source-level architecture measurements for one checkout."""
    root = Path(repo_root).resolve()
    production_paths = (
        "src/wellplot/agent/core.py",
        "src/wellplot/agent/tool_contract.py",
        "src/wellplot/agent/compilation.py",
        "src/wellplot/agent/branch_compiler.py",
        "src/wellplot/agent/operation_executor.py",
        "src/wellplot/agent/providers/_openai_chat.py",
        "src/wellplot/agent/providers/_openai_responses.py",
        "src/wellplot/mcp/server.py",
        "src/wellplot/mcp/stable.py",
        "src/wellplot/mcp/service.py",
    )
    line_counts = {
        path: _line_count(root / path) for path in production_paths if (root / path).exists()
    }
    agent_files = list((root / "src/wellplot/agent").rglob("*.py"))
    try:
        from wellplot.authoring_service import authoring_operation_json_schema

        operation_schema_chars = len(
            json.dumps(authoring_operation_json_schema(), sort_keys=True, separators=(",", ":"))
        )
        schema_error = None
    except Exception as exc:  # noqa: BLE001 - preserve diagnostic output.
        operation_schema_chars = None
        schema_error = str(exc)
    try:
        from wellplot.agent.tool_contract import stable_tool_budget

        stable_contract = stable_tool_budget()
        stable_contract_error = None
    except Exception as exc:  # noqa: BLE001 - preserve diagnostic output.
        stable_contract = None
        stable_contract_error = str(exc)
    server_path = root / "src/wellplot/mcp/server.py"
    try:
        from wellplot.agent.tool_contract import stable_tool_profile

        tool_count = len(stable_tool_profile())
    except Exception:  # noqa: BLE001 - preserve diagnostic output.
        tool_count = (
            len(
                re.findall(
                    r"^\s*@mcp\.tool\b",
                    server_path.read_text(encoding="utf-8"),
                    flags=re.MULTILINE,
                )
            )
            if server_path.exists()
            else 0
        )
    agent_text = "\n".join(path.read_text(encoding="utf-8") for path in agent_files)
    return {
        "git_commit": _git_output(root, "rev-parse", "HEAD"),
        "production_line_counts": line_counts,
        "agent_python_lines": sum(_line_count(path) for path in agent_files),
        "mcp_tool_count": tool_count,
        "generated_submit_symbol_count": len(
            set(re.findall(r"\bsubmit_[a-zA-Z_][a-zA-Z0-9_]*\b", agent_text))
        ),
        "authoring_operation_schema_chars": operation_schema_chars,
        "schema_error": schema_error,
        "stable_tool_budget": stable_contract,
        "stable_tool_contract_error": stable_contract_error,
    }

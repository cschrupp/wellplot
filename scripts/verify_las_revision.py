"""Deterministic before/after acceptance checks for LAS authoring revisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from wellplot.authoring import load_authoring_document

PASS = "PASS"
FAIL = "FAIL"
NOT_CHECKABLE = "NOT_CHECKABLE"
HARNESS_ERROR = "HARNESS_ERROR"

_REQUIREMENT_IDS = (
    "LAS-01",
    "LAS-02",
    "LAS-03",
    "LAS-04",
    "LAS-05",
    "LAS-06",
    "LAS-07",
    "LAS-08",
    "LAS-09",
)
_CHANGE_REQUIREMENT_IDS = frozenset({"LAS-02", "LAS-03", "LAS-04", "LAS-05", "LAS-06"})
_MISSING = object()


def _decode_pointer_part(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _get_pointer(document: object, pointer: str) -> object:
    """Read an RFC 6901 JSON pointer and return a missing sentinel."""
    if pointer in {"", "/"}:
        return document
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer!r}")
    current = document
    for raw_part in pointer[1:].split("/"):
        part = _decode_pointer_part(raw_part)
        if isinstance(current, Mapping):
            current = current.get(part, _MISSING)
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            try:
                current = current[int(part)]
            except (IndexError, TypeError, ValueError):
                return _MISSING
        else:
            return _MISSING
        if current is _MISSING:
            return current
    return current


def _path_is_within(actual: str, allowed: str) -> bool:
    return actual == allowed or actual.startswith(allowed.rstrip("/") + "/")


def _canonical_diff(before: object, after: object, path: str = "") -> list[dict[str, object]]:
    """Return semantic JSON differences without comparing source-file bytes."""
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        differences: list[dict[str, object]] = []
        keys = sorted(set(before) | set(after), key=str)
        for key in keys:
            child_path = f"{path}/{key}" if path else f"/{key}"
            if key not in before or key not in after:
                differences.append(
                    {
                        "path": child_path,
                        "before": before.get(key, _MISSING),
                        "after": after.get(key, _MISSING),
                    }
                )
            else:
                differences.extend(_canonical_diff(before[key], after[key], child_path))
        return differences
    if (
        isinstance(before, Sequence)
        and isinstance(after, Sequence)
        and not isinstance(before, (str, bytes, bytearray))
        and not isinstance(after, (str, bytes, bytearray))
    ):
        differences = []
        common = min(len(before), len(after))
        for index in range(common):
            differences.extend(_canonical_diff(before[index], after[index], f"{path}/{index}"))
        for index in range(common, len(before)):
            differences.append(
                {"path": f"{path}/{index}", "before": before[index], "after": _MISSING}
            )
        for index in range(common, len(after)):
            differences.append(
                {"path": f"{path}/{index}", "before": _MISSING, "after": after[index]}
            )
        return differences
    if before != after:
        return [{"path": path or "/", "before": before, "after": after}]
    return []


def _load_document(path: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    path = Path(path)
    if not path.is_file():
        return None, f"document does not exist: {path}"
    try:
        document = load_authoring_document(path)
    except Exception as exc:  # pragma: no cover - Pydantic text varies by version.
        return None, f"canonical document validation failed: {exc}"
    return document.model_dump(mode="json"), None


def _matches(actual: object, assertion: Mapping[str, Any]) -> bool:
    operator = assertion.get("operator", "equals")
    expected = assertion.get("value")
    if operator == "exists":
        return actual is not _MISSING
    if operator == "equals":
        return actual == expected
    if operator == "contains":
        return isinstance(actual, str) and str(expected) in actual
    if operator == "length_at_least":
        return isinstance(actual, (str, list, tuple, dict)) and len(actual) >= int(expected)
    raise ValueError(f"unsupported LAS assertion operator: {operator!r}")


def _assertions(
    document: Mapping[str, Any],
    assertions: object,
    *,
    field_name: str,
) -> list[str]:
    if assertions is None:
        return []
    if not isinstance(assertions, list) or not all(
        isinstance(item, Mapping) for item in assertions
    ):
        raise ValueError(f"{field_name} must be a list of assertion objects")
    errors = []
    for assertion in assertions:
        path = assertion.get("path")
        if not isinstance(path, str):
            raise ValueError(f"{field_name} assertions require a JSON pointer path")
        actual = _get_pointer(document, path)
        if not _matches(actual, assertion):
            errors.append(f"{path}: assertion {assertion.get('operator', 'equals')} failed")
    return errors


def _check_required_changes(
    after: Mapping[str, Any],
    required_changes: object,
) -> list[str]:
    if required_changes is None:
        return []
    if not isinstance(required_changes, list) or not all(
        isinstance(item, Mapping) for item in required_changes
    ):
        raise ValueError("required_changes must be a list of assertion objects")
    return _assertions(after, required_changes, field_name="required_changes")


def _requirement(
    requirement_id: str,
    errors: list[str] | None = None,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    if errors:
        return {"id": requirement_id, "status": FAIL, "errors": errors}
    if reason is not None:
        return {"id": requirement_id, "status": NOT_CHECKABLE, "errors": [], "reason": reason}
    return {"id": requirement_id, "status": PASS, "errors": []}


def verify_las_revision(
    before_path: str | Path,
    after_path: str | Path,
    acceptance: Mapping[str, Any],
    *,
    execution_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Grade one LAS revision against canonical before/after semantic state.

    The acceptance specification is data owned by the harness, never by the
    provider.  ``execution_evidence`` is required for persistence/rendering
    claims and for distinguishing a rejected request from an unobserved one.
    """
    result: dict[str, Any] = {
        "ok": False,
        "status": HARNESS_ERROR,
        "workflow_status": HARNESS_ERROR,
        "harness_error": False,
        "before_path": str(before_path),
        "after_path": str(after_path),
        "before_sha256": None,
        "after_sha256": None,
        "requirements": [],
        "canonical_diff": [],
        "errors": [],
    }
    try:
        if not isinstance(acceptance, Mapping):
            raise ValueError("acceptance must be an object")
        before, before_error = _load_document(before_path)
        after, after_error = _load_document(after_path)
        result["before_sha256"] = (
            hashlib.sha256(Path(before_path).read_bytes()).hexdigest()
            if Path(before_path).is_file()
            else None
        )
        result["after_sha256"] = (
            hashlib.sha256(Path(after_path).read_bytes()).hexdigest()
            if Path(after_path).is_file()
            else None
        )
        if before_error or after_error:
            result["errors"] = [error for error in (before_error, after_error) if error]
            result["requirements"] = [_requirement("LAS-09", result["errors"])]
            result["status"] = FAIL
            result["workflow_status"] = FAIL
            return result
        assert before is not None and after is not None
        ignored_paths = acceptance.get("ignored_change_paths", [])
        if not isinstance(ignored_paths, list) or not all(
            isinstance(item, str) for item in ignored_paths
        ):
            raise ValueError("ignored_change_paths must be a list of JSON pointers")
        differences = [
            change
            for change in _canonical_diff(before, after)
            if not any(
                _path_is_within(str(change["path"]), ignored_path) for ignored_path in ignored_paths
            )
        ]
        result["canonical_diff"] = differences

        requirements: list[dict[str, Any]] = []
        grounding_errors = _assertions(
            before, acceptance.get("before_assertions"), field_name="before_assertions"
        )
        requirements.append(
            _requirement(
                "LAS-01",
                grounding_errors,
                reason=None
                if acceptance.get("before_assertions") is not None
                else "no before-state assertions supplied",
            )
        )

        by_requirement = acceptance.get("required_changes", {})
        if not isinstance(by_requirement, Mapping):
            raise ValueError("required_changes must be an object keyed by LAS requirement")
        for requirement_id in ("LAS-02", "LAS-03", "LAS-04", "LAS-05", "LAS-06"):
            assertions = by_requirement.get(requirement_id)
            if assertions is None:
                requirements.append(
                    _requirement(
                        requirement_id, reason="dimension is not exercised by this revision"
                    )
                )
            else:
                requirements.append(
                    _requirement(requirement_id, _check_required_changes(after, assertions))
                )

        allowed = acceptance.get("allowed_change_paths")
        prohibited = acceptance.get("prohibited_change_paths", [])
        if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
            raise ValueError("allowed_change_paths must be a list of JSON pointers")
        if not isinstance(prohibited, list) or not all(
            isinstance(item, str) for item in prohibited
        ):
            raise ValueError("prohibited_change_paths must be a list of JSON pointers")
        preservation_errors = [
            f"{change['path']}: mutation is outside allowed change paths"
            for change in differences
            if not any(_path_is_within(str(change["path"]), path) for path in allowed)
        ]
        preservation_errors.extend(
            f"{change['path']}: prohibited unrelated mutation"
            for change in differences
            if any(_path_is_within(str(change["path"]), path) for path in prohibited)
        )
        requirements.append(_requirement("LAS-07", preservation_errors))

        expected_outcome = acceptance.get("expected_outcome")
        if expected_outcome == "rejected":
            if execution_evidence is None:
                requirements.append(
                    _requirement("LAS-08", reason="rejection evidence was not supplied")
                )
            else:
                errors = []
                if execution_evidence.get("accepted") is not False:
                    errors.append("execution evidence does not show rejection")
                if differences:
                    errors.append("rejected revision mutated the canonical document")
                requirements.append(_requirement("LAS-08", errors))
        elif expected_outcome == "accepted":
            requirements.append(
                _requirement("LAS-08", reason="no ambiguity/missing-source rejection is expected")
            )
        else:
            requirements.append(_requirement("LAS-08", reason="expected_outcome is not declared"))

        if execution_evidence is None:
            requirements.append(
                _requirement("LAS-09", reason="persistence/render evidence was not supplied")
            )
        else:
            evidence_errors = [
                key for key in ("persisted", "rendered") if execution_evidence.get(key) is not True
            ]
            requirements.append(
                _requirement(
                    "LAS-09",
                    [f"missing successful execution evidence: {key}" for key in evidence_errors],
                )
            )
        result["requirements"] = requirements
        statuses = {item["status"] for item in requirements}
        if FAIL in statuses:
            result["status"] = FAIL
        elif NOT_CHECKABLE in statuses:
            result["status"] = NOT_CHECKABLE
        else:
            result["status"] = PASS
        applicable_statuses = {
            item["status"] for item in requirements if item["status"] != NOT_CHECKABLE
        }
        result["workflow_status"] = FAIL if FAIL in applicable_statuses else PASS
        result["ok"] = result["status"] == PASS
        result["errors"] = [error for item in requirements for error in item.get("errors", [])]
        return result
    except Exception as exc:  # pragma: no cover - defensive verifier boundary.
        result["harness_error"] = True
        result["status"] = HARNESS_ERROR
        result["workflow_status"] = HARNESS_ERROR
        result["errors"] = [f"verifier error: {type(exc).__name__}: {exc}"]
        return result


def main() -> int:
    """Run one JSON acceptance specification from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before_path", type=Path)
    parser.add_argument("after_path", type=Path)
    parser.add_argument("acceptance_path", type=Path)
    args = parser.parse_args()
    acceptance = json.loads(args.acceptance_path.read_text(encoding="utf-8"))
    result = verify_las_revision(args.before_path, args.after_path, acceptance)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())

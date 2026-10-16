"""Strict schema-closed freeze + SHA-256 digest. No repair. Oracle lock."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from nlp_gate_modernbert.nl_program_eval.closed_schema import ClosedNormalizedProgram
from nlp_gate_modernbert.scope_runtime.contracts import ScopeNormalizedProgram
from nlp_gate_modernbert.scope_runtime.execute import parse_program_from_witness

CANONICALIZATION_VERSION = "nl-program-canonical-json-v1"
DIGEST_ALGORITHM = "sha256"


class FrozenCandidate:
    """Immutable frozen candidate; oracle access becomes legal only after construction."""

    __slots__ = (
        "_program",
        "_canonical_json",
        "_sha256",
        "_canonicalization_version",
        "_oracle_access_enabled",
    )

    def __init__(
        self,
        program: ScopeNormalizedProgram,
        canonical_json: str,
        sha256: str,
        *,
        canonicalization_version: str = CANONICALIZATION_VERSION,
    ) -> None:
        self._program = program
        self._canonical_json = canonical_json
        self._sha256 = sha256
        self._canonicalization_version = canonicalization_version
        self._oracle_access_enabled = True

    @property
    def program(self) -> ScopeNormalizedProgram:
        return self._program

    @property
    def canonical_json(self) -> str:
        return self._canonical_json

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def canonicalization_version(self) -> str:
        return self._canonicalization_version

    @property
    def oracle_access_enabled(self) -> bool:
        return self._oracle_access_enabled

    def to_runtime_program(self) -> ScopeNormalizedProgram:
        """Defensive re-parse into runtime model (no mutation of frozen payload)."""
        return parse_program_from_witness(json.loads(self._canonical_json))


class FreezeFailure:
    __slots__ = ("schema_valid", "failure", "detail")

    def __init__(self, failure: str, detail: str | None = None) -> None:
        self.schema_valid = False
        self.failure = failure
        self.detail = detail


def _canonical_json(closed: ClosedNormalizedProgram) -> str:
    payload = closed.model_dump(mode="json", exclude_none=True)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def freeze_candidate(raw: dict[str, Any] | str | bytes) -> FrozenCandidate | FreezeFailure:
    """Validate recursively closed schema, canonicalize, digest. No repair."""
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            return FreezeFailure("DECOMPOSITION_SCHEMA_INVALID", f"json_decode:{exc}")
    if not isinstance(raw, dict):
        return FreezeFailure("DECOMPOSITION_SCHEMA_INVALID", "candidate_not_object")

    try:
        closed = ClosedNormalizedProgram.model_validate(raw)
    except ValidationError as exc:
        return FreezeFailure("DECOMPOSITION_SCHEMA_INVALID", str(exc))

    try:
        canonical = _canonical_json(closed)
    except (ValueError, TypeError) as exc:
        # NaN/Infinity → allow_nan=False raises ValueError
        return FreezeFailure("DECOMPOSITION_SCHEMA_INVALID", f"canonicalization:{exc}")

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    runtime = parse_program_from_witness(json.loads(canonical))
    return FrozenCandidate(
        program=runtime,
        canonical_json=canonical,
        sha256=digest,
        canonicalization_version=CANONICALIZATION_VERSION,
    )


def require_frozen(candidate: Any) -> FrozenCandidate:
    if not isinstance(candidate, FrozenCandidate):
        raise RuntimeError("oracle_access_denied_before_FrozenCandidate")
    if not candidate.oracle_access_enabled:
        raise RuntimeError("oracle_access_disabled")
    return candidate

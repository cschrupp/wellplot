"""Strict schema-closed freeze + SHA-256 digest. No repair. Oracle lock."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from nlp_gate_modernbert.nl_program_eval.closed_schema import ClosedNormalizedProgram
from nlp_gate_modernbert.scope_runtime.contracts import ScopeNormalizedProgram
from nlp_gate_modernbert.scope_runtime.execute import parse_program_from_witness

CANONICALIZATION_VERSION = "nl-program-canonical-json-v1"
DIGEST_ALGORITHM = "sha256"


@dataclass(frozen=True, slots=True)
class FrozenCandidate:
    """Digest-coupled immutable candidate. Canonical JSON is the source of truth.

    Callers must use ``to_runtime_program()`` (defensive re-parse). The stored
    digest is over ``canonical_json`` bytes only.
    """

    _canonical_json: str
    _sha256: str
    _canonicalization_version: str = CANONICALIZATION_VERSION
    _oracle_access_enabled: bool = True

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

    @property
    def program(self) -> ScopeNormalizedProgram:
        """Defensive re-parse; mutations to the returned model cannot affect the digest."""
        return self.to_runtime_program()

    def to_runtime_program(self) -> ScopeNormalizedProgram:
        """Re-parse canonical JSON into a fresh runtime model every call."""
        return parse_program_from_witness(json.loads(self._canonical_json))

    def verify_digest(self) -> bool:
        return (
            hashlib.sha256(self._canonical_json.encode("utf-8")).hexdigest()
            == self._sha256
        )


@dataclass(frozen=True, slots=True)
class FreezeFailure:
    failure: str
    detail: str | None = None
    schema_valid: bool = False


def canonical_json_bytes(closed: ClosedNormalizedProgram) -> str:
    """Deterministic canonical form: sorted keys, compact separators, no nulls, no NaN."""
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
        canonical = canonical_json_bytes(closed)
    except (ValueError, TypeError) as exc:
        return FreezeFailure("DECOMPOSITION_SCHEMA_INVALID", f"canonicalization:{exc}")

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    frozen = FrozenCandidate(
        _canonical_json=canonical,
        _sha256=digest,
        _canonicalization_version=CANONICALIZATION_VERSION,
        _oracle_access_enabled=True,
    )
    assert frozen.verify_digest()
    return frozen


def require_frozen(candidate: Any) -> FrozenCandidate:
    """Gate for any API that may reach oracle-side material."""
    if not isinstance(candidate, FrozenCandidate):
        raise RuntimeError("oracle_access_denied_before_FrozenCandidate")
    if not candidate.oracle_access_enabled:
        raise RuntimeError("oracle_access_disabled")
    if not candidate.verify_digest():
        raise RuntimeError("frozen_candidate_digest_mismatch")
    return candidate

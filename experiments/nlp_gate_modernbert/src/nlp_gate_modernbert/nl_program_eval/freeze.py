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


@dataclass(frozen=True, slots=True, init=False)
class FrozenCandidate:
    """Digest-coupled immutable candidate. Constructible only via ``freeze_candidate``.

    Canonical JSON is the source of truth. ``program`` / ``to_runtime_program()``
    always re-parse; mutations to returned models cannot affect the digest.
    """

    _canonical_json: str
    _sha256: str
    _canonicalization_version: str
    _oracle_access_enabled: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "FrozenCandidate_requires_freeze_candidate: "
            "construct only via freeze_candidate()"
        )

    @classmethod
    def _create_sealed(
        cls,
        canonical_json: str,
        sha256: str,
        *,
        canonicalization_version: str = CANONICALIZATION_VERSION,
        oracle_access_enabled: bool = True,
    ) -> FrozenCandidate:
        """Internal factory: closed-schema validate + canonicalize + digest check."""
        try:
            closed = ClosedNormalizedProgram.model_validate(json.loads(canonical_json))
            recanon = canonical_json_bytes(closed)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"frozen_candidate_schema_invalid:{exc}") from exc
        if recanon != canonical_json:
            raise RuntimeError("frozen_candidate_not_canonical")
        digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        if digest != sha256:
            raise RuntimeError("frozen_candidate_digest_mismatch")
        obj = object.__new__(cls)
        object.__setattr__(obj, "_canonical_json", canonical_json)
        object.__setattr__(obj, "_sha256", sha256)
        object.__setattr__(obj, "_canonicalization_version", canonicalization_version)
        object.__setattr__(obj, "_oracle_access_enabled", oracle_access_enabled)
        return obj

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

    def revalidate_freeze_contract(self) -> None:
        """Re-run closed-schema + canonicalization + digest (require_frozen gate)."""
        closed = ClosedNormalizedProgram.model_validate(json.loads(self._canonical_json))
        if canonical_json_bytes(closed) != self._canonical_json:
            raise RuntimeError("frozen_candidate_not_canonical")
        if not self.verify_digest():
            raise RuntimeError("frozen_candidate_digest_mismatch")


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
    return FrozenCandidate._create_sealed(
        canonical,
        digest,
        canonicalization_version=CANONICALIZATION_VERSION,
        oracle_access_enabled=True,
    )


def require_frozen(candidate: Any) -> FrozenCandidate:
    """Gate for any API that may reach oracle-side material."""
    if not isinstance(candidate, FrozenCandidate):
        raise RuntimeError("oracle_access_denied_before_FrozenCandidate")
    if not candidate.oracle_access_enabled:
        raise RuntimeError("oracle_access_disabled")
    candidate.revalidate_freeze_contract()
    return candidate

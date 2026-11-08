###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Immutable, provenance-bearing semantic channel catalog contracts.

This module defines and validates catalog data only. Matching remains owned by
the existing :mod:`wellplot.authoring_context` resolver.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _CatalogModel(BaseModel):
    """Strict immutable base for semantic catalog records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CatalogReleasePin(_CatalogModel):
    """Deployment-pinned identities for one reviewed catalog release."""

    pin_schema_version: Literal["1"] = "1"
    approved_release_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    release_ref: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    catalog_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_record_ref: str = Field(min_length=1)
    approved_repository_commit: str = Field(pattern=r"^[a-f0-9]{40}$")


class CatalogApprovalManifest(_CatalogModel):
    """Approval metadata bound to both packaged and semantic catalog digests."""

    manifest_schema_version: Literal["1"] = "1"
    approved_release_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    release_ref: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    catalog_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_record_ref: str = Field(min_length=1)
    review_scope: str = Field(min_length=1)
    status: Literal["approved", "revoked"]


class SemanticCatalogTrustError(ValueError):
    """Fail-closed catalog release error with a stable safe code."""

    def __init__(self, code: str) -> None:
        """Store only a stable classification, never artifact contents."""
        self.code = code
        super().__init__(code)


class CatalogProvenance(_CatalogModel):
    """Source artifact and rights provenance for catalog assertions."""

    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_ref: str = Field(min_length=1)
    license_status: str = Field(min_length=1)
    redistribution_status: str = Field(min_length=1)


class CatalogReview(_CatalogModel):
    """Independent review metadata required for an active rule."""

    reviewer: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewed_at: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    decision: Literal["approved", "rejected"]


class SemanticChannelFamily(_CatalogModel):
    """Stable identity and classification for one scientific channel family."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    concept_kind: Literal[
        "physical_quantity",
        "categorical",
        "status",
        "quality",
        "metadata",
        "derived",
        "array",
        "waveform",
        "unknown",
    ]
    measurement_type: str | None = None
    compatible_unit_ids: tuple[str, ...] = ()
    supported_visualization_types: tuple[str, ...] = ()
    absence_scope: Literal["OPEN_WORLD", "REVIEWED_CLOSED_SCOPE"] = "OPEN_WORLD"


class RequestTermRule(_CatalogModel):
    """Exact scientist-language recognition rule, separate from mnemonics."""

    id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    terms: tuple[str, ...] = Field(min_length=1)
    normalization_profile_id: Literal["casefold_whitespace_v1"]
    status: Literal["candidate", "reviewed", "deprecated"]
    provenance_ids: tuple[str, ...] = ()
    review: CatalogReview | None = None


class PhysicalChannelRule(_CatalogModel):
    """Reviewed exact/glob channel recognition rule for one family."""

    id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    matcher_kind: Literal["exact_mnemonic", "restricted_glob"]
    matcher_value: str = Field(min_length=1)
    source_scope: tuple[str, ...] = ()
    source_content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    kind_constraints: tuple[str, ...] = ()
    unit_constraints: tuple[str, ...] = ()
    status: Literal["candidate", "reviewed", "deprecated"]
    provenance_ids: tuple[str, ...] = ()
    review: CatalogReview | None = None

    @model_validator(mode="after")
    def validate_restricted_glob(self) -> PhysicalChannelRule:
        """Restrict glob syntax to the explicitly supported `*` and `?`."""
        if self.matcher_kind == "restricted_glob" and any(
            character in self.matcher_value for character in "[]"
        ):
            raise ValueError("Restricted glob matchers do not support character classes.")
        if self.source_content_sha256 is not None and not self.source_scope:
            raise ValueError("Content-bound source rules require an explicit source scope.")
        return self


class SemanticChannelCatalog(_CatalogModel):
    """Versioned catalog whose digest covers every recognition assertion."""

    schema_version: Literal["1"] = "1"
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    release_ref: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_provenance: tuple[CatalogProvenance, ...]
    families: tuple[SemanticChannelFamily, ...]
    request_term_rules: tuple[RequestTermRule, ...]
    physical_channel_rules: tuple[PhysicalChannelRule, ...]

    @model_validator(mode="after")
    def validate_catalog_integrity(self) -> SemanticChannelCatalog:
        """Check digest, references, identifiers, and reviewed-rule evidence."""
        expected_digest = semantic_catalog_digest(self.model_dump(mode="json"))
        if self.content_sha256 != expected_digest:
            raise ValueError("Semantic catalog content digest does not match its payload.")

        family_ids = [family.id for family in self.families]
        provenance_ids = [source.id for source in self.source_provenance]
        rule_ids = [rule.id for rule in (*self.request_term_rules, *self.physical_channel_rules)]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("Semantic catalog family identifiers must be unique.")
        if len(provenance_ids) != len(set(provenance_ids)):
            raise ValueError("Semantic catalog provenance identifiers must be unique.")
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("Semantic catalog rule identifiers must be unique.")

        known_families = set(family_ids)
        known_provenance = set(provenance_ids)
        for rule in (*self.request_term_rules, *self.physical_channel_rules):
            if rule.family_id not in known_families:
                raise ValueError(f"Catalog rule {rule.id!r} references an unknown family.")
            if not set(rule.provenance_ids) <= known_provenance:
                raise ValueError(f"Catalog rule {rule.id!r} references unknown provenance.")
            if rule.status == "reviewed":
                if rule.review is None or rule.review.decision != "approved":
                    raise ValueError(f"Reviewed catalog rule {rule.id!r} lacks approved review.")
                if not rule.provenance_ids:
                    raise ValueError(f"Reviewed catalog rule {rule.id!r} lacks provenance.")
                referenced = [
                    source for source in self.source_provenance if source.id in rule.provenance_ids
                ]
                if any(
                    source.license_status.casefold() not in {"approved", "not_applicable"}
                    or source.redistribution_status.casefold() not in {"approved", "not_applicable"}
                    for source in referenced
                ):
                    raise ValueError(
                        f"Reviewed catalog rule {rule.id!r} has unapproved provenance."
                    )
        return self

    def verify_digest(self) -> bool:
        """Recompute the payload digest before consuming this release."""
        return self.content_sha256 == semantic_catalog_digest(self.model_dump(mode="json"))


class TrustedCatalogRelease(_CatalogModel):
    """Validated package release retained for one host transaction."""

    pin: CatalogReleasePin
    manifest: CatalogApprovalManifest
    catalog: SemanticChannelCatalog


class SemanticResolutionEvidence(_CatalogModel):
    """Catalog/source identities bound to one deterministic channel decision."""

    requested_term: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    binding_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    catalog_release_ref: str = Field(min_length=1)
    catalog_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    catalog_artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    requirement_id: str | None = Field(default=None, min_length=1)
    request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    scope_key: str | None = Field(default=None, min_length=1)
    track_scope: str | None = Field(default=None, min_length=1)
    binding_slot: str | None = Field(default=None, min_length=1)
    physical_mnemonic: str | None = Field(default=None, min_length=1)
    source_candidate_id: str | None = Field(default=None, min_length=1)
    source_handle: str | None = Field(default=None, min_length=1)
    inspection_snapshot_id: str | None = Field(default=None, min_length=1)
    source_revision: str = Field(min_length=1)
    physical_identity_json: str = Field(min_length=2)

    @field_validator("physical_identity_json")
    @classmethod
    def validate_physical_identity_json(cls, value: str) -> str:
        """Require canonical nonempty object JSON for immutable identity custody."""
        try:
            identity = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("Physical identity evidence must be valid JSON.") from error
        if not isinstance(identity, dict) or not identity:
            raise ValueError("Physical identity evidence must be a nonempty JSON object.")
        if canonical_physical_identity(identity) != value:
            raise ValueError("Physical identity evidence must use canonical JSON encoding.")
        return value


class ExpectedSemanticBinding(_CatalogModel):
    """Host-compiled semantic request slot expected at publication."""

    request_kind: Literal["SEMANTIC_FAMILY"]
    requirement_id: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope_key: str = Field(min_length=1)
    track_scope: str = Field(min_length=1)
    binding_slot: str = Field(min_length=1)
    requested_term: str = Field(min_length=1)
    source_candidate_id: str = Field(min_length=1)
    source_handle: str = Field(min_length=1)
    inspection_snapshot_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    task_index: int = Field(ge=0)
    section_id: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    binding_id: str = Field(min_length=1)


class SemanticRequestClassification(_CatalogModel):
    """Host classification for one compiled channel-request obligation."""

    requirement_id: str = Field(min_length=1)
    request_kind: Literal["SEMANTIC_FAMILY", "EXPLICIT_PHYSICAL", "UNRESOLVED"]
    expected_binding: ExpectedSemanticBinding | None = None

    @model_validator(mode="after")
    def validate_classification_payload(self) -> SemanticRequestClassification:
        """Only semantic-family classifications carry publication expectations."""
        if (self.request_kind == "SEMANTIC_FAMILY") != (self.expected_binding is not None):
            raise ValueError("Semantic request classification payload is inconsistent.")
        if (
            self.expected_binding is not None
            and self.expected_binding.requirement_id != self.requirement_id
        ):
            raise ValueError("Semantic request classification requirement id differs.")
        return self


class SemanticSourceChannel(_CatalogModel):
    """One physical channel projection in a host-owned inspected source map."""

    mnemonic: str = Field(min_length=1)
    kind: str = Field(default="scalar", min_length=1)
    unit: str | None = Field(default=None, min_length=1)
    physical_identity_json: str = Field(min_length=2)
    addressability: Literal["ADDRESSABLE", "UNADDRESSABLE", "UNKNOWN"]

    @field_validator("physical_identity_json")
    @classmethod
    def validate_identity_json(cls, value: str) -> str:
        """Require canonical object identity JSON."""
        try:
            identity = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("Physical identity evidence must be valid JSON.") from error
        if not isinstance(identity, dict) or not identity:
            raise ValueError("Physical identity evidence must be a nonempty JSON object.")
        if canonical_physical_identity(identity) != value:
            raise ValueError("Physical identity evidence must use canonical JSON encoding.")
        return value


class SemanticSourceBinding(_CatalogModel):
    """One section scope's request-scoped source snapshot and channels."""

    scope_key: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    source_handle: str = Field(min_length=1)
    inspection_snapshot_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    source_path: str | None = Field(default=None, min_length=1)
    source_content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    channels: tuple[SemanticSourceChannel, ...]

    @model_validator(mode="after")
    def validate_content_identity(self) -> SemanticSourceBinding:
        """Require a path whenever a host source binding carries a content hash."""
        if self.source_content_sha256 is not None and self.source_path is None:
            raise ValueError("A source content digest requires its host source path.")
        return self


class SemanticPublicationContract(_CatalogModel):
    """Host-owned expected set and source map for shared publication checks."""

    expected_bindings: tuple[ExpectedSemanticBinding, ...] = ()
    source_bindings: tuple[SemanticSourceBinding, ...] = ()
    trusted_release: TrustedCatalogRelease | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_unique_host_keys(self) -> SemanticPublicationContract:
        """Reject duplicate expected slots and ambiguous source scope mappings."""
        expected_keys = [
            (item.request_sha256, item.requirement_id, item.scope_key, item.binding_slot)
            for item in self.expected_bindings
        ]
        if len(expected_keys) != len(set(expected_keys)):
            raise ValueError("Expected semantic binding slots must be unique.")
        source_keys = [(item.scope_key, item.source_handle) for item in self.source_bindings]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("Semantic source scope/handle pairs must be unique.")
        return self


def verify_semantic_resolution_evidence(
    evidence: SemanticResolutionEvidence,
    catalog: SemanticChannelCatalog,
    *,
    expected_section_id: str,
    expected_track_id: str,
    expected_binding_id: str,
    expected_physical_identity: Mapping[str, object],
    current_source_revision: str,
) -> bool:
    """Revalidate catalog, source, binding scope, and exact physical identity."""
    try:
        expected_identity_json = canonical_physical_identity(expected_physical_identity)
    except (TypeError, ValueError):
        return False
    return all(
        (
            catalog.verify_digest(),
            evidence.catalog_id == catalog.catalog_id,
            evidence.catalog_version == catalog.catalog_version,
            evidence.catalog_release_ref == catalog.release_ref,
            evidence.catalog_content_sha256 == catalog.content_sha256,
            evidence.source_revision == current_source_revision,
            evidence.section_id == expected_section_id,
            evidence.track_id == expected_track_id,
            evidence.binding_id == expected_binding_id,
            evidence.physical_identity_json == expected_identity_json,
        )
    )


def verify_semantic_publication(
    document: object,
    *,
    observed: Sequence[SemanticResolutionEvidence],
    contract: SemanticPublicationContract,
    release: TrustedCatalogRelease,
) -> None:
    """Require exact expected/evidence/source/document agreement before publish."""
    if not release.catalog.verify_digest():
        raise ValueError("semantic_catalog_untrusted")
    if (
        release.pin.content_sha256 != release.catalog.content_sha256
        or release.pin.catalog_id != release.catalog.catalog_id
        or release.pin.catalog_version != release.catalog.catalog_version
        or release.pin.release_ref != release.catalog.release_ref
    ):
        raise ValueError("semantic_catalog_untrusted")

    expected = contract.expected_bindings
    expected_keys = [_semantic_evidence_key(item) for item in expected]
    observed_keys = [_semantic_evidence_key(item) for item in observed]
    if len(expected_keys) != len(set(expected_keys)):
        raise ValueError("semantic_expected_binding_duplicate")
    if len(observed_keys) != len(set(observed_keys)):
        raise ValueError("semantic_evidence_duplicate")
    if set(expected_keys) != set(observed_keys):
        raise ValueError("semantic_evidence_set_mismatch")

    source_map: dict[tuple[str, str], SemanticSourceBinding] = {}
    for source in contract.source_bindings:
        key = (source.scope_key, source.source_handle)
        if key in source_map:
            raise ValueError("semantic_source_binding_ambiguous")
        source_map[key] = source

    expected_by_key = {_semantic_evidence_key(item): item for item in expected}
    for evidence in observed:
        key = _semantic_evidence_key(evidence)
        expectation = expected_by_key[key]
        if not _semantic_evidence_matches_expected(evidence, expectation, release.pin):
            raise ValueError("semantic_evidence_mismatch")

        source = source_map.get((expectation.scope_key, expectation.source_handle))
        if source is None or not _semantic_source_matches_expected(source, expectation):
            raise ValueError("semantic_source_binding_mismatch")
        channels = [
            channel
            for channel in source.channels
            if channel.physical_identity_json == evidence.physical_identity_json
            and channel.mnemonic == evidence.physical_mnemonic
        ]
        if len(channels) != 1 or channels[0].addressability != "ADDRESSABLE":
            raise ValueError("semantic_channel_not_addressable")
        _verify_source_applicability(
            release.catalog,
            family_id=evidence.family_id,
            requested_term=evidence.requested_term,
            channel=channels[0],
            source=source,
        )

        if not _document_has_semantic_binding(
            document,
            section_id=expectation.section_id,
            track_id=expectation.track_id,
            binding_id=expectation.binding_id,
            channel=evidence.physical_mnemonic or "",
        ):
            raise ValueError("semantic_binding_document_mismatch")


def _verify_source_applicability(
    catalog: SemanticChannelCatalog,
    *,
    family_id: str,
    requested_term: str,
    channel: SemanticSourceChannel,
    source: SemanticSourceBinding,
) -> None:
    """Recheck the trusted rule's path, content, kind, and unit constraints."""
    request_family_ids = {
        rule.family_id
        for rule in catalog.request_term_rules
        if rule.status == "reviewed"
        and any(
            normalize_request_term(term) == normalize_request_term(requested_term)
            for term in rule.terms
        )
    }
    if request_family_ids != {family_id}:
        raise ValueError("semantic_request_family_mismatch")
    applicable_rules = [
        rule
        for rule in catalog.physical_channel_rules
        if rule.status == "reviewed"
        and rule.family_id == family_id
        and rule.matcher_kind == "exact_mnemonic"
        and rule.matcher_value.casefold() == channel.mnemonic.casefold()
        and (
            not rule.kind_constraints
            or channel.kind.casefold() in {item.casefold() for item in rule.kind_constraints}
        )
        and (
            not rule.unit_constraints
            or (
                channel.unit is not None
                and channel.unit.casefold() in {item.casefold() for item in rule.unit_constraints}
            )
        )
        and (
            not rule.source_scope
            or (
                source.source_path is not None
                and any(_same_source_path(source.source_path, item) for item in rule.source_scope)
            )
        )
    ]
    if len(applicable_rules) != 1:
        raise ValueError("semantic_source_applicability_mismatch")
    rule = applicable_rules[0]
    if rule.source_content_sha256 is None:
        return
    if source.source_content_sha256 != rule.source_content_sha256:
        raise ValueError("semantic_source_content_mismatch")
    if source.source_path is None:
        raise ValueError("semantic_source_path_missing")
    try:
        current_digest = sha256_file(source.source_path)
    except OSError:
        raise ValueError("semantic_source_content_unavailable") from None
    if current_digest != rule.source_content_sha256:
        raise ValueError("semantic_source_content_mismatch")


def _same_source_path(left: str, right: str) -> bool:
    """Compare host paths after resolving relative catalog scopes at runtime."""
    from pathlib import Path

    return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(
        strict=False
    )


def sha256_file(path: str) -> str:
    """Hash one source file incrementally without retaining its contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _semantic_evidence_key(
    item: ExpectedSemanticBinding | SemanticResolutionEvidence,
) -> tuple[str, str, str, str]:
    """Return the independently compiled semantic request slot identity."""
    requirement_id = item.requirement_id
    request_sha256 = item.request_sha256
    scope_key = item.scope_key
    binding_slot = item.binding_slot
    if not all((requirement_id, request_sha256, scope_key, binding_slot)):
        raise ValueError("semantic_evidence_request_identity_missing")
    return (str(request_sha256), str(requirement_id), str(scope_key), str(binding_slot))


def _semantic_evidence_matches_expected(
    evidence: SemanticResolutionEvidence,
    expected: ExpectedSemanticBinding,
    pin: CatalogReleasePin,
) -> bool:
    """Compare every request, binding, release, and source identity field."""
    return all(
        (
            evidence.requested_term == expected.requested_term,
            evidence.section_id == expected.section_id,
            evidence.track_id == expected.track_id,
            evidence.binding_id == expected.binding_id,
            evidence.catalog_id == pin.catalog_id,
            evidence.catalog_version == pin.catalog_version,
            evidence.catalog_release_ref == pin.release_ref,
            evidence.catalog_content_sha256 == pin.content_sha256,
            evidence.catalog_artifact_sha256 == pin.catalog_artifact_sha256,
            evidence.source_candidate_id == expected.source_candidate_id,
            evidence.source_handle == expected.source_handle,
            evidence.inspection_snapshot_id == expected.inspection_snapshot_id,
            evidence.source_revision == expected.source_revision,
            evidence.track_scope == expected.track_scope,
        )
    )


def _semantic_source_matches_expected(
    source: SemanticSourceBinding,
    expected: ExpectedSemanticBinding,
) -> bool:
    """Verify source-handle continuity from the host inspection snapshot."""
    return all(
        (
            source.candidate_id == expected.source_candidate_id,
            source.source_handle == expected.source_handle,
            source.inspection_snapshot_id == expected.inspection_snapshot_id,
            source.source_revision == expected.source_revision,
        )
    )


def _document_has_semantic_binding(
    document: object,
    *,
    section_id: str,
    track_id: str,
    binding_id: str,
    channel: str,
) -> bool:
    """Find exactly one final canonical binding at its host-compiled scope."""
    value = document.model_dump(mode="json") if isinstance(document, BaseModel) else document
    if not isinstance(value, Mapping):
        return False
    sections = value.get("sections")
    if not isinstance(sections, list):
        return False
    matches: list[Mapping[str, object]] = []
    for section in sections:
        if not isinstance(section, Mapping) or section.get("id") != section_id:
            continue
        tracks = section.get("tracks")
        if not isinstance(tracks, list):
            continue
        for track in tracks:
            if not isinstance(track, Mapping) or track.get("id") != track_id:
                continue
            bindings = track.get("bindings")
            if not isinstance(bindings, list):
                continue
            matches.extend(
                binding
                for binding in bindings
                if isinstance(binding, Mapping) and binding.get("binding_id") == binding_id
            )
    return len(matches) == 1 and matches[0].get("channel") == channel


def canonical_physical_identity(identity: Mapping[str, object]) -> str:
    """Return immutable canonical JSON for a host-selected physical identity."""
    if not identity:
        raise ValueError("Physical identity must be nonempty.")
    canonical = json.dumps(
        dict(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if not isinstance(json.loads(canonical), dict):
        raise ValueError("Physical identity must be a JSON object.")
    return canonical


def semantic_catalog_digest(payload: Mapping[str, object]) -> str:
    """Hash the canonical catalog payload, excluding its digest field."""
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def catalog_from_payload(payload: Mapping[str, object]) -> SemanticChannelCatalog:
    """Validate a raw payload and require its supplied digest to match."""
    return SemanticChannelCatalog.model_validate(dict(payload))


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON members instead of accepting last-value-wins."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_member")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    """Reject non-standard JSON constants such as NaN and Infinity."""
    raise ValueError("invalid_constant")


def _strict_json_object(raw: bytes, *, code: str) -> dict[str, object]:
    """Decode one strict JSON object without retaining unsafe parser details."""
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise SemanticCatalogTrustError(code) from None
    if not isinstance(decoded, dict):
        raise SemanticCatalogTrustError(code)
    return decoded


def _verify_catalog_release_bytes(
    *,
    pin_bytes: bytes,
    manifest_bytes: bytes,
    catalog_bytes: bytes,
) -> TrustedCatalogRelease:
    """Verify release payloads in the accepted digest and schema order.

    This bytes-level verifier does not establish deployment trust for the pin.
    Production callers must obtain pin bytes through the fixed package-resource
    loader below; direct use is intended for isolated provider-free tests.
    """
    pin_payload = _strict_json_object(pin_bytes, code="semantic_catalog_pin_invalid")
    try:
        pin = CatalogReleasePin.model_validate(pin_payload)
    except ValueError:
        raise SemanticCatalogTrustError("semantic_catalog_pin_invalid") from None

    if hashlib.sha256(manifest_bytes).hexdigest() != pin.approval_manifest_sha256:
        raise SemanticCatalogTrustError("semantic_catalog_untrusted")
    manifest_payload = _strict_json_object(
        manifest_bytes,
        code="semantic_catalog_manifest_invalid",
    )
    try:
        manifest = CatalogApprovalManifest.model_validate(manifest_payload)
    except ValueError:
        raise SemanticCatalogTrustError("semantic_catalog_manifest_invalid") from None

    manifest_identity_matches = all(
        (
            manifest.approved_release_id == pin.approved_release_id,
            manifest.catalog_id == pin.catalog_id,
            manifest.catalog_version == pin.catalog_version,
            manifest.release_ref == pin.release_ref,
            manifest.content_sha256 == pin.content_sha256,
            manifest.catalog_artifact_sha256 == pin.catalog_artifact_sha256,
            manifest.approval_record_ref == pin.approval_record_ref,
        )
    )
    if not manifest_identity_matches:
        raise SemanticCatalogTrustError("semantic_catalog_untrusted")
    if manifest.status != "approved":
        raise SemanticCatalogTrustError("semantic_catalog_unapproved")

    if hashlib.sha256(catalog_bytes).hexdigest() != pin.catalog_artifact_sha256:
        raise SemanticCatalogTrustError("semantic_catalog_untrusted")
    catalog_payload = _strict_json_object(
        catalog_bytes,
        code="semantic_catalog_invalid",
    )
    try:
        catalog = catalog_from_payload(catalog_payload)
    except ValueError:
        raise SemanticCatalogTrustError("semantic_catalog_invalid") from None

    catalog_identity_matches = all(
        (
            catalog.content_sha256 == pin.content_sha256,
            catalog.catalog_id == pin.catalog_id,
            catalog.catalog_version == pin.catalog_version,
            catalog.release_ref == pin.release_ref,
        )
    )
    if not catalog_identity_matches:
        raise SemanticCatalogTrustError("semantic_catalog_untrusted")
    return TrustedCatalogRelease(pin=pin, manifest=manifest, catalog=catalog)


def load_deployed_catalog_release() -> TrustedCatalogRelease:
    """Load the one fixed, deployment-packaged semantic catalog release.

    The release pin is trusted only because it is shipped at a fixed resource
    path inside the trusted WellPlot application package. No environment,
    branch, caller-supplied path, or catalog field can select another release.
    CAT-02I ships no approved pin, so the production default is fail-closed.
    """
    release_root = files("wellplot.mcp.assets").joinpath("semantic_catalog")
    try:
        pin_bytes = release_root.joinpath("release-pin.json").read_bytes()
        manifest_bytes = release_root.joinpath("approval-manifest.json").read_bytes()
        catalog_bytes = release_root.joinpath("catalog.json").read_bytes()
    except (FileNotFoundError, OSError):
        raise SemanticCatalogTrustError("semantic_catalog_pin_missing") from None
    return _verify_catalog_release_bytes(
        pin_bytes=pin_bytes,
        manifest_bytes=manifest_bytes,
        catalog_bytes=catalog_bytes,
    )


def revalidate_deployed_catalog_release(
    expected: TrustedCatalogRelease,
) -> TrustedCatalogRelease:
    """Re-read the fixed package resources and require the same transaction pin."""
    current = load_deployed_catalog_release()
    if current.pin != expected.pin:
        raise SemanticCatalogTrustError("semantic_catalog_stale")
    return current


def build_semantic_catalog(payload: Mapping[str, object]) -> SemanticChannelCatalog:
    """Build a catalog from a payload by filling its deterministic digest."""
    content = {
        "schema_version": payload.get("schema_version", "1"),
        "catalog_id": payload["catalog_id"],
        "catalog_version": payload["catalog_version"],
        "release_ref": payload["release_ref"],
        "source_provenance": [
            CatalogProvenance.model_validate(item).model_dump(mode="json")
            for item in payload["source_provenance"]
        ],
        "families": [
            SemanticChannelFamily.model_validate(item).model_dump(mode="json")
            for item in payload["families"]
        ],
        "request_term_rules": [
            RequestTermRule.model_validate(item).model_dump(mode="json")
            for item in payload["request_term_rules"]
        ],
        "physical_channel_rules": [
            PhysicalChannelRule.model_validate(item).model_dump(mode="json")
            for item in payload["physical_channel_rules"]
        ],
    }
    content["content_sha256"] = semantic_catalog_digest(content)
    return SemanticChannelCatalog.model_validate(content)


EMPTY_SEMANTIC_CHANNEL_CATALOG = build_semantic_catalog(
    {
        "schema_version": "1",
        "catalog_id": "wellplot.semantic-curve-catalog",
        "catalog_version": "0.0.0-empty",
        "release_ref": "wellplot.semantic-curve-catalog/0.0.0-empty",
        "source_provenance": [],
        "families": [],
        "request_term_rules": [],
        "physical_channel_rules": [],
    }
)


def normalize_request_term(value: str) -> str:
    """Apply versioned exact matching: Unicode casefold and whitespace collapse."""
    return re.sub(r"\s+", " ", value.strip().casefold())


__all__ = [
    "CatalogApprovalManifest",
    "CatalogReleasePin",
    "CatalogProvenance",
    "CatalogReview",
    "ExpectedSemanticBinding",
    "EMPTY_SEMANTIC_CHANNEL_CATALOG",
    "PhysicalChannelRule",
    "RequestTermRule",
    "SemanticCatalogTrustError",
    "SemanticChannelCatalog",
    "SemanticPublicationContract",
    "SemanticRequestClassification",
    "SemanticChannelFamily",
    "SemanticResolutionEvidence",
    "SemanticSourceBinding",
    "SemanticSourceChannel",
    "TrustedCatalogRelease",
    "build_semantic_catalog",
    "canonical_physical_identity",
    "catalog_from_payload",
    "load_deployed_catalog_release",
    "normalize_request_term",
    "revalidate_deployed_catalog_release",
    "semantic_catalog_digest",
    "verify_semantic_publication",
    "verify_semantic_resolution_evidence",
]

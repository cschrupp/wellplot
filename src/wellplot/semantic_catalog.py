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
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _CatalogModel(BaseModel):
    """Strict immutable base for semantic catalog records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


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


class SemanticResolutionEvidence(_CatalogModel):
    """Catalog/source identities bound to one deterministic channel decision."""

    requested_term: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    catalog_release_ref: str = Field(min_length=1)
    catalog_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_revision: str = Field(min_length=1)
    physical_identity: dict[str, object]


def verify_semantic_resolution_evidence(
    evidence: SemanticResolutionEvidence,
    catalog: SemanticChannelCatalog,
    *,
    current_source_revision: str,
) -> bool:
    """Revalidate immutable catalog and source identities before publication."""
    return (
        catalog.verify_digest()
        and evidence.catalog_id == catalog.catalog_id
        and evidence.catalog_version == catalog.catalog_version
        and evidence.catalog_release_ref == catalog.release_ref
        and evidence.catalog_content_sha256 == catalog.content_sha256
        and evidence.source_revision == current_source_revision
    )


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
    "CatalogProvenance",
    "CatalogReview",
    "EMPTY_SEMANTIC_CHANNEL_CATALOG",
    "PhysicalChannelRule",
    "RequestTermRule",
    "SemanticChannelCatalog",
    "SemanticChannelFamily",
    "SemanticResolutionEvidence",
    "build_semantic_catalog",
    "catalog_from_payload",
    "normalize_request_term",
    "semantic_catalog_digest",
    "verify_semantic_resolution_evidence",
]

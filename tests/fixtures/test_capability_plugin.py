"""External-looking capability fixture used by the CM-25 extensibility gate."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from wellplot.capabilities import CapabilitySpec
from wellplot.model.intent import AuthoringDocumentIntent, AuthoringRemarkIntent


class ExternalNoteArtifact(BaseModel):
    """Minimal v1 artifact contract owned by the fixture package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    note: str = Field(min_length=1)


class ExternalNoteArguments(BaseModel):
    """Minimal v2 argument contract owned by the fixture package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    note: str = Field(min_length=1)


def _compile_note(note: str) -> AuthoringDocumentIntent:
    """Build the canonical result without using a built-in capability helper."""
    return AuthoringDocumentIntent(
        remarks=[
            AuthoringRemarkIntent(
                remark_id="external-note",
                title="External Note",
                text=note,
            )
        ]
    )


def compile_external_note(artifact: BaseModel) -> AuthoringDocumentIntent:
    """Compile the fixture's v1 artifact through its own deterministic handler."""
    typed = ExternalNoteArtifact.model_validate(artifact)
    return _compile_note(typed.note)


def handle_external_note(arguments: BaseModel) -> AuthoringDocumentIntent:
    """Handle the fixture's v2 arguments through the public capability contract."""
    typed = ExternalNoteArguments.model_validate(arguments)
    return _compile_note(typed.note)


def external_capability() -> CapabilitySpec:
    """Return a dual-mode capability that is not part of built-in registration."""
    return CapabilitySpec(
        capability_id="extension.synthetic",
        category="annotation",
        description="External test-only note capability.",
        artifact_model=ExternalNoteArtifact,
        compiler=compile_external_note,
        aliases=("synthetic note",),
        arguments_model=ExternalNoteArguments,
        handler=handle_external_note,
        worker_hints=("Accept one concise note.",),
        examples=("extension.synthetic(note='Check cement bond')",),
    )


__all__ = [
    "ExternalNoteArguments",
    "ExternalNoteArtifact",
    "compile_external_note",
    "external_capability",
    "handle_external_note",
]

"""Provider-neutral result envelopes shared by canonical authoring adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuthoringRunState:
    """Structured per-run state captured during one authoring workflow."""

    objectives: tuple[str, ...] = ()
    completed_objectives: tuple[str, ...] = ()
    blocked_objectives: tuple[str, ...] = ()
    discovered_sections: tuple[str, ...] = ()
    discovered_tracks_by_section: dict[str, tuple[str, ...]] = field(default_factory=dict)
    discovered_binding_ids_by_track: dict[str, tuple[str, ...]] = field(default_factory=dict)
    available_channels_by_section: dict[str, tuple[str, ...]] = field(default_factory=dict)
    last_verification: dict[str, object] = field(default_factory=dict)


def _clarification_summary_text(entry: dict[str, object]) -> str:
    """Return the concise user-facing text for one clarification entry."""
    question = entry.get("clarification_question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    input_key = str(entry.get("input_key", "the requested value")).strip()
    labels = entry.get("candidate_labels")
    if isinstance(labels, list):
        visible_labels = [str(label).strip() for label in labels if str(label).strip()]
        if visible_labels:
            return f"Choose a header field for `{input_key}`: " + " or ".join(visible_labels) + "."
    return f"Choose the header field for `{input_key}`."


@dataclass(frozen=True)
class AuthoringUserReport:
    """Concise deterministic operator report for one authoring run."""

    done: tuple[str, ...] = ()
    could_not_do: tuple[str, ...] = ()
    why_not: tuple[str, ...] = ()
    warnings_or_errors: tuple[str, ...] = ()
    request_inconsistencies: tuple[str, ...] = ()
    needs_clarification: tuple[dict[str, object], ...] = ()
    next_help: tuple[str, ...] = ()

    def sections(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Return the non-empty report sections in display order."""
        return tuple(
            (label, items)
            for label, items in (
                ("Done", self.done),
                ("Could not do", self.could_not_do),
                ("Why not", self.why_not),
                ("Warnings/errors", self.warnings_or_errors),
                ("Request inconsistencies", self.request_inconsistencies),
                (
                    "Needs clarification",
                    tuple(_clarification_summary_text(item) for item in self.needs_clarification),
                ),
                ("Next help", self.next_help),
            )
            if items
        )

    def to_text(self) -> str:
        """Render the operator report as concise plain text."""
        lines: list[str] = []
        for label, items in self.sections():
            lines.append(f"{label}:")
            lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)


@dataclass(frozen=True)
class AuthoringResult:
    """Final result envelope returned by a public authoring adapter."""

    provider: str
    model: str
    credential_source: str | None
    request_kind: str
    example_id: str | None
    source_logfile_path: str | None
    goal: str
    draft_logfile: str
    server_root: Path
    tool_trace: tuple[Any, ...]
    final_text: str
    validation: dict[str, object]
    draft_summary: dict[str, object]
    inspect_summary: dict[str, object]
    change_summary: dict[str, object]
    draft_text: str
    report_preview_png: bytes = field(repr=False)
    section_preview_png: bytes = field(repr=False)
    plan: Any | None = None
    phase_summaries: tuple[Any, ...] = ()
    run_state: AuthoringRunState = field(default_factory=AuthoringRunState)
    user_report: AuthoringUserReport = field(default_factory=AuthoringUserReport)
    needs_clarification: tuple[dict[str, object], ...] = ()
    request_coverage: tuple[dict[str, object], ...] = ()
    operation_outcomes: tuple[dict[str, object], ...] = ()
    defaults_provenance: dict[str, str] = field(default_factory=dict)
    submitted_intent: dict[str, object] | None = None
    report_facts: dict[str, object] = field(default_factory=dict)

    @property
    def draft_path(self) -> Path:
        """Return the absolute path to the generated draft logfile."""
        return self.server_root / self.draft_logfile

    @property
    def summary_lines(self) -> tuple[str, ...]:
        """Return normalized change-summary lines for notebook/UI display."""
        lines = self.change_summary.get("summary_lines", [])
        if not isinstance(lines, list):
            return ()
        return tuple(line for line in lines if isinstance(line, str) and line.strip())

    def preview_bytes(self, kind: str = "section") -> bytes:
        """Return one preview payload by logical kind."""
        normalized_kind = str(kind).strip().lower()
        if normalized_kind == "section":
            return self.section_preview_png
        if normalized_kind == "report":
            return self.report_preview_png
        raise ValueError("preview kind must be either 'section' or 'report'.")

    @property
    def user_report_text(self) -> str:
        """Return the concise operator report as plain text."""
        return self.user_report.to_text()

    def write_preview_artifacts(
        self,
        *,
        output_dir: str | Path | None = None,
    ) -> dict[str, Path]:
        """Persist the in-memory preview PNGs and return their paths."""
        target_dir = self.draft_path.parent if output_dir is None else Path(output_dir)
        if output_dir is not None and not target_dir.is_absolute():
            target_dir = self.server_root / target_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = self.draft_path.stem.removesuffix(".log")
        report_preview = target_dir / f"{stem}_report_preview.png"
        section_preview = target_dir / f"{stem}_section_preview.png"
        report_preview.write_bytes(self.report_preview_png)
        section_preview.write_bytes(self.section_preview_png)
        return {"report_preview": report_preview, "section_preview": section_preview}


__all__ = ["AuthoringResult", "AuthoringRunState", "AuthoringUserReport"]

#!/usr/bin/env python3
"""Repeat the LAS tutorial seed request until its persisted state is correct."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from wellplot.agent import create_project_session
from wellplot.authoring import load_authoring_document

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "workspace" / "data" / "30-23a-3 8117_d.las"
DEFAULT_PROJECT = REPO_ROOT / "workspace" / "evaluations" / "seed_feedback_loop"
SEED_GOAL = """
Start from the existing starter logfile and create the initial open-hole draft.

- Keep the section id `main`.
- Set the section subtitle to `Interactive LAS tutorial draft`.
- Keep the seeded `gr_sp` overview track before the depth track.
- Do not add any additional tracks yet.
- Keep the existing open-hole header archetype structure.
- Fill any available header values from the LAS metadata.
- If some open-hole header labels do not have values yet, keep the blank placeholders.
- Set the first service title to `Open Hole Quicklook`.
- Do not add remarks yet.
""".strip()


def _read_secret(path: Path | None) -> str | None:
    """Read one ignored credential file without printing its contents."""
    if path is None or not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _grade_seed(path: Path, baseline: Path) -> list[str]:
    """Return unmet persisted invariants for the seed request."""
    document = load_authoring_document(path, allowed_root=path.parents[2])
    baseline_document = load_authoring_document(baseline, allowed_root=baseline.parents[2])
    errors: list[str] = []
    sections = {section.id: section for section in document.sections}
    section = sections.get("main")
    if section is None:
        errors.append("section `main` is missing")
    else:
        if section.subtitle != "Interactive LAS tutorial draft":
            errors.append(f"main subtitle is {section.subtitle!r}")
        track_ids = [track.id for track in section.tracks]
        if track_ids != ["gr_sp", "depth"]:
            errors.append(f"main track order is {track_ids!r}")

    if document.header is None or not document.header.service_titles:
        errors.append("the first service title is missing")
    else:
        service_title = document.header.service_titles[0].value
        title_value = getattr(service_title, "value", service_title)
        if title_value != "Open Hole Quicklook":
            errors.append(f"the first service title is {title_value!r}")

    if document.remarks != baseline_document.remarks:
        errors.append("remarks changed even though the request prohibited remarks")
    return errors


async def _run(args: argparse.Namespace) -> int:
    """Run bounded fresh attempts and print redacted feedback evidence."""
    provider = args.provider or os.getenv("WELLPLOT_AGENT_PROVIDER", "openai_compat")
    model = args.model or os.getenv("OPENAI_COMPAT_MODEL") or os.getenv("OPENAI_MODEL")
    base_url = args.base_url or os.getenv("OPENAI_COMPAT_BASE_URL")
    api_key = _read_secret(Path(args.api_key_file) if args.api_key_file else None)
    project_dir = Path(args.project_dir).resolve()
    source_path = Path(args.source).resolve()
    session, paths = create_project_session(
        server_root=REPO_ROOT,
        project_dir=project_dir,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=args.timeout,
        run_max_rounds=args.max_rounds,
        revise_max_rounds=args.max_rounds,
    )

    for attempt in range(1, args.attempts + 1):
        starter = session.bootstrap_starter(
            kind="open_hole_quicklook",
            source_data_file=source_path,
            staged_data_name="user_input.las",
            title="Main Review",
            subtitle="Placeholder starter source",
            depth_range=(8400, 9300),
            starter_logfile="agent_starter.log.yaml",
            draft_logfile="agent_open_hole_draft.log.yaml",
            render_output_path="agent_open_hole_draft.pdf",
            starter_name="Agent LAS Starter",
        )
        try:
            result = await session.run(
                goal=SEED_GOAL,
                source_logfile_path=starter.logfile_path,
            )
            draft_path = Path(result.draft_logfile)
            if not draft_path.is_absolute():
                draft_path = paths.server_root / draft_path
            errors = _grade_seed(draft_path, Path(starter.logfile_path))
            evidence: dict[str, Any] = {
                "attempt": attempt,
                "passed": not errors,
                "errors": errors,
                "draft": str(draft_path),
                "feedback_loop": result.report_facts.get("feedback_loop", {}),
                "warnings": result.report_facts.get("warnings", []),
                "tool_trace": [call.name for call in result.tool_trace],
                "stable_tool_outcomes": result.report_facts.get("stable_tool_outcomes", []),
            }
        except Exception as exc:  # noqa: BLE001 - report one failed live attempt
            evidence = {
                "attempt": attempt,
                "passed": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
        print(json.dumps(evidence, indent=2, sort_keys=True))
        if evidence["passed"]:
            return 0
    return 1


def main() -> int:
    """Parse arguments and run the seed feedback loop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-file", default=None)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--project-dir", default=str(DEFAULT_PROJECT))
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--max-rounds", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=1800.0)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

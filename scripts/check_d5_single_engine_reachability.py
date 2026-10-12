"""Provider-free reachability audit for the canonical D5 authoring engine."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ENTRYPOINTS = (
    "wellplot.agent",
    "wellplot.agent.composition",
    "wellplot.agent.direct_notebook",
    "wellplot.agent.notebook",
    "wellplot.mcp.agentic_server",
)
FORBIDDEN_MODULES = (
    "wellplot.agent.core",
    "wellplot.agent.stable_fallback",
    "wellplot.agent.code_mode.program_worker",
    "wellplot.agent.code_mode.report_worker",
    "wellplot.agent.code_mode.typed_delivery",
    "wellplot.agent.code_mode.semantic_ir_v2_compiler",
    "wellplot.agent.code_mode.semantic_ir_v2r_compiler",
    "wellplot.agent.graph",
)
FORBIDDEN_SOURCE_REFERENCES = {
    "src/wellplot/agent/routing.py": (
        "from .core import",
        'engine == "v1"',
        'Literal["v1"',
    ),
    "src/wellplot/agent/core.py": ("stable_fallback", "catalog_fallback"),
    "src/wellplot/agent/code_mode/visual_correction.py": (
        "ProgramSectionCompiler",
        "ReportProgramCompiler",
        "TypedDeliverySectionCompiler",
    ),
}


def _runtime_probe(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    """Import every canonical entry point in a clean child interpreter."""
    code = """
import json
import sys
import wellplot.agent
import wellplot.agent.composition
import wellplot.agent.direct_notebook
import wellplot.agent.notebook
import wellplot.mcp.agentic_server
print(json.dumps({name: name in sys.modules for name in FORBIDDEN}))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    result = subprocess.run(
        [sys.executable, "-c", code.replace("FORBIDDEN", repr(FORBIDDEN_MODULES))],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Canonical import probe failed.")
    return json.loads(result.stdout)


def run_audit(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    """Return and validate the canonical runtime reachability evidence."""
    runtime = _runtime_probe(repo_root)
    loaded = [name for name, present in runtime.items() if present]
    if loaded:
        raise RuntimeError(f"Forbidden canonical runtime modules loaded: {loaded}")

    source_violations: list[str] = []
    for relative, needles in FORBIDDEN_SOURCE_REFERENCES.items():
        text = (repo_root / relative).read_text(encoding="utf-8")
        source_violations.extend(
            f"{relative}: forbidden reference {needle!r}" for needle in needles if needle in text
        )
    if source_violations:
        raise RuntimeError("\n".join(source_violations))

    return {
        "entrypoints": list(CANONICAL_ENTRYPOINTS),
        "forbidden_modules_loaded": [],
        "source_violations": [],
        "status": "PASS",
    }


def main() -> int:
    """Run the audit and emit sanitized JSON evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    result = run_audit(args.repo_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

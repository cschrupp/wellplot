"""Fail-closed production attestation for the canonical D5 runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "architecture" / "D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json"
MANIFEST_VERSION = "wellplot.d5.single-engine-production.v1"
FROZEN_D4_PRODUCTION_COMPONENTS = (
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/code_mode/typed_delivery.py",
    "src/wellplot/agent/code_mode/state.py",
    "src/wellplot/agent/code_mode/workflow.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/enrichment.py",
    "src/wellplot/agent/code_mode/report_worker.py",
    "src/wellplot/agent/code_mode/program_worker.py",
    "src/wellplot/agent/code_mode/repair.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai.py",
    "src/wellplot/agent/providers/openai_v2.py",
    "src/wellplot/agent/providers/openai_program_v2.py",
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "src/wellplot/agent/providers/_v2_client.py",
    "src/wellplot/agent/direct_notebook.py",
    "src/wellplot/authoring.py",
    "src/wellplot/authoring_reconciler.py",
    "src/wellplot/authoring_executor.py",
    "src/wellplot/authoring_service.py",
    "src/wellplot/agent/operation_executor.py",
    "scripts/verify_cbl_packet.py",
    "scripts/verify_las_revision.py",
)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one repository file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_components(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """Compute the fixed canonical component set from the current checkout."""
    return {
        relative: sha256_file(repo_root / relative) for relative in FROZEN_D4_PRODUCTION_COMPONENTS
    }


def build_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Build the deterministic successor manifest."""
    return {
        "manifest_version": MANIFEST_VERSION,
        "authority": "WELLPLOT-D5-2R1-REACHABILITY-CLOSEOUT",
        "historical_d4_attestation": "scripts/nlp_d4_live_acceptance.py",
        "production_components": current_components(repo_root),
    }


def verify_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Verify the manifest set and every component hash fail-closed."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = build_manifest(repo_root)
    if manifest != expected:
        raise RuntimeError("D5 production component attestation drifted.")
    return expected


def main() -> int:
    """Generate or verify the successor manifest."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if args.write:
        MANIFEST_PATH.write_text(
            json.dumps(build_manifest(repo_root), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    result = verify_manifest(repo_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

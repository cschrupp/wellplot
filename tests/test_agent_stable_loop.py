"""Retirement checks for the historical stable-loop authoring engine."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from wellplot.agent.routing import normalize_authoring_engine

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_retired_stable_loop_is_not_loaded_by_canonical_entrypoints() -> None:
    """Canonical imports must not activate the retired stable-loop module."""
    result = subprocess.run(
        [sys.executable, "scripts/check_d5_single_engine_reachability.py", "--repo-root", "."],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["status"] == "PASS"
    assert "wellplot.agent.stable_fallback" not in evidence["forbidden_modules_loaded"]


def test_retired_v1_selector_fails_closed() -> None:
    """The removed alternate engine cannot be selected by compatibility callers."""
    with pytest.raises(ValueError, match="exactly 'v2'"):
        normalize_authoring_engine("v1")

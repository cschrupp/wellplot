"""DECOMPOSER-PILOT-PREFLIGHT-01: pins, constraint compile, parity (no generate)."""

from __future__ import annotations

__all__ = ["run_preflight"]


def run_preflight(*args, **kwargs):
    from nlp_gate_modernbert.decomposer_pilot.preflight import run_preflight as _run

    return _run(*args, **kwargs)

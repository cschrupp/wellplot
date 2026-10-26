"""Load the frozen ten-turn D5 population without changing D4 fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts import nlp_d4_live_acceptance as d4

POPULATION_PATH = Path("tests/fixtures/d5_final_10_turn_population.json")
C02_REQUEST_PATH = Path("tests/fixtures/d5_c02_held_out_request.json")
C02_CONTRACT_PATH = Path("tests/fixtures/d5_c02_held_out_contract.json")
FINAL_TURN_IDS = (
    "D4-C01:C01",
    "D4-L01:T1",
    "D4-L01:T2",
    "D4-L01:T3",
    "D4-L01:T4",
    "D4-L02:T1",
    "D4-L02:T2",
    "D4-L03:C01",
    "D4-L04:C01",
    "D5-C02:C01",
)
EXPECTED_C02_REQUEST_SHA256 = "f9e746ab41dc420f30f0f19a11859926a9b6e7276a1e56552d56e4752fe93579"
EXPECTED_C02_CONTRACT_SHA256 = "26e2917178a119784328ea00ff2aefd8c5317b8177232de2fa2b733ca1d3e7e3"
EXPECTED_POPULATION_SHA256 = "7481ad88b489f676426002f0b68abc4927cef5ed15376dd9279fbb0853aa5d54"
EXPECTED_FINAL_EXECUTION_CHECKPOINT = "d610bcc098ebae5e55a7c8e4e1677b2423c039f4"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_final_population(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the nine accepted D4 turns plus the frozen C02 turn."""
    if _sha256(repo_root / POPULATION_PATH) != EXPECTED_POPULATION_SHA256:
        raise ValueError("final population fixture identity drifted")
    population = _load(repo_root / POPULATION_PATH)
    if population.get("execution_checkpoint") != EXPECTED_FINAL_EXECUTION_CHECKPOINT:
        raise ValueError("final population execution checkpoint drifted")
    if tuple(population.get("turn_ids", ())) != FINAL_TURN_IDS:
        raise ValueError("D5 final population order drifted")
    if population.get("d4_cases_fixture_sha256") != d4.FROZEN_CASES_SHA256:
        raise ValueError("D4 cases fixture identity drifted")
    if population.get("d4_gold_fixture_sha256") != d4.FROZEN_GOLD_SHA256:
        raise ValueError("D4 gold fixture identity drifted")
    if _sha256(repo_root / C02_REQUEST_PATH) != EXPECTED_C02_REQUEST_SHA256:
        raise ValueError("C02 request fixture identity drifted")
    if _sha256(repo_root / C02_CONTRACT_PATH) != EXPECTED_C02_CONTRACT_SHA256:
        raise ValueError("C02 contract fixture identity drifted")
    cases = d4.load_cases(repo_root)
    gold = d4.load_gold(repo_root)
    request = _load(repo_root / C02_REQUEST_PATH)
    contract = _load(repo_root / C02_CONTRACT_PATH)
    c02_case = {
        "case_id": request["case_id"],
        "turn_id": request["turn_id"],
        "workflow": "CBL-CONSTRUCT",
        "execution_index": 10,
        "expected_outcome": request.get("expected_outcome", "DIRECT_CORRECT"),
        "request": request["request"],
        "request_sha256": d4.sha256_text(request["request"]),
    }
    c02_gold = {
        "turn_id": contract["turn_id"],
        "expected_outcome": contract["expected_outcome"],
        "grader": contract["grader"],
        "contract": contract,
    }
    return cases + [c02_case], {"cases": gold["cases"] + [c02_gold]}

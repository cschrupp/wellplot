"""Six-case EvaluationSpec registry (harness-side; not candidate payload)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    fixture_id: str
    utterance: str
    oracle_witness_id: str
    required_atom_ids: tuple[str, ...]
    ordering_atom_ids: tuple[str, ...] = ()
    observed_out_of_scope: tuple[str, ...] = ()
    expected_terminal: dict = field(default_factory=lambda: {"status": "ok", "authority": "OK", "reason": None})


CASE_REGISTRY: dict[str, CaseRecord] = {
    "D5GAP-0085": CaseRecord(
        case_id="D5GAP-0085",
        fixture_id="d5_duplicate_cbl",
        utterance="Make both CBL views use 0–100, then fill between them in blue.",
        oracle_witness_id="D5GAP-0085",
        required_atom_ids=(
            "BOTH_CBL_SCALE_0_100",
            "SCALE_BEFORE_FILL",
            "FILL_BETWEEN_CBL",
        ),
        ordering_atom_ids=("SCALE_BEFORE_FILL",),
        observed_out_of_scope=("fill_styling_blue",),
    ),
    "D5GAP-0089": CaseRecord(
        case_id="D5GAP-0089",
        fixture_id="d5_duplicate_cbl",
        utterance="First change the narrow CBL view to 0–100, then fill between the first and second CBL instances.",
        oracle_witness_id="D5GAP-0089",
        required_atom_ids=(
            "NARROW_CBL_SCALE_0_100",
            "SCALE_BEFORE_FILL",
            "FILL_BETWEEN_CBL_INSTANCES",
        ),
        ordering_atom_ids=("SCALE_BEFORE_FILL",),
    ),
    "D5GAP-0117": CaseRecord(
        case_id="D5GAP-0117",
        fixture_id="d5_petrophysics",
        utterance="Set RHOB to 1.95–2.95 reversed and split-fill it at 2.45.",
        oracle_witness_id="D5GAP-0117",
        required_atom_ids=(
            "RHOB_RANGE_1_95_2_95",
            "RHOB_REVERSED",
            "RHOB_SPLIT_FILL",
            "SPLIT_BASELINE_2_45",
        ),
        ordering_atom_ids=(),
    ),
    "D5GAP-0096": CaseRecord(
        case_id="D5GAP-0096",
        fixture_id="d5_petrophysics",
        utterance="Add a Petrophysics track with GR 0–150 and RT logarithmic 0.2–2000.",
        oracle_witness_id="D5GAP-0096",
        required_atom_ids=(
            "NEW_TRACK",
            "TRACK_TITLE_PETROPHYSICS",
            "GR_ON_NEW_TRACK",
            "GR_RANGE_0_150",
            "RT_ON_NEW_TRACK",
            "RT_LOG_0_2_2000",
        ),
        ordering_atom_ids=(),
    ),
    "D5GAP-0101": CaseRecord(
        case_id="D5GAP-0101",
        fixture_id="d5_main_las",
        utterance="Append a 24 mm Caliper QC track and plot CALI on it at 6–12.",
        oracle_witness_id="D5GAP-0101",
        required_atom_ids=(
            "NEW_TRACK",
            "TRACK_TITLE_CALIPER_QC",
            "TRACK_WIDTH_24_MM",
            "CALI_ON_NEW_TRACK",
            "CALI_RANGE_6_12",
        ),
        ordering_atom_ids=(),
    ),
    "SEED-cm-9643c020e2e02463": CaseRecord(
        case_id="SEED-cm-9643c020e2e02463",
        fixture_id="d0_base",
        utterance=(
            "Create one normal track named Petrophysics. First plot GR linearly from -10 to 140. "
            "Then plot RT logarithmically from 0.1 to 10000. Preserve that binding order."
        ),
        oracle_witness_id="SEED-cm-9643c020e2e02463",
        required_atom_ids=(
            "NEW_TRACK",
            "TRACK_NORMAL_DEFAULT",
            "TRACK_TITLE_PETROPHYSICS",
            "GR_ON_NEW_TRACK",
            "GR_LINEAR_M10_140",
            "RT_ON_NEW_TRACK",
            "RT_LOG_0_1_10000",
            "GR_BEFORE_RT",
        ),
        ordering_atom_ids=("GR_BEFORE_RT",),
    ),
}

CASE_IDS = tuple(CASE_REGISTRY.keys())

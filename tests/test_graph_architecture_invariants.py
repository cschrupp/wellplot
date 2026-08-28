"""Static architecture constraints for the generic compilation graph."""

###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

from pathlib import Path


def test_graph_topology_contains_no_domain_specific_capability_names() -> None:
    """The graph orchestrates generic stages and never selects scientific domains."""
    workflow = (
        (Path(__file__).parents[1] / "src" / "wellplot" / "agent" / "graph" / "workflow.py")
        .read_text(encoding="utf-8")
        .casefold()
    )

    forbidden = (
        "cbl",
        "vdl",
        "well_diagram",
        "image_track",
        "track.image",
        "section.log_plot",
        "track.normal",
        "binding.curve",
    )
    assert not [token for token in forbidden if token in workflow]

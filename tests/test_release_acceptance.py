"""Release-facing documentation and notebook acceptance checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

from wellplot import __version__

_PROMPT_LITERAL = re.compile(
    r"(?:goal|feedback|TARGET_PROMPT)\s*=\s*(?:f|r|fr|rf)?"
    r"(?P<quote>'''|\"\"\")(.*?)(?P=quote)",
    re.DOTALL,
)
_INTERNAL_PROMPT_FIELDS = ("track_id", "section_id", "binding_id", "width_mm")


def _notebook_source(path: Path) -> str:
    """Return markdown and code source without stored execution outputs."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in payload.get("cells", [])
        if cell.get("cell_type") in {"markdown", "code"}
    )


def _prompt_literals(path: Path) -> list[str]:
    """Extract natural-language goal and feedback blocks from one notebook."""
    source = _notebook_source(path)
    return [match.group(2) for match in _PROMPT_LITERAL.finditer(source)]


def test_release_metadata_and_notebook_prompts_are_user_facing() -> None:
    """Keep the 0.6.0 notebooks free from internal desired-state field demands."""
    repository_root = Path(__file__).parents[1]
    assert __version__ == "0.6.0"
    changelog = (repository_root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [0.6.0]" in changelog
    assert "generic defaults" in changelog.lower()

    notebook_paths = [
        repository_root / "examples/notebooks/user/agent_las_step_by_step.ipynb",
        repository_root / "examples/notebooks/user/agent_cbl_log_example_from_prompt.ipynb",
    ]
    for notebook_path in notebook_paths:
        prompts = _prompt_literals(notebook_path)
        assert prompts
        for prompt in prompts:
            for field_name in _INTERNAL_PROMPT_FIELDS:
                assert field_name not in prompt
            assert not re.search(r"\bkind\s*:", prompt)

    las_source = _notebook_source(notebook_paths[0])
    assert "Use a logarithmic scale from 0.2 to 2000 ohm.m." in las_source
    assert "include_phase_previews=True" in las_source
    assert "display_authoring_result" in las_source


def test_release_documentation_explains_optional_defaults_and_diagnostics() -> None:
    """Keep the published guidance aligned with open-world authoring behavior."""
    repository_root = Path(__file__).parents[1]
    example_guide = (
        repository_root / "docs/site/guides/example-7-agent-las-step-by-step.md"
    ).read_text(encoding="utf-8")
    workflow_guide = (repository_root / "docs/site/workflows/mcp-workflow.md").read_text(
        encoding="utf-8"
    )

    for document in (example_guide, workflow_guide):
        assert "generic form" in document.lower()
        assert "family" in document.lower()
        assert "provenance" in document.lower()
        assert "scale" in document.lower()
    assert "track form and its X-scale" in example_guide
    assert "X-scale describes" in workflow_guide
    assert "unmatched source channel" in workflow_guide.lower()
    assert "ambiguous" in workflow_guide.lower()

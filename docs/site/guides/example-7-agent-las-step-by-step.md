# Example 7: Agent-Assisted LAS Packet Walkthrough

This guide documents the detailed step-by-step notebook for building an
open-hole packet from a user LAS file through the public `wellplot.agent` API.

Notebook:

- `examples/notebooks/user/agent_las_step_by_step.ipynb`

Use this walkthrough when you want the model to help with authoring decisions,
but you still want the edits to stay explicit, reviewable, and preview-driven.

## What this notebook teaches

The notebook works on one evolving draft logfile instead of re-running a full
example from scratch each time.

The flow is:

1. stage the user LAS file into the project folder
2. generate a reusable starter scaffold from a shipped preset
3. let the LAS header populate the first-page metadata fields
4. add remarks
5. refine the overview track and then add one track at a time
6. preview after each step
7. render the final PDF through the public agent session helper

The notebook uses these public APIs directly:

- `create_project_session(...)`
- `session.bootstrap_starter(...)`
- `await session.run(...)`
- `await session.revise(...)`
- `await session.render_logfile_to_file(...)`
- `display_authoring_result(...)`
- `relative_path(...)`

## Runtime requirements

Install:

```bash
python -m pip install "wellplot[agent,las,notebook]"
```

Credential setup:

- prefer `OPENAI_API_KEY` in the shell before launching Jupyter
- `wellplot.agent` also loads ignored local credential files under the
  repository root: `.env.local`, `.env`, `OPENAI_API_KEY.txt`, or
  `openai_api_key.txt`

Runtime model:

- the notebook imports the installed `wellplot` package
- the hosted model works through the public `wellplot.agent` layer
- `wellplot.agent` launches the local stdio `wellplot-mcp` server underneath
- the notebook should be run from a checkout of this repository so the example
  files and sample data are available

## Why this is different from the other user notebooks

The earlier user notebooks are curated, executed, and deterministic. They show
exact rendered checkpoints for a fixed example package.

This notebook is different:

- it is manual and credentialed
- it depends on a live model
- it is intended for real user adaptation, not only for replaying a shipped
  repository example
- narrow header-only requests are routed automatically through deterministic
  heading tools, so prompts like `Fill header RMF as 0.01 @ 25` do not need to
  go through the broader freeform authoring loop
- `display_authoring_result(...)` now prints a concise deterministic operator
  report before the preview image, so each notebook step shows what changed,
  what did not, and what the agent can help with next
- it is a working first pass, so prompt wording, model choice, and revision
  round budgets may still need tuning for final packet polish

That is why it lives in the `user/` notebook set but remains unexecuted in git.

## Recommended usage

Start with the default copied LAS file once so the full workflow is known to
work in your environment.

Then point `session.bootstrap_starter(...)` at your own LAS file so the project
folder gets a staged `user_input.las`, refreshed starter files, and the same
default draft/render targets before rerunning from the top.

The starter scaffold step is intentionally higher level than the YAML-first
user notebooks. Instead of hand-writing the full template and starter logfile
schema in the notebook, this walkthrough uses
`session.bootstrap_starter(...)` to stage the data source, configure the
project defaults, materialize the same files from a shipped preset, and then
show the generated YAML so the user can still inspect what the agent will
revise.

That shipped preset now pulls its heading scaffold from packaged header
archetype assets. The agent is expected to preserve that open-hole or
cased-hole scaffold and fill matching values into it, not rebuild the first
page when the user pastes ticket text or asks for a few specific header
values.

The safest iteration pattern is:

1. create the first draft with `session.run(...)`
2. inspect the operator report and preview image
3. make the next change with `session.revise(...)`
4. inspect the report again, especially any skipped work or inconsistencies
5. render the final PDF only after the section preview looks right

## Related references

- [Examples](examples.md)
- [MCP Workflow](../workflows/mcp-workflow.md)
- [MCP API](../reference/mcp-api.md)

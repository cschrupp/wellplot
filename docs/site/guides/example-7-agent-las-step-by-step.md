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

1. write a tiny starter logfile with one reference depth track
2. point that draft at the user LAS file
3. let the LAS header populate the first-page metadata fields
4. add remarks
5. add one track at a time
6. preview after each step
7. render the final PDF through the public agent session helper

The notebook uses these public APIs directly:

- `AuthoringSession.from_local_mcp(...)`
- `await session.run(...)`
- `await session.revise(...)`
- `await session.render_logfile_to_file(...)`

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
- it is a working first pass, so prompt wording, model choice, and revision
  round budgets may still need tuning for final packet polish

That is why it lives in the `user/` notebook set but remains unexecuted in git.

## Recommended usage

Start with the default copied LAS file once so the full workflow is known to
work in your environment.

Then replace `workspace/tutorials/agent_las_step_by_step/user_input.las` with
your own LAS file and rerun the notebook from the top.

The safest iteration pattern is:

1. create the first draft with `session.run(...)`
2. inspect the preview image
3. make the next change with `session.revise(...)`
4. inspect the preview again
5. render the final PDF only after the section preview looks right

## Related references

- [Examples](examples.md)
- [MCP Workflow](../workflows/mcp-workflow.md)
- [MCP API](../reference/mcp-api.md)

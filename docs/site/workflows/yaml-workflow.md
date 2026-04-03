# YAML Workflow

Use YAML when the layout itself is a managed artifact.

## Best fit

The YAML workflow is a good fit for:

- repeatable operational layouts
- templated job savefiles
- hand-editable report definitions
- workflows where layout changes less often than the source data

## Current model

The YAML stack has two main pieces:

- templates: reusable layout defaults
- savefiles: job-specific overrides and bindings

The pipeline resolves configuration in this order:

1. renderer defaults
2. template values
3. savefile values

## Typical flow

1. define reusable defaults in a template
2. create a savefile for a specific job
3. load LAS or DLIS data referenced by the savefile
4. render the output artifact

## Example entry points

Reusable base template:

- `templates/wireline_base.template.yaml`

Representative savefiles:

- `examples/cbl_main.log.yaml`
- `examples/cbl_job_demo.log.yaml`
- `examples/cbl_report_pages.log.yaml`
- `examples/cbl_report_pages_open_hole.log.yaml`

## Render from a savefile

```bash
uv run python -m well_log_os.cli render examples/cbl_main.log.yaml
```

Validate before rendering:

```bash
uv run python -m well_log_os.cli validate examples/cbl_main.log.yaml
```

## When not to use YAML first

Prefer the Python API when:

- channels are produced in memory from computation
- you need repeated partial renders in a notebook
- the layout is being assembled dynamically inside a pipeline

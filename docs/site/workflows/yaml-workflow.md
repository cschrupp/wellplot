# YAML Workflow

Use YAML when the layout itself is a maintained artifact.

## Best fit

- repeatable job templates
- saved report definitions
- operator-editable configs
- production workflows that separate layout from computation

## Current model

- templates define reusable defaults
- savefiles override or fill in job-specific data
- the renderer consumes the same normalized layout model that the Python API uses

## Example files

- `examples/cbl_job_demo.log.yaml`
- `examples/cbl_report_pages.log.yaml`
- `templates/wireline_base.template.yaml`

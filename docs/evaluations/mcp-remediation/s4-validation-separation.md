# S4 Validation Separation

## Scope

Separate deterministic authoring validation into explicit structural, data, and
render tiers without changing the stable tool count or adding agent recovery
logic.

## Validation tiers

- `structural`: canonical object identities, references, required fields, and
  numeric constraints. This tier does not load LAS/DLIS data or construct a
  render document.
- `data`: structural validation plus configured source loading, channel
  availability, scalar/raster compatibility, and raster-track compatibility.
- `render`: data validation plus document construction for the configured
  renderer.

`validate_logfile` exposes the tier through `level`. Its result reports the
tier that actually ran. The default remains `render` for compatibility with
existing callers that use validation as a pre-render check.

## Persistence policy

Canonical persistence always performs the S3 canonical projection, writes the
normalized YAML, reloads it, and checks canonical validity again. The default
persistence tier is now `structural`.

Operations that change a configured data source or create a curve/raster
binding persist at the `data` tier. Layout, heading, remarks, style, page, and
other source-independent edits persist at the `structural` tier. Rendering and
preview remain render-tier operations.

This deliberately permits a structurally valid draft with an unavailable
source to retain unrelated edits. A later `data` or `render` validation reports
the unavailable source at the boundary where it matters.

## Acceptance evidence

- Structural mutations succeed with unavailable source data.
- Data validation rejects unavailable sources and invalid binding channels.
- Render validation continues to construct full documents and exposes render
  failures.
- The stable MCP validation result declares `validation_level` and the real
  stdio wire baseline is updated.

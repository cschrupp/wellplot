# Reference

This section is the stable lookup layer for `wellplot`.

Use it when you already know what workflow you want and need the exact public
surface, YAML shape, or report-page structure.

## Reference map

- [Python API](python-api.md)
  - public package imports
  - `wellplot.api` module surfaces
  - dataset, builder, render, and serialization entry points
- [MCP API](mcp-api.md)
  - experimental stdio server surface
  - tools, resources, and prompts
  - write semantics and server-root policy
- [YAML Logfile](logfile-yaml.md)
  - top-level logfile structure
  - section-first layout and binding model
  - track kinds and binding kinds
  - render, page, depth, and track-header keys
- [Report Pages](report-pages.md)
  - heading, remarks, and tail structure
  - report block fields
  - open-hole and cased-hole detail tables

## Design boundary

The reference pages document the supported public surface and the normalized YAML
shape used by the project today.

They do not attempt to document every internal helper in:

- `wellplot.templates`
- `wellplot.logfile`
- `wellplot.renderers`

For deeper implementation notes, use the repository documents:

- `README.md`
- `docs/rendering-workings.md`
- `docs/programmatic-api-plan.md`
- `docs/decision-log.md`
- `docs/roadmap.md`

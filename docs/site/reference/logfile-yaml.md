# YAML Logfile

This page describes the normalized logfile YAML shape used by `wellplot`.

The logfile format is the main file-backed authoring surface for printable
reports.

## Top-level shape

At the highest level, a logfile contains:

```yaml
version: 1
name: my-log
data:
  source_path: path/to/file.las
  source_format: auto
render:
  backend: matplotlib
  output_path: out.pdf
  dpi: 300
document:
  page: ...
  depth: ...
  layout: ...
  bindings: ...
```

Required top-level keys:

- `version`
- `name`
- `render`
- `document`

Optional top-level keys:

- `data`

## `data`

Use top-level `data` when one source file feeds the report by default.

Keys:

- `source_path`
- `source_format`
  - `auto`
  - `las`
  - `dlis`

Section-first data loading is also supported. A section can override the root
data source through its own `data` block.

## `render`

The `render` block controls backend selection and output behavior.

Main keys:

- `backend`
  - `matplotlib`
  - `plotly`
- `output_path`
- `dpi`
- `continuous_strip_page_height_mm`
- `matplotlib.style`

Use `matplotlib` for printable multisection reports.

Use `plotly` for interactive single-section rendering.

## `document`

The `document` block contains page, axis, layout, and binding configuration.

Main keys:

- `page`
- `depth`
- `header`
- `footer`
- `markers`
- `zones`
- `layout`
- `bindings`

## `document.page`

Page settings control physical layout and section strip behavior.

Important keys:

- `size`
- `width_mm`
- `height_mm`
- `orientation`
- `continuous`
- `bottom_track_header_enabled`
- `margin_left_mm`
- `margin_right_mm`
- `margin_top_mm`
- `margin_bottom_mm`
- `track_gap_mm`
- `header_height_mm`
- `track_header_height_mm`
- `footer_height_mm`

Common pattern:

```yaml
page:
  size: A4
  orientation: portrait
  track_header_height_mm: 18
  track_gap_mm: 0
```

## `document.depth`

The shared layout axis lives in `document.depth`.

Keys:

- `unit`
- `scale`
- `major_step`
- `minor_step`

Example:

```yaml
depth:
  unit: ft
  scale: 240
  major_step: 10
  minor_step: 2
```

Reference tracks can override the active layout axis through their
`reference.define_layout` settings.

## `document.layout`

The project is now track-first and section-first.

Main keys:

- `heading`
- `remarks`
- `tail`
- `log_sections`

Each log section defines:

- its own `id`
- optional section `data`
- the list of physical tracks to render

## `log_sections[*].tracks`

Each section track defines layout, not channel binding.

Core keys:

- `id`
- `title`
- `kind`
- `width_mm`

Optional keys:

- `position`
- `x_scale`
- `grid`
- `track_header`
- `reference`
- `annotations`

Supported track kinds:

- `reference`
  - depth/time axis track and reference overlays
- `normal`
  - scalar curve track
- `array`
  - raster or waveform track with scalar overlays
- `annotation`
  - interval/text/marker/arrow/glyph track

Compatibility aliases still parse, but the explicit kinds above are the
intended public vocabulary.

## Track header configuration

Track headers use explicit object slots.

Example:

```yaml
track_header:
  objects:
    - kind: title
      enabled: true
      reserve_space: true
      line_units: 3
    - kind: scale
      enabled: true
      reserve_space: true
      line_units: 2
    - kind: legend
      enabled: true
      reserve_space: true
      line_units: 1
```

Supported header object kinds:

- `title`
- `scale`
- `legend`

## `document.bindings`

Bindings attach channels to the physical tracks defined in layout.

Main keys:

- `on_missing`
- `channels`

Each binding normally includes:

- `section`
- `track_id`
- `channel`
- `kind`

Supported binding kinds:

- `curve`
- `raster`

## Curve bindings

Curve bindings support the main scalar rendering features.

High-value keys:

- `label`
- `style`
- `scale`
- `header_display`
- `callouts`
- `fill`
- `reference_overlay`
- `value_labels`
- `wrap`
- `render_mode`

Implemented fill modes:

- `between_curves`
- `between_instances`
- `to_lower_limit`
- `to_upper_limit`
- `baseline_split`

Curve header controls:

- `show_name`
- `show_unit`
- `show_limits`
- `show_color`
- `wrap_name`

## Raster bindings

Raster bindings support VDL, waveform, and image-style array tracks.

High-value keys:

- `label`
- `style`
- `profile`
- `normalization`
- `waveform_normalization`
- `clip_percentiles`
- `interpolation`
- `show_raster`
- `raster_alpha`
- `color_limits`
- `colorbar`
- `sample_axis`
- `waveform`

Typical array-track use cases:

- VDL density rendering
- waveform-only displays
- waveform overlay on top of raster density

## Reference-track extras

Reference tracks can host local events and scalar overlays while still defining
the layout axis.

Track-level `reference` keys:

- `axis`
- `define_layout`
- `unit`
- `scale`
- `major_step`
- `minor_step`
- `events`

Curve binding `reference_overlay` keys:

- `mode`
  - `curve`
  - `indicator`
  - `ticks`
- `tick_side`
- `lane_start`
- `lane_end`
- `tick_length_ratio`
- `threshold`

## Annotation tracks

Annotation tracks do not use channel bindings for their main content. They use
typed track-local objects.

Supported annotation objects:

- `interval`
- `text`
- `marker`
- `arrow`
- `glyph`

Annotation tracks also respect the standard `grid` configuration, which means
the background grid can be turned on or off without changing object behavior.

## Heading, remarks, and tail

Report packet pages are configured in `document.layout`.

- `heading`
  - first report page cover block
- `remarks`
  - first-page remarks section
- `tail`
  - optional tail page using the same information model

See [Report Pages](report-pages.md) for the report-specific structure.

## Validation helpers

For Python-side validation:

- `wellplot.get_logfile_json_schema()`
- `wellplot.validate_logfile_mapping(...)`

For file loading:

- `wellplot.load_logfile(...)`
- `wellplot.logfile_from_mapping(...)`

## Example starting points

- `examples/cbl_job_demo.log.yaml`
- `examples/cbl_report_pages.log.yaml`
- `examples/cbl_report_pages_open_hole.log.yaml`
- `examples/cbl_feature_showcase_full.log.yaml`
- `examples/reference_track_overlays.log.yaml`

# Report Pages

This page documents the report-page structures that sit around the log strips:

- `heading`
- `remarks`
- `tail`

These blocks live under:

```yaml
document:
  layout:
    heading: ...
    remarks: ...
    tail: ...
```

## Report packet model

The report packet model separates:

- log strips
  - the physical plotted sections
- report pages
  - cover-style heading page
  - remarks page area
  - optional tail page

The heading and tail share the same main information model. The tail is a
reduced follow-on page built from the heading content rather than a completely
separate schema.

## `heading`

The heading is a report block.

It supports:

- company identity block
- service title list
- key/value fields
- coordinates
- scale text
- altitude values
- optional detail table:
  - `open_hole`
  - `cased_hole`

### Core heading keys

- `enabled`
- `show_tail`
- `logo_path`
- `logo_text`
- `company_name`
- `service_titles`
- `fields`
- `coordinates`
- `services`
- `scale_text`
- `altitudes`
- `open_hole`
- `cased_hole`

## `service_titles`

`service_titles` is the main list of log/service names shown in the cover block.

Accepted forms:

- plain string
- numeric value
- object with formatting metadata

Formatting keys:

- `value`
- `source_key`
- `default`
- `font_size`
- `auto_adjust`
- `bold`
- `italic`
- `alignment`

Use the object form when you need heading/tail typography control.

## `fields`

Fields are simple label/value entries for well, field, county, company, and
similar report metadata.

Field-style keys:

- `label`
- `value`
- `source_key`
- `default`

## `coordinates`

Coordinates are usually rendered as labeled values in the heading block.

Typical keys:

- `x`
- `y`
- `z`
- `latitude`
- `longitude`

These are report values, which means they can be:

- literal values
- sourced through `source_key`
- given a `default`

## `scale_text`

The heading and tail scale display is user-supplied.

This is intentional.

The project does not assume one layout scale across every possible packet, so
the report-page scale label remains explicit author-controlled text rather than
being inferred from strip layout at serialization time.

## `altitudes`

The heading altitude block currently supports the standard lanes used in the
project examples:

- `KB`
- `GL`
- `DF`

These are rendered as separate cells in the heading/tail cover layout.

## `remarks`

`remarks` is a list of remark blocks rendered in the first-page remarks area.

Each remark supports:

- `title`
- `text`
- `lines`
- `alignment`
- `font_size`
- `title_font_size`
- `background_color`
- `border`

At least one of these content keys is required:

- `text`
- `lines`

Use `text` for paragraph-like notes.

Use `lines` for explicit line control.

## `tail`

The tail reuses the same report packet information model as the heading.

Current behavior:

- enabled through the heading/tail settings
- intended as a compact end page
- uses the most important heading information, including scale text

Use the tail when you want a closing page for printed packets. Do not use it as
an alternate source of truth for report metadata.

## Detail tables

The report block can include one of the standardized detail tables:

- `open_hole`
- `cased_hole`

For the MVP, the field subsets are intentionally fixed and standardized rather
than arbitrary free-form table definitions.

### `open_hole`

Use this for pre-casing operational details such as:

- date
- service order
- drilled depth
- log depth
- first reading
- last reading
- pipe and hole dimensions
- fluid properties
- measured resistivity values
- equipment and crew notes

### `cased_hole`

Use this for cased-hole operational details such as:

- date
- service order
- drilled depth
- log depth
- first reading
- start time
- end time
- cement top
- fluid and salinity
- pressure and deviation
- nominal speed
- reference log and date
- equipment and crew notes

## Report values

Many report-page fields share the same value model.

A report value can be:

- literal string
- literal number
- object with:
  - `value`
  - `source_key`
  - `default`

This lets you mix:

- hard-coded packet text
- values pulled from dataset metadata
- explicit fallbacks when metadata is absent

## Recommended usage

Use report pages when you are building:

- printable job packets
- vendor-style cover pages
- repeatable heading/tail output from templates

Keep the log strips and the report block separate in your thinking:

- tracks define plotted measurement layout
- report pages define packet identity and operational context

## Example files

- `examples/cbl_report_pages.log.yaml`
- `examples/cbl_report_pages_open_hole.log.yaml`
- `examples/api_end_to_end_demo.py`

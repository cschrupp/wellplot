# S5 Contract Semantics and Prompt Evidence

## Scope

S5 removes public controls that stable MCP dispatch did not honor, corrects a
canonical-to-legacy curve-opacity projection loss, and rewrites server prompts
to use only the registered stable tool names.

## Public-Control Audit

| Control | Outcome | Evidence |
| --- | --- | --- |
| `inspect_authoring.detail` | Retained | Dispatcher returns compact summaries or full scoped objects. |
| `inspect_vocab.family` / `detail` | Retained | Dispatcher validates family and selects compact or full catalog payloads. |
| `inspect_source.include_metadata` | Retained | Dispatcher includes metadata and provenance only when requested. |
| `validate_logfile.level` | Retained | S4 dispatches structural, data, or render validation explicitly. |
| `create_draft.source_data_file` | Removed | It was rejected and could not create a data-backed draft. |
| `render_logfile.backend` | Removed | Rendering uses the document's configured backend; the argument had no effect. |

`render_logfile` continues to report the backend actually used in its result.

## Prompt Contract

All six server prompt templates now refer only to the 17 registered stable
tools. `start_from_example_prompt` refers to packaged example MCP resources
instead of inlining the README and YAML artifacts.

## Regression Coverage

- Stable-profile tests reject the two removed public fields.
- Prompt tests extract call-style references and require membership in
  `stable_tool_profile()`.
- Curve-style round-trip coverage verifies that canonical `alpha` persists as
  legacy `opacity`.
- Curve and scale tests select bindings by stable id and assert canonical
  default serialization explicitly.

# CM-16 Development Memory

## Scope

CM-16 introduces a bounded, host-side inspection facade for preparing compact
worker context from explicit canonical inputs. It does not add discovery,
program-time inspection, capability behavior, or a public runtime route.

- **Migration baseline SHA:** `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c`
- **Slice base SHA:** `ea2d115`
- **Scope:** immutable document projections, explicit section-scoped channel
  projections, fixed selectors, pure tests, and architecture evidence.

## Projection Contract

`AuthoringInspectionFacade` exposes only these methods:

| Method | Projection |
|---|---|
| `document_summary()` | `name`, `title`, `subtitle`, ordered `section_ids` |
| `sections()` | ordered section ID/title/subtitle/depth range, track IDs, track kinds |
| `tracks(section_id)` | ordered track ID/title/kind/width and binding IDs |
| `bindings(section_id, track_id)` | ordered binding ID/kind/channel |
| `header_slots()` | ordered slot ID/key/label, without current values |
| `channels(section_id)` | explicit mnemonic/kind/unit/compact shape metadata |

Document-derived objects preserve canonical order. Channel context is accepted
only as `Mapping[str, Sequence[AuthoringChannelInput]]`, where each key is an
explicit section scope. The facade does not infer source files or map a source
to a section. Returned channels are sorted case-insensitively by
`(mnemonic, kind, unit)`.

## Decisions And Invariants

- Projection models are frozen, strict Pydantic values with forbidden extras.
  Collection fields use tuples so callers cannot mutate returned state.
- The facade deep-copies the document and channel context at construction.
  Serialized caller inputs remain unchanged after construction and every
  projection call.
- Track and binding selection always requires `section_id`; local IDs such as
  `main.combo` and `repeat.combo` remain independently addressable.
- Unknown sections and section-local tracks raise the existing typed
  `ProgramNameError`. Missing explicit channel facts for a known section
  return an empty channel projection; no global channel set is invented.
- Header projections expose slot identity only. They omit current values,
  nested layout, provider metadata, and raw header content.
- Channel projections omit source paths, reader handles, raw metadata, arrays,
  sample values, and sampled min/max values. Shapes are compact dimension
  tuples supplied by the caller.
- The facade is not part of the CM-12 interpreter registry. The intended flow
  is host inspection, compact worker context, then generated program.

## Validation

- `UV_CACHE_DIR=/tmp/wellplot-uv-cache uv run pytest -q
  tests/test_authoring_program_inspection.py` passed: `9 passed in 0.89s`.
- The final combined CM-10 through CM-16 test, Ruff, formatting, and diff
  evidence is recorded with this slice commit.

## Runtime And Production Delta

- Production addition: one read-only inspection facade and its immutable
  projection models.
- Direct dependencies remain below the agent and edge layers: canonical
  authoring context and model modules only.
- Automatic source discovery, filesystem inspection, program-time inspection,
  capability plugins, providers, planners, LangGraph, MCP, routing,
  persistence, rendering, notebooks, and legacy deletion delta: zero.

## Limitations And Deferrals

CM-16 does not acquire source metadata, inspect files, expose a full canonical
document dump, or make inspection available to generated programs. It does not
interpret track or binding semantics beyond projecting canonical kind fields,
and contains no CBL, VDL, GR, resistivity, or other capability knowledge.

CM-20 owns capability-plugin v2 contracts. No provider, planner, graph, MCP,
routing, or legacy-deletion work is included in this slice.

## Decision

**STOP after CM-16. Proceed to CM-20 only after this slice is committed and
pushed.**

# Private WellPlot dependency inventory (SLM-01)

SLM-01 lowerer currently operates on an experimental `DocumentState` model and
does **not** import private `src/wellplot/_*` modules.

## Allowed product imports (public / stable)

| Module | Use |
|---|---|
| `wellplot` (package install) | Optional future round-trip validation |
| None required at runtime for apply() | DocumentState is self-contained |

## Private interfaces consumed

_None as of SLM-01 candidate._

If a future revision reaches into non-public WellPlot helpers, list them here
before merge/review. No private interface may be promoted to public API solely
to accommodate SLM-01.

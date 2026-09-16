# CM-51R Development Memory

## Scope

CM-51R hardens the opt-in agentic MCP edge after the CM-51 implementation
review. The slice preserves the MCP tool schema, v2 session composition,
private canonical transaction, persistence gate, default engine, and legacy
implementation.

- **Slice base SHA:** `ca03c37`
- **Implementation commit:** `7b27529` (`Harden CM-51 MCP edge semantics`)
- **Production LOC delta:** `+23 / -12`
- **Test LOC delta:** `+74 / -1`
- **Runtime behavior delta:** relative logfile paths resolve against the
  configured MCP root; unexpected session exceptions record a bounded terminal
  trace event before being re-raised; executor-failure evidence now proves
  private mutation is discarded before persistence.

## Corrections

The MCP edge now preserves the historical root semantics for relative
`logfile_path` values. Absolute paths remain absolute, while relative paths are
joined to the resolved server root before canonicalization and containment
validation. The result is independent of the process working directory.

The direct session boundary remains exception-transparent. If an unexpected
exception escapes `AgentSession.build()` or `AgentSession.revise()`, the edge
records only:

```text
event: run_finished
status: failed
details: {error_type: <exception class name>}
```

The exception is then re-raised unchanged. Exception text is not copied into
the terminal trace, so this path does not widen diagnostic disclosure or turn
programming defects into normal MCP result objects.

The execution-failure test now mutates the private `AuthoringService` before
returning failure. The persisted logfile remains byte-for-byte unchanged,
proving that partial private state cannot escape the transaction.

## Validation

- Focused MCP and architecture tests: `20 passed`.
- Full MCP/agentic regression selection: `211 passed, 2 skipped, 11 subtests passed`.
- Ruff check over changed Python files: passed.
- Ruff format check over changed Python files: passed.
- `git diff --check`: passed.

## Boundaries

CM-51R does not change provider/session contracts, MCP tool names or
arguments, result fields, source discovery, persistence, rendering, routing,
notebooks, the default engine, retries, or legacy deletion. No compatibility
shim or provider-specific behavior was added.

The existing CM-51 trace remains the sidecar location. This correction only
adds terminal evidence for exceptions that are intentionally re-raised; it
does not retain prompts, generated programs, provider objects, full plans,
LangGraph state, or canonical source paths.

## Decision

```text
CM-51 implementation       complete
CM-51R hardening           complete
CM-52 notebook cutover     blocked pending separate authorization
CM-53 default v2 engine    blocked pending separate authorization
```

**PROCEED / STOP:** CM-51R is implemented, committed, and ready to push.
Stop before CM-52 planning or implementation changes.

# CM-53R3 Development Memory

## Scope

CM-53R3 hardens the report and section worker SDK references after the
default-v2 probes showed models copying unsupported executable arguments. The
slice changes worker-facing documentation and tests only. The deterministic
interpreter remains strict; no aliases, argument rewriting, source inference,
planner changes, routing changes, or additional repair attempts were added.

- **Slice base SHA:** `062b7f5`
- **Implementation commit:** `787ec71` (`Harden Code Mode worker SDK contracts`)
- **Production delta:** `+127 / -87` across `program_worker.py` and
  `report_worker.py`
- **Test delta:** `+89 / -3` across the two focused worker test modules
- **Runtime behavior delta:** worker prompts now expose exact call shapes,
  allowed keyword sets, and bounded host-grounded source/channel/slot facts;
  kernel validation is unchanged

## Worker Contracts

The section worker now documents positional handles and exact keyword sets for
`wp.source`, `wp.section`, `wp.target_section`, `wp.update_section`,
`wp.track`, `wp.curve`, and `wp.raster`. The report worker does the same for
all report primitives. Unsupported names such as `scale_linear`, `x_scale`,
and `high` are absent from the worker contract.

Context-sensitive examples remain host-bounded:

```text
source handles       exact opaque candidate IDs only
channel examples     exact loaded mnemonics and scalar/array kinds only
report identifiers   only keys and service-title slots present in context
canonical paths      never included
```

The initial worker prompt and CM-34 repair prompt receive the same generated
SDK contract. With no selected source, no host-specific source handle is
shown. Multiple sources are listed without privileging the first candidate.

## Validation

- Focused Code Mode/worker suite: `53 passed`.
- Ruff check: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- The strict interpreter test still rejects an invented `scale_linear`
  keyword with `ProgramTypeError`.

## Local Default-Route Probe

The same three-run local Qwen public-route probe was rerun with `engine`
omitted, the verified `qwen3.6-35b-a3b` endpoint, temperature `1.0`,
`top_p=0.95`, `max_tokens=16384`, and thinking disabled. All three runs
reached `engine="v2"`; none fell back to v1.

The final batch was `0/3` accepted. The prior unsupported scale/channel
argument failures did not recur, but the model still produced calls outside
the documented contract, including missing positional handles, an unregistered
`wp.current_report`, and malformed section/target construction. One run also
ended with a bounded `provider.invalid_response` during section repair.

This is non-acceptance probe evidence, not CM-43R2 evidence. The full frozen
acceptance set was not run after this result, and no acceptance JSONL was
updated.

## Decision

```text
CM-53 routing implementation       accepted
CM-53R3 worker contract            complete (`787ec71`)
unsupported keyword documentation  removed
host-grounded examples             preserved
kernel strictness                  unchanged
extra repair attempts              0
default-v2 transition              open
CM-60+                             blocked
```

**PROCEED / STOP:** Stop before expanding the frozen CM-43R2 live suite or
changing planner, channel/source selection, runtime strictness, routing, or
provider behavior. The probe demonstrates remaining model adherence failures,
not a proven Wellplot kernel defect.

# Incremental Report Construction

Report reconstruction compiles small typed artifacts before persisting the packet.
The planner still identifies the requested report values. The report compiler
partitions that plan into report settings, groups of at most eight header slots,
and individual remarks. Tasks run sequentially; each has its own three-round
structured-response budget and a schema limited to its fields and target IDs.

The planner's header collections are also scoped to the stable slot IDs exposed
by the inspected starter document. A request for a semantic field such as a
state must select the matching existing slot, such as `general.country` when
that is the starter's State/Country field. It cannot create `general.state`.
Invalid planner submissions receive the provider's normal schema correction
before report tasks begin.

Each candidate is combined with accepted artifacts in memory and checked through
the existing canonical authoring executor on a copy of the scaffold. Rejected
candidates do not replace accepted work. The combined artifact must still cover
all planned report values. Packet persistence and final verification remain the
responsibility of the existing graph transaction; passing one task does not save
a partial packet.

Trace events use stage `report_task` and targets such as
`report.general_fields.2` or `report.remark.1`. This exposes exactly which small
submission was rejected. A failed task stops report compilation. Accepted work
is retained during that invocation, not checkpointed for a later notebook retry.

Revision compilation retains its existing sparse report contract. Custom report
capabilities retain their own artifact models. Reconstruction plans without
explicit header collections or remarks use the existing single report task.

This change addresses report omissions seen in run
`326fa1d854a1442b8fa127668780c0c7`: the report worker omitted eleven planned fields
in repeated submissions and then lost previously supplied remarks and titles.
The same run also experienced section transport failures; task decomposition does
not resolve provider disconnects or overload. More, smaller calls can increase
latency and input-token cost. Live evaluation is still needed to measure that
tradeoff. Section task decomposition is outside this change.

## Section Schema Follow-up

Run `3c8350994f9f47e3b952925b2ac0a6a5` completed report compilation, then
submitted an expanded main-pass artifact with invalid VDL limits `[0, 1]`.
The correction request and the repeat-pass request both disconnected.

Section artifacts already use partial intents and preserve omitted fields.
Collections with no planned children now advertise only an empty array, without
pulling the unused child models into the function schema. This retains rejection
of unplanned children and the existing revision clear semantics. Planned fills
and annotations still receive their full typed schemas.

Section guidance asks for requested properties and required identities rather
than expanded defaults. The raster limit field explains that VDL limits must
straddle zero even with amplitude normalization disabled: its rendered color
map remains centered on zero. Omitted limits retain existing settings or use
automatic limits for new bindings. Explicit overrides remain subject to canonical
validation. This reduces schema overhead and clarifies the observed validation
failure; it does not guarantee provider transport reliability or add retries.

## Planner Report Coverage

Planner context now includes the stable detail slot IDs together with each
row's semantic key and label. The planner response contract also carries typed
remarks. Every explicit report header value, including detail-row values, and
every explicit remark must appear in `report_values`; the report tasks then
compile and verify those values independently.

Header plan values are display text. The planner preserves requested units and
fixed precision instead of converting values such as `5445.50 ft` to a numeric
value. Packet acceptance compares rendered scale endpoints, so equivalent
canonical forms such as ascending bounds plus `reverse: true` are accepted.
Descending bounds combined with `reverse: true` invert a scale twice and are
rejected.

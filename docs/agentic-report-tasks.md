# Incremental Report Construction

Report reconstruction compiles small typed artifacts before persisting the packet.
The planner still identifies the requested report values. The report compiler
partitions that plan into report settings, groups of at most eight header slots,
and individual remarks. Tasks run sequentially; each has its own three-round
structured-response budget and a schema limited to its fields and target IDs.

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

# D5-5D Sealed Evidence Analysis

## Scope and custody

```yaml
authority: WELLPLOT-D5-5D-SEALED-EVIDENCE-ANALYSIS-AUTH-001
analysis_checkpoint: bcae7f532a54705ab83993f846f7b5f6a4e58664
provider_model_calls_during_analysis: 0
sealed_campaigns_modified: false
decision: QWEN_FAIL_LUNA_INCONCLUSIVE_COMPARISON_INCOMPLETE
```

Only the committed, sealed artifacts were read. Prompts, credentials,
generated payloads, and hidden reasoning are not reproduced here.

| Lane | State | Journal | Terminal | Summary | Evidence |
| --- | --- | --- | --- | --- | --- |
| Qwen `d5-5-qwen-001` | `e2924e5da900fa78358d25c3bbe5bd5dce1cc892c5846a571bce212e6de6ceaf` | `8bfd089cd8c378e240eaf567d62b7d41143d082fc0a2a51d36bec66e560cff99` | `1b7b755aabec8820a9823b65f87986a26bdc8c7ec63c346c20a2f524372f6f68` | `3ded8a9b8311881c6a8403b4aa87c3487f091d2d075b369a3e55d4881d60e985` | `0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac` |
| Luna `d5-5-luna-001` | `6ea36c15f565e2b2e0f6dad8c4c41b9ce79aa4ac360395f4544ad5d941e4054d` | `f4e608fcbdf7db7dacac83f92d0da134e254e5602dbeb9b74ce47232619ec91a` | `1a2d87632643c6e64c1217be88dc43a8248e07fb91c72c53a2e443e7a5ea1130` | `1b831a80826d4c2bbcfafa80f67f516b18e3a1bbe70a5e201a2368cdd1b512e2` | `e662ffb9988d2e171b8cfe9e68e33707a84694c19e5bd7411b691cc9fd2366fd` |

The terminal cross-references match the state, journal, and evidence digests
listed above. Both namespaces contain the expected state, journal, terminal,
summary, and evidence files. The historical D5-4 campaign was not changed.

## Qwen result

The sealed Qwen campaign completed all nine turns and terminally recorded:

```yaml
decision: FAIL
attribution: SEMANTIC_CONTRACT
logical_generation_calls: 21
physical_generation_attempts: 21
provider_calls: 21
model_calls: 21
endpoint_calls: 2
```

The exact failed turns and earliest evidence-supported causal boundary are:

| Turn | Evidence | Earliest causal boundary |
| --- | --- | --- |
| `D4-C01:C01` | `CBL-01`, `02`, `04`, `05`, `06`, `08`, and `09` failed; persistence and render were not proven | The model-produced canonical result failed deterministic CBL verification before persistence/render. This is a semantic contract failure, not a custody or provider failure. |
| `D4-L01:T1` | `LAS-02` and `LAS-09` failed; the required title change was missing and persistence/render were not proven | The model-produced canonical result failed the required title transition and preservation contract before persistence/render. |
| `D4-L01:T3` | `LAS-03` and `LAS-09` failed; track title/kind/width and binding label/channel/scale assertions failed | The model-produced canonical result failed the required track/binding semantic transition before persistence/render. |

The remaining Qwen turns passed their sealed deterministic gates:

```yaml
D4-L01:T2: PASS / persisted / rendered
D4-L01:T4: PASS / persisted / rendered
D4-L02:T1: PASS / safe negative / unchanged
D4-L02:T2: PASS / persisted / rendered
D4-L03:C01: PASS / safe negative / unchanged
D4-L04:C01: PASS / safe negative / unchanged
```

This is a valid Qwen failure result. It is not evidence for replay or
selective rerun.

## Historical D5-4 comparison

The exact historical D5-4 per-turn artifact namespace is not available in this
checkout. The comparison is therefore bounded to the accepted D5-4 result and
hardening contract; no unsupported per-turn historical delta is claimed.

Within that admissible boundary, D5-5 Qwen evidence shows the post-hardening
system still handles the safe-negative cases and selected LAS persistence/
render paths, while CBL construction and two positive LAS semantic transitions
remain model-sensitive. The current evidence does not establish that the
remaining failures are caused by the canonical deterministic engine.

## Luna result

The sealed Luna campaign stopped on its first measured generation:

```yaml
decision: INCONCLUSIVE
attribution: PROVIDER_BOUNDARY / STRUCTURED_OUTPUT
failure_category: provider_rejected
completed_turns: 1
logical_generation_calls: 1
physical_generation_attempts: 1
provider_calls: 1
model_calls: 1
endpoint_calls: 1
```

No HTTP status was retained in the admissible sealed evidence. The evidence
supports a structured-output/provider-boundary rejection, but it does not
distinguish model capability from provider routing or endpoint contract
incompatibility. Luna therefore supplies no usable semantic benchmark result
and must not be described as a model-capability failure. It remains sealed
historical evidence and is not replayed.

## Post-terminal cleanup defect

The campaign terminal records were written before the command process exited.
The execution wrapper separately exhibited an `Event loop is closed` cleanup
failure because it called `asyncio.run(campaign)` and then
`asyncio.run(close_async_client)`. This is a harness lifecycle defect after
terminal custody, not a campaign result, provider/model failure, or mutation
of either sealed namespace. The replacement preparation closes the adapter in
the same async lifecycle.

## Disposition

```yaml
qwen: FAIL / SEMANTIC_CONTRACT
luna: INCONCLUSIVE / PROVIDER_BOUNDARY / STRUCTURED_OUTPUT
comparison: INCOMPLETE
replay: FORBIDDEN
sealed_artifacts: PRESERVED
next_preparation: DEEPSEEK / d5-5-deepseek-001
```

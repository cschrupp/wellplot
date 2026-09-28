# CM-57P10 Final Fresh Promotion Gate

## Status

CM-57P10 was prepared as a fresh, provider-controlled final promotion gate.
The authorized live population has now completed and produced a valid terminal
decision.

```text
baseline: 5244db6fc169c78201c1ffcd751c01c0d045b5fd
authorized checkpoint: fd3448487cbd3418bbcb33a89ce5e5b809198e42
experiment: CM-57P10
decision: FINAL_PROMOTION_RC_REJECTED
provider calls: 106
worker/program calls: 0
production changes: 0
CM-57P closed after valid result: true
CM-57D: blocked
```

P9A remains immutable at its recorded result:
`INCONCLUSIVE_REPRODUCIBILITY_EVALUATION`. P9C is a separate provider-free
provenance preparation step and does not rewrite or upgrade the P9A decision.

## P9C Endpoint Provenance

CM-57P9C used exactly five non-inference `GET /v1/models` probes against the
configured endpoint. All five probes reported the configured model label and
the same sorted, unique available model identifiers.

```text
decision: ENDPOINT_PROVENANCE_NORMALIZED_STABLE
probe count: 5
endpoint: http://192.168.2.140:8888/v1
model API label: qwen3.6-35b-a3b
available model IDs: qwen3.6-35b-a3b
normalized identity SHA-256:
23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980
raw catalog SHA-256:
881772e8f41e3ba60e1930f9ffa3193667942b9d9d20da7b44c9ade621ad494e
```

The normalized endpoint identity is decision-bearing. The raw catalog hash is
descriptive evidence only and is not used as a failure condition for the
normalized P9C result. No completion or other inference request was made by
P9C. The bounded summary is recorded in
`CM-57P9C-endpoint-provenance-summary.json`.

## Live Result

The authorized P10 matrix completed once at the reviewed checkpoint. The
population is complete and endpoint provenance is valid: the normalized PRE
and POST endpoint identities matched, while their raw catalog hashes differed
and remained descriptive only.

```text
cases: 24
attempts per case: 2
shared rows: 48
planner executions: 96
provider calls: 106
worker/program calls: 0
P stable passes: 4
RC stable passes: 16
candidate gains: 13
protected regressions: 1
RC unstable cases: 0
RC terminal failures: 2
unexpected references: 6
missing required references: 0
decision: FINAL_PROMOTION_RC_REJECTED
```

The raw JSONL is preserved outside the repository:

```text
/tmp/cm57p10-final-promotion-qwen.jsonl
sha256: e38f7054443301e56a7d9c7d17fdff9bc5a41d404768b970759421fcda460d5d
```

The bounded provider-free finalization summary is committed as
`CM-57P10-final-promotion-live-summary.json` with SHA-256
`8e23ff688fdca200caabab212dbd34c042fa7195f45d615af99a326c728f7cb4`.

The result is a valid terminal rejection, not an infrastructure or provenance
inconclusive result. The candidate improved many section cases but violated a
protected P-pass case and the reference-safety gate; the frozen promotion
contract therefore rejects RC. The P-series is closed after this valid result:
no P11, new prompt candidate, new holdout, threshold adjustment, or additional
reproducibility experiment is authorized.

## P10 Question

CM-57P10 asks whether the complete production candidate remains viable on a
fresh holdout when the current production planner is compared with the frozen
RC prompt. It uses the production planner, production `SemanticPlan` schema,
existing P5 evaluator, and the unchanged provider boundary. It does not
change routing, prompts, schemas, capability metadata, or production code.

The candidate arm is evaluated against the production arm on the same case and
attempt. No provider output is generated during this implementation slice.

## Fresh Holdout

The corpus is versioned as `cm57p10.final-promotion.v1` and contains 24
independently authored cases: four cases in each of six families.

```text
REPORT_ONLY
SINGLE_SECTION_NO_REFERENCE
REFERENCE_REQUIRED
MULTITRACK_SINGLE_SECTION
MULTI_SECTION
MIXED_REPORT_SECTION
```

The loader rejects duplicate IDs, duplicate normalized requests, historical
request hashes from the P5/P7 corpora, paths, capability IDs, planner schema
terms, and nonzero unresolved requirements. Existing P5 capability gold is
reused only as bounded evaluation gold; it is not provider input.

```text
corpus SHA-256:
43d06f5808340beda1af178e08f3dfd14bd241cad5c84064d50a9dca9216582f
```

## Frozen Controls

```text
model: qwen3.6-35b-a3b
planner temperature: 0.0
max output tokens: 16384
token parameter: max_tokens
timeout: 900 seconds
concurrency: 1
arms: P -> RC
attempts: 2 per case and arm
cases: 24
families: 6 x 4
shared rows: 48
planner executions: 96
expected provider calls: 96-192
worker/program calls: 0
```

The frozen prompt, schema, source-summary, planner, provider, and capability
artifact hashes are recorded by the P10 harness. The P10 provider path is
sequential and rejects an existing non-empty evidence file before provider
construction.

```text
P prompt SHA-256:
5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18
RC prompt SHA-256:
e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34
response schema SHA-256:
3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3
source-summary SHA-256:
ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e
planner source SHA-256:
0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413
provider base SHA-256:
4c14afc1e6e53faef1ef99266059b7b88b6c4dec4bfb5a4768ca5b36efc3f049
OpenAI-compatible provider SHA-256:
1409f83cdc6e8ed376f3d1d59102acde06b3e272ce15035adec6cd830723c653
capability catalog file SHA-256:
2290d9656bf69cea130e97c39da4c572449a0bbb3bcd6aff61463f25b2702cac
capability catalog SHA-256:
b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37
P9C summary SHA-256:
862e51e688405089640b9e77105b33c7ba29e196be4743ca98ccf443dc371a31
```

## Evidence and Decision Boundary

Future rows retain bounded outcome, plan, call-path, semantic-fact, and
provenance evidence only. Provider response text, request payloads, document
paths, and raw provider responses are not persisted. Each future row is bound
to the authorized checkpoint and current P10 provenance.

The live row also carries `endpoint_pre_fingerprint_sha256`, computed as the
SHA-256 of the complete canonical PRE v2 fingerprint. Finalization requires
every row to match the supplied PRE fingerprint hash, so evidence from one
endpoint session cannot be combined with PRE/POST files from another session.

The runner classifies case/arm outcomes as `STABLE_PASS`, `STABLE_FAIL`, or
`UNSTABLE`. Finalization is fail-closed for incomplete populations, provenance
drift, endpoint instability, infrastructure failures, protected regressions,
reference-safety violations, parent-section closure violations, duplicate
section violations, or insufficient candidate gains.

The only future top-level decisions are:

```text
FINAL_PROMOTION_RC_ACCEPTED
FINAL_PROMOTION_RC_REJECTED
INCONCLUSIVE_FINAL_PROMOTION_EVALUATION
```

Acceptance requires a complete valid population, stable RC cases, no protected
regressions, at least three RC-only gains, net gain of at least three, at least
18 stable RC passes, reference safety, and structural closure/multiplicity
invariants. A valid P10 result remains evidence for review; it does not itself
authorize production adoption or CM-57D.

For either valid terminal decision (`FINAL_PROMOTION_RC_ACCEPTED` or
`FINAL_PROMOTION_RC_REJECTED`), the summary records the P-series hard stop:

```text
CM57P_closed_after_valid_result: true
prompt_revisions_remaining: 0
fresh_promotion_holdouts_remaining: 0
additional_prompt_experiments_authorized: false
```

An inconclusive result keeps the closure flag false and leaves the remaining
promotion counts unavailable for any permitted infrastructure replacement.

## Future Evidence Paths and Hard Stop

The future live runner uses fresh paths and must not append or resume:

```text
/tmp/cm57p10-final-promotion-qwen.jsonl
/tmp/cm57p10-endpoint-pre.json
/tmp/cm57p10-endpoint-post.json
```

The output JSONL must be absent or zero-length before the live runner starts.
There is no smoke request, selective rerun, or partial-population recovery.
If execution is interrupted, the partial raw evidence is preserved separately
and the population is not resumed or merged.

P10 live inference is complete. The valid terminal rejection closes CM-57P;
CM-57D remains blocked and no production adoption is authorized by this
evidence-only result. Further work must be separately scoped outside the
closed P-series.

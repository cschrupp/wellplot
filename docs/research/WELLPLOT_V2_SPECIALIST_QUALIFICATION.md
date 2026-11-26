# Isolated specialist qualification

The `isolated-specialists` population uses the existing D5 observation mode,
authority, readiness, physical-attempt observer, shared call ledger and custody
verifier. No model-facing planner output or host-selected action is supplied.
The canonical workers return the first typed observation without entering
their production compile methods.

## Frozen identities

| Artifact | SHA-256 |
| --- | --- |
| [Ordered W01–W08 panel](WELLPLOT_V2_SPECIALIST_PANEL.json) | `729292eee9e54c3bb09705c30eca692b530ab28a7b285a8c5237ab83ef9f9817` |
| [Report manual](WELLPLOT_V2_SPECIALIST_REPORT.md) | `8ff3cd897fba7fe66ad84326dbdce9044ec9a827179b23b32e4d1a9ecab4a588` |
| [Section manual](WELLPLOT_V2_SPECIALIST_SECTION.md) | `f2522ae3d1191eb6db265af04c230e93d7f71a03b3194027e334d69a724088e0` |
| [Independent rubric](WELLPLOT_V2_SPECIALIST_RUBRIC.md) | `330808aedb47568480d98085a722002f91bb5eed85bc7eff80fb293e46a432eb` |
| Report advertised schema | `0db39fb37d254600f80403e175586e804db85d5460697dd2d31a73b065e55f88` |
| Section advertised schema | `ac2928f97643f08becb002a5229a950ecbfa6adae62140bb40d39c5ae1e401a1` |
| Authority schema bundle | `47b3358ac648af374843fa15e15ed75e349c7687e41aa2bf09223a32010f638e` |
| Ordered rendered input pairs | `9b72e75dba95712aa04fb936ae6c5d3343303457413a564ea25887af0e1df613` |

Schema and rendered-input hashes use the D5 canonical JSON encoding. The
input digest covers exact system and user message strings, in order, including
canonical document serialization, inspection projections and objectives.
It is bound through the existing `planner_population_system_prompt_sha256`
authority field for this profile. The harness digest and schema bundle have
separate existing authority fields. The actual HTTP request bodies,
settings, schemas and response bytes are retained by existing model-I/O
custody, rather than reconstructing HTTP evidence from message digests.

Individual rendered pair SHA-256 values, in the same canonical encoding:

| Case | SHA-256 |
| --- | --- |
| W01 | `de0dc8fdb0da7a79543d273df3d200e35b803574ba2b660718904cdecf3df8aa` |
| W02 | `dace77465a2d8a40d8a8f1adbbc5f3ef6efbde34025462f1d4f6bb2a104a1e74` |
| W03 | `abef0b43e7b4f3f63ae6a7ffb7e0c7c01252fa973ba57be1ed144490f96e34cc` |
| W04 | `48707df26d4cf0e592a621222ad9240c864ae341e5e5cd0e66fd3b882b6426f8` |
| W05 | `21a31ecf4ba795233943f28e3b74020527e99f35f36062c6bb9aba10db012dd6` |
| W06 | `4856f4938e456cadda958cabd36ae556855df0e57cb1b033dc4b6762df4fd117` |
| W07 | `2fab99ca9117c76be9a1546a235f7d76f2e5ffe799363e0c40588ea7e066d914` |
| W08 | `0ad2c0c0580121a0394e6fdb86b9cb1c4b3b1160681b1fe7cf0098be2ebbb57a` |

## Qualification boundary

The canonical HTTP mock test executes all W01–W08 in order (three report,
five section) with one deliberately invalid initial response. It verifies
eight logical and physical attempts, exact role-specific schemas and
messages, zero correction, and sealed custody. The interruption variant
injects a read timeout at W02, stops before W03, and verifies sealed
inconclusive transport evidence. Production planner and worker compilation
are forbidden in these tests. The ledger rejects wrong-role calls, duplicates
and physical retries before delegation.

Focused results: 14 D5 first-pass authority and observation tests passed
(including A10, H1a, H1b and revised S03), and 163 specialist boundary and
canonical worker regression tests passed.

No live inference was performed. Exact tokenizer/template budget and
separate smoke and measured execution authority remain operational gates.
Integrated H2, S05 and S06 dependency edges are unchanged.

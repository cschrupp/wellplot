# Isolated specialist smoke preparation

The [non-panel fixtures](WELLPLOT_V2_SPECIALIST_SMOKE_FIXTURES.json) reuse the
frozen manuals and schemas. The report proposes an exact sparse title revision;
the section proposes a scalar binding using an inspected track handle. Neither
path compiles, lowers, executes or publishes an action.

| Role | Fixture SHA-256 | Rendered input pair SHA-256 |
| --- | --- | --- |
| Report | `3bab7150a8e8671db5db578d814f951ad55529a6594decdb28763effe0ffd5b2` | `09c88dc9b832aa7cf5fbd7ef33a43c91a96d8b33ab4eae771293c2c2a6299a8c` |
| Section | `c451f11dc7c1a096dc03903abaa1238f70a55bb6dc451e3a9da2e01af5128022` | `f99cd4ffad2c785a192677c1cbbd5f28946efcd1e71b6dd5816e853d6253097a` |

| Role | Input tokens | Exact SDK body SHA-256 |
| --- | ---: | --- |
| Report | 1561 | `0501479212dd723b153b874ff903dcdb44f7b70d3139baf6dbfff288ded4d962` |
| Section | 2048 | `b43958754969e0895236164aced24403461918be703fcfde5a4536c3cad55118` |

The canonical readiness projection matched Qwen `qwen3.6-35b-a3b`, build
`b12340-b8645ddda`, context 65,536, template SHA-256
`55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c`,
and defaults SHA-256
`5136c0f2b22a73572fe88f44e8cf32159ffb3b345ced2e33ba7507d612f7f8c3`.
GGUF byte identity was unavailable. Authenticated `/apply-template` rendered
byte-identical prompts with and without each advertised schema; both had
the thinking-disabled suffix. `/tokenize` counted special tokens. Both fit
without truncation under 60,000 inputs, reserving 4,096 output and 1,440 margin.
No generation endpoint was called.

Mock HTTP qualifies valid and invalid first responses for each role, rejects
wrong roles and duplicate attempts, verifies exact prompts and schemas, and
checks sealed custody. Neither profile can load the measured panel.
Descriptors are proposed only, not live authority. Integrated H2 is blocked.

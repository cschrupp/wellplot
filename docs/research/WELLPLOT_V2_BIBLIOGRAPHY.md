# WellPlot V2 — Research bibliography and architectural reading notes

Collected 2026-11-25. Scope: the S03 planner/worker instruction research and the subsequent discussion of conversational scientific authoring, shared context, specialist responsibility, clarification, recovery and outcome-based evaluation.

This is a living **reference collection**, not a new architecture decision, experiment freeze, implementation authority or live authority. The existing [roadmap](../roadmap.md), [Project Decision Protocol](../project-decision-protocol.md) and [Planner–Worker Authority Revision](../architecture/PLANNER_WORKER_AUTHORITY_REVISION.md) govern their respective concerns. External results do not establish WellPlot or Qwen performance. The application notes below are proposed adaptations or cautions, not findings of the cited papers. Years denote original paper/preprint publication unless indicated. Product documentation is living material; consult its current version before adopting an interface.

## Existing repository research (preserve; do not duplicate or rewrite)

- [SI-V2.1 External Architecture Research](../evaluations/agent-code-mode/semantic-ir-v2/02-external-research.md): existing notes on Vega-Lite, Flint, PICARD and compiler IR practice. Those remain the provenance of that historical semantic-IR design.
- [S01–S02 evidence and H1 freeze](WELLPLOT_V2_S01_S02_H1.md): prior experiment non-rediscovery evidence, model observations and original grading.
- [S03 instruction recovery and implementation](WELLPLOT_V2_S03_IMPLEMENTATION.md): existing WellPlot manuals and historical notebooks, H1a instructional package, Brown et al. and Liu et al. references, accepted measured closeout.
- [H1b design](WELLPLOT_V2_H1B_DESIGN.md): scientific planning/delegation, SHOP2 inspiration, frozen prompts and corrected compiler evidence.
- [Published WellPlot documentation](https://wellplot.readthedocs.io/en/latest/): application knowledge; prefer the corresponding repository revision when binding actual experimental instructions.

## A. Closest analogues: conversational visualization and analytics

| ID | Primary source | Relevance to WellPlot |
| --- | --- | --- |
| VIS-01 | [Data Formulator 2: Iterative Creation of Data Visualizations, with AI Transforming Data Along the Way](https://doi.org/10.1145/3706598.3713296), CHI 2025; [preprint](https://arxiv.org/abs/2408.16119); [implementation](https://github.com/microsoft/data-formulator) | Iterative intent-driven visualization, existing artifact refinement, data transformation delegation and exploration history. Blended UI/NL is an analogue, not evidence that a particular agent split works for well logs. |
| VIS-02 | [Facilitating Conversational Interaction in Natural Language Interfaces for Visualization](https://arxiv.org/abs/2207.00189), 2022; NL4DV conversational extension | Structured analytic specifications, contextual follow-up queries and ambiguity resolution. Retain the pending objective when a user clarifies a field or value. |
| VIS-03 | Gao et al., [DataTone: Managing Ambiguity in Natural Language Interfaces for Data Visualization](https://research.adobe.com/publication/datatone-managing-ambiguity-in-natural-language-interfaces-for-data-visualization/), UIST 2015 | Mixed-initiative resolution of consequential ambiguity and retention of user corrections. Do not silently choose scientifically distinct source channels. |
| VIS-04 | Databricks, [Genie conversation API](https://docs.databricks.com/api/genie/v1/conversation), [conversation/message representation](https://docs.databricks.com/api/genie/v1/genie-list-conversations) | Conversation identity and separate answer/follow-up-question attachments. One turn can communicate useful results plus a clarification. Product API is an example, not a WellPlot dependency. |
| VIS-05 | Microsoft, [Use Copilot with semantic models in Power BI](https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-semantic-models), [Prepare data for AI FAQ](https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-faq) | Grounding in authoritative semantic metadata and documented limitations. Expose trustworthy source/document information; verify model assertions instead of inferring availability from generated text. |

## B. Dialogue state, memory and conversational repair

| ID | Primary source | Relevance to WellPlot |
| --- | --- | --- |
| DIA-01 | Rasa, [CALM](https://rasa.com/calm), [Handling deviations from the happy path](https://learning.rasa.com/rasa-pro/deviations-from-happypath/) and [reference conversation-repair flows](https://github.com/RasaHQ/rasa-calm-demo/blob/main/data/flows/patterns.yml) | Separate understanding from business rules and recovery. Clarification, correction, cancellation and errors have different continuation semantics. Adapt the concepts to the existing host-owned conversation/outcome state; do not install a parallel flow engine. |
| DIA-02 | [A Survey of the Evolution of Language Model-Based Dialogue Systems — companion research index](https://github.com/hrwise-nlp/Survey-Evolution-DS) | Background on task-oriented dialogue: understanding, dialogue-state tracking, policy and language generation as distinct responsibilities. The companion index is retained for further reading, not as an empirical evaluation of our architecture. |

Design implications discussed: preserve the full ordered transcript in storage, distinguish prior statements from current verified document state, retain unresolved objectives and explicit user decisions, and resume only still-requested work using refreshed state. Complete transcript availability and initial full-context experiments are WellPlot proposals, not requirements established by these references.

## C. Scientific planning, decomposition and orchestration

| ID | Primary source | Relevance to WellPlot |
| --- | --- | --- |
| PLN-01 | [SHOP2: An HTN Planning System](https://doi.org/10.1613/jair.1141), JAIR 2003; [open preprint](https://arxiv.org/abs/1106.4869) | Separate compound objectives and their decomposition; express necessary ordering. H1b adapts the distinction, not the HTN execution system. |
| PLN-02 | Wang et al., [Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models](https://arxiv.org/abs/2305.04091), 2023 | Deliberate planning methodology and avoiding missing steps. Motivate objective accounting, not mandatory exposure of private reasoning traces. |
| PLN-03 | Zhou et al., [Least-to-Most Prompting Enables Complex Reasoning in Large Language Models](https://arxiv.org/abs/2205.10625), 2022 | Decompose complex problems into simpler subproblems. Scientific dependencies should be distinguished from implementation prerequisites. |
| PLN-04 | Kim et al., [An LLM Compiler for Parallel Function Calling](https://arxiv.org/abs/2312.04511), 2023 | Planner, task dispatch, dependency-aware execution. Reuse our own host and canonical graph; no new scheduler or compiler. |
| PLN-05 | Prasad et al., [ADaPT: As-Needed Decomposition and Planning with Language Models](https://arxiv.org/abs/2311.05772), 2023 | Adaptive decomposition when execution encounters difficulty; do not require a complete implementation plan before scientific investigation. |
| PLN-06 | Anthropic, [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents), 2024 | Orchestrator–workers, environmental feedback and bounded complexity. Distinguish predictable workflows from autonomous decisions. |
| PLN-07 | OpenAI, [A Practical Guide to Building AI Agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/) | Manager versus handoff orchestration. Retain one user-facing conversational identity and specialized responsibilities within the existing workflow. |
| PLN-08 | Anthropic, [How We Built Our Multi-Agent Research System](https://www.anthropic.com/research/multi-agent-research-system), 2025 | Concrete lead/subagent coordination, task descriptions and evaluation practices. Reported gains and token costs are system-specific, not causal evidence for WellPlot. |
| PLN-09 | Anthropic Cookbook, [lead-agent prompt](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/prompts/research_lead_agent.md) and [subagent prompt](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/prompts/research_subagent.md) | Previously examined examples of substantive role-specific instructions, delegation boundaries and worked guidance. Mutable reference implementation; resolve a specific revision before relying on exact wording or sizes. |

## D. Prompt design, demonstrations, API instruction and context

| ID | Primary source | Relevance to WellPlot |
| --- | --- | --- |
| CTX-01 | Brown et al., [Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165), 2020 | In-context demonstrations; already referenced in S03. |
| CTX-02 | Agarwal et al., [Many-Shot In-Context Learning](https://arxiv.org/abs/2404.11018), 2024 | More demonstrations can help on some tasks; no universal optimum example count. |
| CTX-03 | Qi et al., [AGENTIF: Benchmarking Instruction Following of Large Language Models in Agentic Scenarios](https://arxiv.org/abs/2505.16944), 2025 | Complex and lengthy agent instructions can be difficult to follow. Measure actual compliance; no hard prompt-length cutoff follows from this benchmark. |
| CTX-04 | Liu et al., [Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172), 2023 | Position-dependent context use. An advertised context window is not proof of reliable recall; already referenced in S03. |
| CTX-05 | Hsieh et al., [RULER: What's the Real Context Size of Your Long-Context Language Models?](https://arxiv.org/abs/2404.06654), 2024 | Effective context capability can differ from nominal length. Qualify full plot JSON, inventories and conversation together on representative workloads. |
| CTX-06 | Patil et al., [Gorilla: Large Language Model Connected with Massive APIs](https://arxiv.org/abs/2305.15334), 2023; [project](https://gorilla.cs.berkeley.edu/) | API documentation and accurate tool use matter; training/retrieval results do not prove a particular prompting-only method. |
| CTX-07 | Qin et al., [ToolLLM](https://arxiv.org/abs/2307.16789), 2023 | Tool descriptions, selection and multi-step tool use. Worker manuals should explain actual permitted APIs, preconditions, arguments, outcomes and errors. |
| CTX-08 | OpenHands, [documentation repository](https://github.com/OpenHands/docs), [software-agent SDK](https://github.com/OpenHands/software-agent-sdk) | Reference implementations of role/task-specific skill instructions. Inspiration only; no new prompt-management or skill framework proposed. |

Earlier discussion proposed approximate planner/report/section total context ranges of 4–9K, 4–10K and 7–17K tokens, respectively. These were engineering estimates, not measured requirements or literature-derived thresholds. They predate the proposal to share full conversation and canonical document context; measure actual payloads and runtime token counts before setting a budget. Distinguish stable instruction text, examples, tool schemas, source metadata, document JSON, transcript, feedback and output allowance. Caching observations are descriptive, not causal performance guarantees.

## E. Scientific tools, environment feedback and recovery

| ID | Primary source | Relevance to WellPlot |
| --- | --- | --- |
| ACT-01 | Yao et al., [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629), ICLR 2023 | Interleave decisions and environmental observations; recover using verified feedback. No need to expose chain-of-thought or permit arbitrary actions. |
| ACT-02 | Yang et al., [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://arxiv.org/abs/2405.15793), NeurIPS 2024; see [v2](https://arxiv.org/abs/2405.15793v2) for historical instruction/interface comparisons | Tool/interface design, worked demonstrations and feedback matter. Ablations are specific to SWE-agent's evaluated configuration, not universal worker prompt sizes. |
| ACT-03 | Boiko et al., [Autonomous chemical research with large language models (Coscientist)](https://doi.org/10.1038/s41586-023-06792-0), Nature 2023 | Scientific planning plus specialist tools, documentation and experimental observations. Adapt the scientific investigation boundary; no unrestricted execution. |
| ACT-04 | Bran et al., [Augmenting large language models with chemistry tools (ChemCrow)](https://doi.org/10.1038/s42256-024-00832-8), Nature Machine Intelligence 2024; [open text](https://pmc.ncbi.nlm.nih.gov/articles/PMC11116106/) | Expert-built scientific tools improve access to domain operations; retain canonical scientific API and verification authority. |
| ACT-05 | Wang et al., [Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291), 2023 | Environment feedback, execution errors and self-verification. Relevant as a recovery example, not authority for a separate executable skill library. |
| ACT-06 | Xia et al., [Agentless: Demystifying LLM-based Software Engineering Agents](https://arxiv.org/abs/2407.01489), 2024 | Counterpoint to elaborate orchestration: simple staged approaches can be effective. Prefer minimal justified complexity and test before adding machinery. |

## F. Evaluation, reliability and multi-agent failure analysis

| ID | Primary source | Relevance to WellPlot |
| --- | --- | --- |
| EVAL-01 | Yao et al., [τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains](https://arxiv.org/abs/2406.12045), 2024 | Dynamic dialogue, tool use, domain policies and final-state correctness; repeated-trial reliability. Evaluate actual saved scientific artifacts and conversation, not merely schema-valid planner output. |
| EVAL-02 | Barres et al., [τ²-Bench: Evaluating Conversational Agents in a Dual-Control Environment](https://arxiv.org/abs/2506.07982), 2025; [proceedings](https://proceedings.mlr.press/v306/barres26a.html) | User and agent both modify shared state. Especially relevant to manual plot edits between turns, coordination and stale-state handling. |
| EVAL-03 | Cemri et al., [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657), NeurIPS 2025; [proceedings](https://proceedings.nips.cc/paper_files/paper/2025/hash/b1041e52d3be19f0a9bc491657488e4a-Abstract-Datasets_and_Benchmarks_Track.html) | MAST taxonomy: specification/design, inter-agent alignment, verification/termination failures. More agents do not automatically improve reliability. |

## Reading-to-experiment crosswalk

| Existing milestone | Particularly relevant references | What still requires WellPlot evidence |
| --- | --- | --- |
| S03 planner | PLN-01–09, CTX-01–05, VIS-02/03 | Complete intent coverage, delegation, dependencies and contextual grounding under the revised responsibility contract. Preserve prior H1a/H1b results. |
| S04 specialist choice | CTX-06–08, ACT-01–04 | Actual worker inspection, existing-state assessment, lawful action selection and grounded blockers. |
| S05 completion | ACT-01–06, EVAL-03 | Refreshed state, bounded recovery, verified dependency closure and safe partial publication. |
| Response and conversational milestones | VIS-01–05, DIA-01/02, EVAL-01/02 | Dedicated response-role factual accuracy, clarification, informational requests, full dialogue context and safe resumption. Placement/budgets remain governed by the active design. |
| S06 and final qualification | ACT-06, EVAL-01–03, CTX-03–05 | Decide minimal architecture from evidence; real LAS/DLIS correctness, preservation, publication, reload/render, and adapter parity. |

Do not use literature results as substitutes for measured WellPlot outcomes, infer causal improvement from uncontrolled changes, or convert these reading notes into new implementation gates. No parallel engine, workflow, source parser, memory system or prompt framework is implied. Retain one canonical authoring path and use existing APIs and inspected state.

Reference-recovery note: this collection consolidates the two recent research discussions and links the older repository record. Core identifiers and many primary landing pages were rechecked on 2026-11-25; not every full text or mutable code revision was reopened during this bibliography-only pass. Nature publisher pages were inaccessible during the recheck; their DOI links and the open ChemCrow text are retained. Additional historical references can be added here without editing frozen experiment artifacts.

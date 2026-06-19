# Architecture Decision Record — Claim Verification Pipeline

Scope: HackerRank Orchestrate (June26 edition). Each entry follows Context → Alternatives Considered → Decision → Tradeoffs → Risks Accepted → Why Alternatives Were Rejected. Status reflects the state at submission time, not an aspiration.

---

## ADR-001: Agentic Perception, Deterministic Disposition

**Status:** Accepted

**Context.** The system must decide `claim_status` (supported / contradicted / not_enough_information) from a text claim plus 1–3 images, with risk of prompt injection in the claim text and a known evaluation penalty for justification text that contradicts the decided status.

**Alternatives considered.**
1. Single ReAct-style agent that perceives *and* decides in one loop.
2. Fixed deterministic pipeline (parse → caption → fixed rules), no adaptive reasoning.
3. Multi-agent committee (claim agent + vision agent + risk agent + arbitrator).
4. Two-pass grounding-verified agent (draft, then re-inspect cited images).

**Decision.** Genuine model-driven perception (claim understanding + per-image vision reasoning) feeds a separate, non-LLM rule layer that owns the final disposition. The model is never asked to be both the witness and the judge in the same call.

**Tradeoffs.** Costs more design time upfront than option 1 or 2. Buys back that cost through testability: the rule layer can be unit-tested against labeled data with zero LLM calls, and the model's authority is scoped to perception only, which is the failure mode the evaluation's contradiction-cap rule specifically punishes.

**Risks accepted.** The arbitration layer is only as complete as the edge cases discovered before submission. A claim pattern outside the documented set fails uniformly rather than being caught by chance the way redundant agents might. Tracked in `known_limitations.md`.

**Why alternatives rejected.** Option 1 puts free-text disposition authorship in the same call as perception — undefended against "show me the line that decides the status" in review, and structurally exposed to claim-text injection reaching the decision. Option 2 is safe on consistency but has no mechanism to adapt to compound claims or identity mismatches — a fixed-stage pipeline with no adaptive branching reads as "rules with LLM calls bolted on," not an agent. Option 3's design is sound but its realistic solo-build completion probability inside a 24-hour window is low enough that the expected outcome is worse than a simpler design executed completely. Option 4's second pass shares failure modes with the first — re-asking the same kind of question doesn't change what the model is vulnerable to, and it does nothing for the history-override pattern, which doesn't involve grounding at all.

---

## ADR-002: Deterministic Disposition Owns claim_status, severity, risk_flags

**Status:** Accepted

**Context.** `claim_status`, `issue_type`, `object_part`, `severity`, `valid_image`, and `risk_flags` must be internally consistent on every row, including the not_enough_information / unknown pairing and the none-severity / contradicted pairing.

**Decision.** A pure rule-evaluation function consumes only typed objects from upstream layers (claim understanding, image aggregation, evidence validation, history risk) and emits the locked verdict. No layer downstream of it can alter these fields; no LLM call participates in this decision.

**Tradeoffs.** Every edge case this layer doesn't explicitly handle fails the same way every time, rather than failing differently across retries. That's treated as acceptable — uniform, debuggable failure beats inconsistent failure for a system being read by a code reviewer.

**Risks accepted.** The two-gate structure (evidence sufficiency, then content match) is derived from a 20-row labeled sample with perfect consistency in that sample. Perfect consistency at n=20 is encouraging, not proof the rule generalizes to every hidden-test pattern.

**Why alternatives rejected.** Letting the perception model self-report a disposition (with the rule layer as a "sanity check" rather than the decision-maker) reintroduces the exact authorship ambiguity ADR-001 exists to remove.

---

## ADR-003: User History Is Structurally Firewalled From Evidence

**Status:** Accepted

**Context.** A claim from a user with a flagged history must not be auto-contradicted on history alone; a claim from a clean-history user must not be auto-supported on a partial visual match.

**Decision.** The component that reads `user_history.csv` receives only `user_id` as input. It has no code path through which claim text or image findings can reach it, and no code path through which its output can directly set `claim_status`.

**Tradeoffs.** This is structurally cheaper than option below, not more expensive — it requires no LLM call at all. The cost is entirely in discipline: it would be easy to collapse this into one prompt with everything in context, which silently destroys the guarantee.

**Risks accepted.** Because the firewall is total, the system cannot detect a fraud pattern that is only visible by cross-referencing history *and* the current claim's content together (e.g., a recurring image-reuse pattern). This is a deliberate scope boundary — see `known_limitations.md`.

**Why alternatives rejected.** "Weigh history appropriately" as a prompt instruction inside the main judgment call is the prompted-hope pattern this decision specifically avoids — it is not verifiable from the code, and a single context window gives the model every opportunity to let history leak into a content judgment, observably or not.

---

## ADR-004: Justification Generation Is Separated From Disposition, and Independently Audited

**Status:** Accepted

**Context.** The evaluation explicitly caps the score on a row where a correct decision carries a justification that is empty, generic, or contradicts the decision.

**Decision.** A "constrained writer" call receives the already-locked disposition object and produces justification text referencing only facts present in that object — it cannot introduce a new claim or outcome. A second, non-generative check audits the written text against the locked object before the row is written. On failure: one bounded re-generation, then a deterministic template built directly from field values, which is guaranteed to pass.

**Tradeoffs.** Adds a fourth and fifth model-call/check stage. In exchange, removes the single most commonly cited execution failure pattern in this competition: a model that decides and explains in the same breath occasionally explains something other than what it decided.

**Risks accepted.** The template fallback guarantees the row is never blocked, but a row that hits the fallback ships with a flatter, value-only justification. If the fallback rate is high and unreviewed, this looks like quality the team never checked, not quality the team chose. Mitigated by a manual fallback-log review before submission (see `pre_submission_checklist.md`).

**Why alternatives rejected.** Letting one call both decide and explain reintroduces the exact authorship-blending problem ADR-001/002 exist to prevent — confirmed in this competition's own published evaluation guidance as a recurring, specifically penalized pattern.

---

## ADR-005: No RAG / Vector Retrieval Over Reference Data

**Status:** Accepted

**Context.** `evidence_requirements.csv` and `user_history.csv` are small (11 and 47 rows respectively) and need exact, not semantic, lookup.

**Decision.** Both load into in-memory dictionaries at process start. No embeddings, no vector store.

**Tradeoffs.** None of substance at this data scale. The decision becomes wrong only if either reference table grows by an order of magnitude or needs semantic (not exact-key) matching — neither is true here.

**Risks accepted.** None material. Flagged only because "why no RAG" is a near-certain interview question, and the honest answer is that RAG would have been over-engineering, not a missed opportunity.

**Why alternatives rejected.** A vector store adds a dependency and a failure surface to solve a problem a dictionary already solves exactly, for a dataset where the embedding step would cost more than the lookups it replaces.

---

## ADR-006: No Agent Orchestration Framework

**Status:** Accepted

**Context.** The pipeline is a fixed eight-stage sequence over one claim row at a time — no dynamic re-planning, no shared long-term memory across rows.

**Decision.** A thin, hand-written orchestrator sequences the stages. No LangChain, CrewAI, or similar framework.

**Tradeoffs.** Loses out-of-the-box retry/memory/tool-routing abstractions. Gains a codebase where every decision point is a named function a reviewer can point to directly, instead of "the framework handled it" — which is a materially weaker answer under the architecture-ownership criterion this competition explicitly grades.

**Risks accepted.** Hand-written retry/backoff logic is more code than importing a library's. Scoped narrowly (three named retry classes, see `security_and_robustness.md`) to keep that surface small.

**Why alternatives rejected.** None of the dynamic capabilities these frameworks are built for (multi-step planning, long-horizon memory, tool discovery) are exercised by this problem's shape.

---

## ADR-007: No Async / Parallel Image Processing in v1

**Status:** Accepted, flagged as the first post-submission optimization

**Context.** Up to 3 images per row, ~111 images across the full labeled-plus-test corpus.

**Decision.** Images are processed sequentially within a row in this submission.

**Tradeoffs.** Slower wall-clock time for the full batch run. At this volume, the time saved by parallelizing does not offset the complexity added (result ordering, partial-failure handling, burst rate-limit risk) inside a 24-hour solo build.

**Risks accepted.** If the hidden test set has a meaningfully larger image count per row than observed in the sample, this tradeoff degrades. No evidence currently supports that.

**Why alternatives rejected.** Not rejected outright — deferred. Named explicitly in `evaluation_strategy.md` as a flagged next step, not silently omitted.

---

## ADR-008: No Persistent Database

**Status:** Accepted

**Context.** Input and output are both CSV; the entire reference dataset fits comfortably in memory.

**Decision.** CSV in, CSV out, append-per-row writes for crash safety. No SQLite, no managed database.

**Tradeoffs.** No query language, no concurrent-write safety beyond what append-mode already provides — irrelevant at a 64-row batch-job scale processed by a single process.

**Risks accepted.** None material at this scale.

**Why alternatives rejected.** A database adds setup and connection-management overhead disproportionate to a job whose entire working set is two small lookup tables and a row-at-a-time write target.

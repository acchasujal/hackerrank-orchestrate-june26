# Implementation Order

## Critical Path

`schemas` → `llm_client` → **per-image vision analysis** → multi-image aggregation → disposition → justification → consistency check → orchestrator → full corpus run → evaluation report.

Per-image vision analysis is the bottleneck — the slowest, costliest, most prompt-fragile single component. Everything downstream of it waits on it; everything upstream of it (the deterministic layers) can be built and validated independently of it.

## Build Order

| Order | Component | Build Time | Depends On | Earliest Validation Point |
|---|---|---|---|---|
| 1 | Schemas | 30–45 min | None | Diff the output row schema against the spec's column contract |
| 2 | I/O utilities (incremental read/write) | 30 min | Schemas | Round-trip dry run on the labeled sample |
| 3 | LLM client (calls, retry, cache, cost log) | 45–60 min | Schemas | One real call logged end-to-end |
| 4 | History risk component | 15–20 min | Schemas, I/O | Run against the full history table, diff known flags |
| 5 | Evidence validation component | 20–30 min | Schemas, I/O | Run against sample rows, confirm both not-enough-information cases match |
| 6 | **Disposition rule table + unit tests** | 45–60 min | Schemas only (hand-built test fixtures) | **20/20 sample rows pass before any model call exists** |
| 7 | Multi-image aggregation | 30–45 min | Schemas only (synthetic fixtures) | Unit test on 2–3 hand-built multi-image scenarios |
| 8 | Claim-understanding (model call) | 60–90 min | Schemas, LLM client | Run against all 20 sample claim texts, compare extracted fields |
| 9 | Per-image vision analysis (model call) | 120–150 min | Schemas, LLM client | Run against a hand-picked set covering clear / blurry / non-original / multilingual-context / compound cases |
| 10 | Justification writer + template fallback | 45–60 min | Disposition output shape | Template-only path testable with zero model calls |
| 11 | Consistency check | 30 min | Justification + disposition shapes | Deliberately inject one mismatch, confirm catch → regenerate → fallback |
| 12 | Orchestrator | 45–60 min | All layers, skeleton-level | First single row through all stages |
| 13 | Evaluation harness | 60–90 min | Orchestrator, sample set | First accuracy table on the sample |
| 14 | Evaluation report (generated) | 30–45 min | Call logs populated | First auto-generated draft |
| 15 | Pre-submission checklist pass | 45–60 min | Full sample run complete | Sign-off before the full corpus run |
| 16 | Full corpus run | 1–2 hr wall-clock | Everything above | First rows of the output file look sane |

## MVP Definition

An end-to-end run on the labeled sample producing a schema-valid output file, with the disposition rule table verified against all 20 labels, the injection-quarantine schema in place (detection heuristic strength not yet required), and incremental write confirmed working.

## Submission-Ready Definition

MVP, plus: full corpus run completed and written; `code/README.md` complete; `evaluation_report.md` generated from real logs; pre-submission checklist complete; at least one manual fallback-log review performed.

## Top-10 Definition

Submission-ready, plus: the highest-ROI fixes from the risk register applied (disposition unit tests, shared image-ID extraction, the three documented-limitation write-ups, a genuinely differentiated second evaluation configuration); interview answers drafted for the highest-probability questions in `interview_prep.md` (kept out of the submitted repository — see that document's note).

## Deferred Work (named explicitly, not silently dropped)

- Async/parallel image processing (ADR-007) — first post-submission optimization if image volume grows.
- Enum fuzzy-matching beyond exact-match validation — build only if the sample dry run actually shows near-miss enum drift.
- A broader (3–4 point) evaluation-configuration sweep beyond the required two-configuration comparison.
- Exhaustive multilingual stress-testing beyond one Spanish and one Chinese-English spot check.

## Last-Phase Plan (final hours before deadline)

1. Full corpus run, with buffer for retries.
2. Manual review of every fallback-triggered row.
3. Manual spot-check of the severity distribution against the sample's known distribution.
4. Final header/contract validation re-run.
5. Secret-string grep.
6. Finalize `code/README.md` and `evaluation_report.md`.
7. Submit with real time buffer remaining.

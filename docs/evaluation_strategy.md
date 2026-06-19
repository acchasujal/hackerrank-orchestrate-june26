# Evaluation Strategy

## Purpose

Establish, before the full test-set run, that the pipeline's decision logic is correct on data with known answers — decoupling "is the logic right" from "is the extraction good enough," since these fail independently and a single end-to-end pass/fail number conflates them.

## Sample Evaluation Process

1. Run the full pipeline against `sample_claims.csv` (20 labeled rows) under each evaluation configuration.
2. For the deterministic layers (evidence validation, history risk, disposition), validate separately against hand-constructed structured inputs derived directly from the 20 labels — this can run, and did run, before any model call existed, and is the strongest correctness evidence in the system because it has no extraction-quality noise in it.
3. For the model-driven layers (claim understanding, per-image analysis), compare extracted structured fields against the labels manually, since no field-level extraction ground truth is provided beyond the final disposition.
4. Run the full corpus (`claims.csv`, unlabeled) once, using the configuration selected from step 1–3.

## Metrics

| Metric | Field(s) | Method |
|---|---|---|
| Exact-match accuracy | `claim_status`, `issue_type`, `object_part`, `severity`, `evidence_standard_met`, `valid_image` | Direct comparison against the 20 labels |
| Confusion matrix | `claim_status` (3-class) | Fully enumerable at n=20; informative about error *direction*, not a statistically robust accuracy estimate at this sample size |
| Set-overlap F1 | `supporting_image_ids`, `risk_flags` | Order-independent, partial credit for near-misses |

## Error Analysis

Every disagreement between the pipeline's output and a label on the sample set is categorized into one of:
- Extraction error (claim-understanding or per-image layer produced the wrong structured fact)
- Aggregation error (correct per-image facts, wrong merge across images)
- Rule error (correct structured inputs, wrong disposition-table branch)
- Label ambiguity (the case is genuinely underspecified even on manual review)

This categorization, not the raw accuracy number, is what should change the system during the build — a rule error is a code bug; a label-ambiguity case is a limitation to document, not a bug to chase.

## Cost Tracking

Every model call is logged with input/output token counts, latency, and a cached/uncached flag. Per-row and per-batch cost is computed directly from these logs, not estimated. Total call volume for the full sample-plus-test corpus is in the low hundreds of calls — small enough that no batching infrastructure is needed to stay within standard provider rate limits, a conclusion that is checked against the real provider limit once before the full run rather than assumed.

## Latency Tracking

Per-call latency is logged alongside cost. Per-row wall-clock time is the sum of its sequential model calls (no parallelization in this submission — see ADR-007); the full-batch wall-clock estimate is derived from this, not guessed.

## Configuration Comparison Methodology

Two configurations are run against the sample set and compared on the metrics above. The two configurations differ on one real strategic axis (e.g., the evidence-sufficiency threshold, or perception-prompt strictness) — not merely a model-tier swap — so the comparison produces an actual accuracy/cost or accuracy/strictness tradeoff finding rather than a cosmetic one.

## What Success Means

- Every row in the final `output.csv` has a value in every required column, with no internal contradiction (severity/status pairing rules hold, `valid_image` and `claim_status` are independently computed).
- The disposition layer's logic matches all 20 sample labels when fed the labels' own structured facts directly (i.e., the rule table itself is provably correct, independent of extraction quality).
- Known gaps are named in `known_limitations.md`, not silently absent from the output.

## What Failure Means

- A row with an internal contradiction in the output (e.g., `severity=none` paired with `claim_status=supported`).
- A disposition-table rule that disagrees with a labeled sample row when given that row's own correct structured facts — this is a logic bug, not an acceptable edge case.
- A justification that doesn't reference any fact in the locked disposition object.

## How Regressions Are Detected

The 20-row sample evaluation is re-run after any change to the disposition rule table, the evidence-validation thresholds, or the justification-writer prompt. A regression is any sample row that previously matched its label and no longer does. This is a small, fast, deterministic check specifically because the disposition layer requires no model call to validate — it is the cheapest and fastest regression signal in the system, and is run before every meaningful code change, not just once at the end.

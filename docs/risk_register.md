# Risk Register — Claim Verification Pipeline

Ratings are ordinal (High/Medium/Low), assigned by judgment against labeled-data evidence where it exists. They are not derived from a numeric formula — none of the three inputs (probability, severity, detection difficulty) are measured quantities, and presenting a multiplied score would imply precision the underlying judgment doesn't have.

**Detection Difficulty** = would this surface on its own (a crash, a failed validation) before submission, or could it ship silently and only be caught by a hidden test or a sharp interview question.

## Top 10 by Expected Leaderboard Impact

Ranked by severity × detection difficulty, not severity alone — a high-severity risk with low detection difficulty (you'll see it immediately) is lower real risk than a medium-severity one that ships silently.

| Rank | ID | One-line | Why it ranks here |
|---|---|---|---|
| 1 | H6 / A4 | `valid_image=False` + `claim_status` interaction generalized from a single labeled example | High detection difficulty — wrong on a row produces no crash, no flag |
| 2 | H19 | `manual_review` can only ever fire from history, never from evidence ambiguity alone | Confirmed structural gap; silent in Output CSV, loud in interview |
| 3 | I8 | Justification fallback always "passes," can mask a real disposition bug | Force-multiplier: raises detection difficulty on every other risk in this table |
| 4 | I7 | No unit tests on the disposition rule table before first full run | Same force-multiplier shape as I8 |
| 5 | H18 | One image can support two compound-claim parts; schema has one `issue_visible` field | Confirmed present in observed data; affects a real subset of rows |
| 6 | I6 | `image_id` extracted inconsistently between layers | Breaks a directly-graded field with no crash signal |
| 7 | I3 | OutputRow column name/order drift from spec | Catastrophic if it ships, but detection difficulty is near-zero if checked |
| 8 | I14 | No incremental write; a crash mid-batch loses the whole run | Low probability, but zero recovery time near the deadline |
| 9 | I10 | Object-specific enums (car/laptop/package) cross-contaminate | Usually throws on validation — moderate, not high, real risk |
| 10 | I20 | `evaluation_report.md` rushed if deferred to the last hour | Zero detection difficulty, but zero time left to fix once detected |

---

## Implementation Risks (I1–I20)

| ID | Description | Severity | Probability | Detection Difficulty | Mitigation | Status |
|---|---|---|---|---|---|---|
| I1 | Injection heuristic misses non-English/indirect manipulation | Medium | Medium | Medium | Log every raw claim regardless of detection outcome; don't rely on detection succeeding | Accepted (logged) |
| I2 | `is_compound` false-positive on restated, not distinct, descriptions | Medium | Medium | Medium | Require two distinct `object_part` values, not just two phrasings, before flagging compound | Mitigated |
| I3 | OutputRow column name/order drift from spec | Critical | Low | Low (if checked) | Validate header against spec string before every write | Mitigated |
| I4 | CSV embedded-quote/delimiter edge cases in claim text | Medium | Low | Low | Use a CSV library with proper quoting; no manual string splitting | Mitigated |
| I5 | Stale module-level cache across sample vs. test dataset paths | High | Low | Medium | Key cache by file path + mtime, not a bare singleton | Mitigated |
| I6 | `image_id` mismatch between aggregation output and actual filenames | High | Medium | High | Single shared extraction function used by every layer that touches an image ID | Mitigated |
| I7 | No unit tests on disposition rule branches | High | High | High | Minimum one test per gate branch against all 20 sample rows, before first full run | Mitigated |
| I8 | Justification consistency fallback always "passes" | High | Medium | High | Log every fallback trigger separately; manual review before submission | Mitigated |
| I9 | Secret/API key hardcoded during fast iteration | Medium | Medium | Low | Grep for literal key strings as a pre-submission step | Mitigated |
| I10 | Object-specific enum cross-contamination | High | Medium | Low | Three separate enum dictionaries, never one shared filtered list | Mitigated |
| I11 | Image path join bugs across sample/ vs. test/ directories | Medium | Medium | Low | Resolve paths from one config-driven dataset root; test both directories explicitly | Mitigated |
| I12 | Sequential processing + 3-tier retries → real runtime risk | Medium | Medium | Low | Time a 5-row dry run early, not at hour 20 | Mitigated |
| I13 | Fixed backoff schedule untested against actual provider RPM | Medium | Medium | Low | Run one real burst test against the live key before the full batch | Mitigated |
| I14 | No incremental write; crash mid-batch loses all output | High | Low | Low (you'd know instantly) | Append-mode write, row by row | Mitigated |
| I15 | Vision model may obey image-embedded instructions before the wrapper reacts | High | Medium | Medium | Stated as a known, partial-coverage limitation, not claimed as solved | Accepted (documented) |
| I16 | Structured-output enum drift ("dented" vs. "dent") | Medium | Medium | Low | Fuzzy-normalize near-miss values before triggering a retry | Mitigated |
| I17 | Throttling parameters chosen without checking the real limit | Medium | Medium | Low | Confirm actual TPM/RPM for the chosen model tier once, before the full run | Mitigated |
| I18 | Two evaluation configs differ only by model swap, not strategy | Medium | Medium | Low | Vary one real strategic choice (e.g., evidence threshold) instead | Mitigated |
| I19 | `code/README.md` deprioritized under time pressure | Medium | Medium | Low | Drafted early, finalized last | Mitigated |
| I20 | `evaluation_report.md` rushed despite logged data existing | High | Medium | Low | Generated programmatically from logs, not hand-written | Mitigated |

## Hidden-Test Risks (H1–H20)

| ID | Description | Severity | Probability | Detection Difficulty | Mitigation | Status |
|---|---|---|---|---|---|---|
| H1 | Second-mentioned compound issue is the verifiable one, not the first | High | Medium | High | Conceded as a named limitation; tiebreak rule stated explicitly | Accepted (documented) |
| H2 | One compound pair supported, one contradicted; no partial-credit value exists | Medium | Medium | Medium | Conservative default to `contradicted` overall, stated as a deliberate tradeoff | Accepted (documented) |
| H3 | Lighting/white-balance variance triggers a false cross-image conflict | Medium | Medium | Medium | Require a clear identity mismatch, not ambiguous lighting, to fire the flag | Mitigated |
| H4 | Subtle authority-framed injection ("supervisor already confirmed...") | Medium | Medium | Medium | Detect intent class, not literal phrases | Accepted (documented, partial coverage) |
| H5 | `wrong_object_part` flag has zero precedent in labeled data | Medium | Medium | Medium | Documented as untested rather than claimed as calibrated | Accepted (documented) |
| H6 | `valid_image=False` + `claim_status` still required, confirmed in one sample row | Critical | Medium | High | `valid_image` computed independently; never gates `claim_status` | Mitigated |
| H7 | 3+ language mixing within one conversation | Low | Low | Medium | One synthetic 3-language test case, not a structural fix | Mitigated (spot-checked) |
| H8 | Image count exceeds the observed max of 3 | Low | Low | Low | No hardcoded N=3 assumption anywhere in code or report | Mitigated |
| H9 | Explicit claim retraction/correction misread as a genuine compound claim | Medium | Medium | Medium | Retraction language ("actually," "I was wrong") checked before compound logic | Mitigated |
| H10 | Severity boundary calibration (low/medium/high) under perception framing | Medium | High | Medium | Spot-checked against sample's severity distribution before submission | Accepted (documented) |
| H11 | Package claim mixing exterior and interior language | Medium | Medium | Medium | Weight the customer's final explicit statement | Mitigated |
| H12 | History text hints at an image-reuse fraud pattern; no detection mechanism exists | High | Low | Low (once known) | Explicitly out of scope — see ADR-003 | Accepted (out of scope) |
| H13 | Authenticity probe row is a pure, unverifiable visual judgment | Medium | Medium | Medium | Flagged as a known confidence limitation, not a solved capability | Accepted (documented) |
| H14 | Clear but irrelevant decoy image, no clean risk flag covers it | Low | Medium | Low | Per-image vs. per-row `valid_image` semantics defined explicitly | Mitigated |
| H15 | Sarcastic/venting customer language false-flagged as injection | Medium | Medium | Medium | Require imperative-to-system phrasing, not general negativity, to flag | Mitigated |
| H16 | Numeric/structured-data adversarial trap | Low | Low | Low | No current evidence this pattern exists in this dataset | Monitoring |
| H17 | `user_id` missing from `user_history.csv` | Medium | Low | Low (crash signal) | Explicit `Optional[HistoryRisk]` default branch | Mitigated |
| H18 | One image relevant to two compound-claim parts | High | Medium | Medium | Documented schema gap; affects an estimated minority of compound rows | Accepted (documented) |
| H19 | `manual_review` only ever fires from history, never from evidence ambiguity alone | High | High | High | Documented as a deliberate scope boundary, not silently absent | Accepted (documented) |
| H20 | `claim_object` itself (not just `object_part`) contradicted by images | Medium | Low | Medium | No top-level object cross-check currently exists | Accepted (out of scope) |

## Unvalidated Assumptions (A1–A11)

| ID | Assumption | Severity if wrong | Probability it's wrong | Mitigation |
|---|---|---|---|---|
| A1 | `wrong_object_part` has a derivable rule | Medium | Medium | Documented as untested |
| A2 | Max 3 images holds for any hidden/live batch | Low | Low | No N=3 hardcoded anywhere |
| A3 | Every `user_id` in the claim set exists in `user_history.csv` | Medium | Low | Explicit fallback branch (H17) |
| A4 | `valid_image=False` never blocks `claim_status` (one labeled example) | High | Medium | Treated as provisional; logged if it recurs differently |
| A5 | Mention order is a meaningful compound tiebreak | Medium | Medium | Conceded in interview prep, zero precedent to validate against |
| A6 | Conflicting compound outcomes resolving to `contradicted` is correct | Medium | Medium | Same — zero precedent |
| A7 | Severity boundaries are reliably model-calibrated | Medium | High | Spot-checked, not claimed as solved |
| A8 | Image authenticity is detectable by the chosen vision model at all | Medium | Medium | No ground truth exists to confirm; stated as unverified |
| A9 | Two model-swap configs satisfy the "strategy comparison" requirement | Medium | Medium | Configs differ on a real strategic axis, not just model ID |
| A10 | Current RPM/TPM headroom supports the no-parallelization decision (ADR-007) | Medium | Medium | Verified against the real provider limit once, before the full run |
| A11 | Reusing `manual_review_required` covers the chat-injection enum gap | Medium | Medium | Named as a gap, not presented as a solution, in the report |

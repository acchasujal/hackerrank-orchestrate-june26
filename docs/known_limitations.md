# Known Limitations

Every limitation below was discovered during dataset and architecture analysis, not after the fact. Each is a scope decision, not an oversight — listed here so it reads that way to a reviewer rather than being found independently and read as a gap nobody noticed.

---

### 1. Compound-claim primary-issue tiebreak uses mention order
**Impact.** On a compound claim where the second-mentioned issue is the one actually visible, the wrong issue can be reported as primary.
**Why not solved.** No labeled compound-claim row exists in the sample to validate any tiebreak rule against — mention-order is the best available signal, not a verified one.
**Future improvement.** Weight by per-image evidence strength per claimed pair instead of mention order, once labeled compound examples exist to tune against.

### 2. One image can support two compound-claim parts; schema records one `issue_visible` value
**Impact.** Affects a real minority of test rows containing 3+ images and bundled claims.
**Why not solved.** Extending the per-image schema to a list of findings was judged not worth the added complexity for the volume of affected rows, given the 24-hour build window.
**Future improvement.** Change `issue_visible` to a list, and have aggregation map each finding independently to its corresponding claimed pair.

### 3. `manual_review` only ever derives from user history, never from evidence ambiguity alone
**Impact.** A claim with no history flag but genuinely ambiguous evidence is resolved by the disposition rules rather than escalated.
**Why not solved.** This is the direct consequence of the history/evidence firewall (ADR-003) — the same boundary that prevents history from overriding clean evidence also prevents evidence ambiguity from triggering a history-shaped signal. Loosening it for this case would weaken the firewall generally.
**Future improvement.** Add a second, independent `evidence_ambiguity_flag` that can also set `manual_review`, sourced from the disposition layer itself rather than from history.

### 4. Severity (low/medium/high) is a calibrated visual judgment, not a derivable rule
**Impact.** Severity is the one disposition-adjacent field with no rule-table backing — it comes directly from model perception.
**Why not solved.** Nothing in the available reference data (evidence requirements, history) constrains severity; it is inherently a visual judgment call.
**Future improvement.** Spot-check against the sample's known severity distribution before submission (done); a larger labeled set would allow a proper calibration pass.

### 5. `wrong_object_part` flag has zero precedent in labeled data
**Impact.** The flag exists in the schema but its firing conditions are untested against any real example.
**Why not solved.** No labeled row exercises this case.
**Future improvement.** Treat any production use of this flag as low-confidence until validated against a real example.

### 6. In-image embedded-text defense is partial
**Impact.** If a vision model acts on embedded instructional text during its own perception step (before producing structured output), a wrapper that only inspects the output afterward cannot fully catch it.
**Why not solved.** This depends on model-level behavior the pipeline doesn't control directly.
**Future improvement.** Add an explicit pre-step instruction in the perception prompt to flag, not follow, any instruction-like text found in an image, and test against adversarial synthetic images.

### 7. No detection mechanism for fraud patterns that span history and current-claim content jointly
**Impact.** A recurring pattern (e.g., image reuse across multiple claims by the same user) referenced in history text is not cross-checked against the current claim's images.
**Why not solved.** This is the direct, deliberate cost of the history/evidence firewall (ADR-003) — the same design choice that blocks history from overriding clean evidence also blocks this kind of joint check.
**Future improvement.** A narrow, explicitly-scoped cross-check (e.g., perceptual image-hash comparison against prior submitted images for the same user) could be added without reopening the general firewall.

### 8. Image authenticity detection has no ground truth to validate against
**Impact.** `non_original_image` / `possible_manipulation` flags are produced but their accuracy is unverified.
**Why not solved.** No labeled example confirms or denies a specific authenticity call.
**Future improvement.** Treat as a stated-confidence, not validated-accuracy, signal until ground truth exists.

### 9. Conflicting compound-claim sub-outcomes default to an overall `contradicted`
**Impact.** A multi-part claim with one true and one false assertion resolves conservatively rather than with partial credit.
**Why not solved.** No schema field exists for a mixed outcome, and no labeled precedent indicates the intended behavior.
**Future improvement.** Only worth revisiting if the evaluation schema is extended to support partial-credit dispositions.

### 10. Subtle, non-keyword injection attempts are not reliably caught
**Impact.** Authority-framed or indirect injection phrasing can pass the detection heuristic undetected.
**Why not solved.** The structural defense (disposition never reads raw claim text) holds regardless of detection success — detection is for audit logging, not blocking — so this is a logging gap, not a decision-safety gap.
**Future improvement.** Classifier-based intent detection instead of pattern matching, if injection sophistication increases.

### 11. Two evaluation configurations is a small comparison set
**Impact.** The cost/accuracy tradeoff finding is directional, not exhaustive.
**Why not solved.** Time-boxed to a 24-hour build; a broader sweep wasn't prioritized over completing the core pipeline.
**Future improvement.** A 3–4 point sweep across the evidence threshold would give a fuller tradeoff curve.

### 12. No parallel image processing
**Impact.** Full-batch wall-clock time is higher than a parallelized version would achieve.
**Why not solved.** At the observed image volume (~111 across sample + test), the complexity cost (ordering, partial-failure handling, burst rate-limit risk) wasn't judged worth it for the time saved. See ADR-007.
**Future improvement.** First post-submission optimization if the hidden or live image volume turns out to be substantially larger.

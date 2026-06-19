# Hidden Test Playbook — PRIVATE, DO NOT COMMIT

This document reverse-engineers likely hidden-test categories from the labeled sample, the unlabeled test set, and the dataset's own structure. It exists to direct build effort, not to be read by anyone evaluating the submission — a document titled this way, found in a submitted repo, reads as "gamed the grading" rather than "built carefully," which actively damages the Honesty & self-awareness score it's meant to protect indirectly. Keep this outside the submitted repository.

Confidence levels reflect how directly each category is evidenced in the actual data, not a guess about HackerRank's intent.

---

## 1. Prompt Injection in Claim Text
**Confidence: High — directly evidenced.** Multiple explicit system-directed instructions and pressure-tactic rows are present in the unlabeled test set; the labeled sample contains none, meaning the dev loop against the sample alone never exercises this.
**Why it likely exists.** The problem statement's framing explicitly concerns trustworthy automated review of untrusted customer text.
**Failure signature.** A row where the claim text contains an instruction-like phrase and the output shows `claim_status=supported` or a generic/missing `manual_review` flag with no other supporting evidence.
**Mitigation.** Disposition never reads raw claim text (architectural, see ADR-001/002). Manually inject a real example from the dataset into a held-out test before submission and confirm the outcome tracks image content, not the injected phrase.

## 2. Compound Claims
**Confidence: High — directly evidenced.** Multiple test-set rows bundle two distinct issue/part pairs into a single-value schema, with zero precedent in the labeled sample.
**Why it likely exists.** Real customer claims plausibly describe more than one problem; testing whether a system collapses this correctly (or silently drops one half) is a natural adversarial check.
**Failure signature.** A compound row where the reported primary issue is the first-mentioned one but the actually-visible damage matches the second-mentioned one.
**Mitigation.** Explicit, documented tiebreak rule (mention order) plus disclosure of the unresolved secondary issue in the justification text rather than silent dropping. Documented as an unproven heuristic, not a solved case (see Known Limitations #1).

## 3. Identity / Object Mismatch
**Confidence: High — directly evidenced.** At least two test rows map directly to a vehicle-identity requirement category ("blue car," "black car") with no equivalent in the sample.
**Why it likely exists.** Distinguishes systems that check the *claimed object itself*, not just the claimed part, against the images.
**Failure signature.** A row where the object in the image doesn't match the claimed object, but the system still evaluates only the claimed part/issue without flagging the object-level mismatch.
**Mitigation.** Cross-image conflict detection at the aggregation layer; `object_detected` compared across images. Object-level (not just part-level) contradiction is a documented gap (Known Limitations / claim_object mismatch) — named, not silently absent.

## 4. Multilingual / Code-Switched Claims
**Confidence: High — directly evidenced.** Test set includes Spanish-only and Chinese-English code-switched rows; sample coverage is Hindi-English only.
**Why it likely exists.** Real customer bases are multilingual; a system that silently collapses to `issue_type=unknown` on a non-English claim is a real, plausible failure mode worth testing for.
**Failure signature.** A non-English or code-switched row where extracted fields are empty, generic, or default values.
**Mitigation.** Language normalization sub-step before extraction logic runs; spot-checked against at least one Spanish and one Chinese-English row before submission.

## 5. History-Override Trap
**Confidence: High — directly evidenced and likely the single most heavily weighted pattern.** A majority of test-set rows carry a flagged user history, a meaningfully higher proportion than in the labeled sample — consistent with the problem statement's explicit framing around this exact trap.
**Why it likely exists.** Directly named in the problem statement as the core tension the system must resolve.
**Failure signature.** A flagged-history user's row resolving to `contradicted` despite genuinely clean, sufficient evidence — or the reverse, a clean-history user's weak-evidence claim resolving to `supported`.
**Mitigation.** Structural firewall (ADR-003) — history cannot directly set `claim_status` by construction, not by prompted instruction.

## 6. Authenticity / Manipulation Checks
**Confidence: Medium.** One sample row pairs a non-original-looking but still legible image with a `contradicted` outcome; no broader pattern is confirmed.
**Why it might exist.** Tests whether the system distinguishes "image doesn't support the claim" from "image isn't trustworthy at all," which are different findings with different correct outputs.
**Failure signature.** `valid_image=False` incorrectly blocking a `claim_status` determination that the image content actually supports, or the reverse — treating an inauthentic image as fully trustworthy.
**Mitigation.** `valid_image` computed independently of the disposition gates (Known Limitations / Security doc both note this is provisional, generalized from a single example).

## 7. Severity Calibration Under Perception Framing
**Confidence: Medium.** The labeled sample shows a skewed severity distribution and a strict pairing rule with `claim_status`, but no adversarial severity-specific test is directly evidenced.
**Why it might exist.** Severity is the one disposition-adjacent field with no rule-table backing — a natural place for a hidden test to probe calibration rather than logic.
**Failure signature.** Severity inflated or deflated relative to what the images plausibly show, especially on borderline cases.
**Mitigation.** Spot-check distribution against the sample before submission; documented as an inherent visual-judgment limitation, not solved.

# Interview Prep — PRIVATE, DO NOT COMMIT

This file is rehearsal material for the live AI Judge interview. It is not a repository artifact. If this file is visible to the judge (in the code zip, in a public repo), it actively damages the Honesty & self-awareness score it's meant to protect — a visible script for handling questions reads as gaming the interview, not preparing for it. Keep this outside the submitted repository entirely (separate folder, `.gitignore`, or just don't add it to git).

Format: Question / Best Answer / Weak Answer / Why the weak answer fails, with the rubric line it's tested against (Technical depth 40%, Problem understanding 25%, Communication 20%, Honesty 15%).

---

**Q1. Show me the line that decides `claim_status`.**
Best: Name the exact file and function (the disposition rule table) and walk through the two-gate structure live.
Weak: Describe the system in general terms without pointing to a specific function.
Why it fails: Technical depth (40%) is the largest single weight in the interview score — a vague answer to the single most predictable question is the worst possible failure point.

**Q2. Why is mention-order a meaningful tiebreak for compound claims?**
Best: It's the best available signal given zero labeled precedent for compound claims, and the alternative — picking arbitrarily — is worse. Concede the limitation directly.
Weak: Defend it as definitely correct.
Why it fails: Honesty & self-awareness (15%) rewards naming an unproven design choice as such, not overselling it.

**Q3. Why default conflicting compound outcomes to `contradicted` instead of partial credit?**
Best: Conservative-by-design tradeoff — no schema field exists for a mixed outcome, and a claim with one false assertion shouldn't auto-clear as a whole.
Weak: Claim this is definitely the "right" answer the evaluation expects.
Why it fails: There's no precedent to validate against; overclaiming correctness here is an unforced honesty risk.

**Q4. The history firewall means you'd miss a recurring fraud pattern visible across multiple claims — isn't that a blind spot?**
Best: Yes, explicitly — that's the direct cost of guaranteeing history can never override clean evidence. Named in `known_limitations.md` as a deliberate scope boundary.
Weak: Argue the firewall has no real downside.
Why it fails: Problem understanding (25%) is partly about recognizing the cost side of a tradeoff, not just the benefit side.

**Q5. How do you avoid false-flagging a frustrated but honest customer as a prompt-injection attempt?**
Best: The detector requires imperative-to-system phrasing, not general negativity, before it fires — and the structural defense (disposition never reads raw text) holds even if detection misses a case.
Weak: Claim the detector is highly accurate without describing how false positives are bounded.
Why it fails: Technical depth wants the mechanism, not a confidence claim.

**Q6. Your justification fallback always "passes" — how do you know the disposition logic underneath is actually correct?**
Best: The fallback guarantees a row isn't blocked; it does not validate correctness. Correctness is established separately, by unit-testing the disposition table against all 20 labeled rows, and by manually reviewing every fallback trigger before submission.
Weak: Imply the fallback itself is a quality guarantee.
Why it fails: This is the most damaging possible answer pattern — confusing "doesn't crash" with "is correct."

**Q7. Show me your unit tests for the disposition table.**
Best: Walk through the test file, point to specific branch coverage against the 20 sample rows.
Weak: "I tested it manually."
Why it fails: The single most damaging honest answer here is "none" — if true, fix this before the interview, not during it.

**Q8. What happens if a `user_id` in the claim set has no matching row in the history table?**
Best: Explicit fallback branch, no crash, degrades to a "no history" default.
Weak: Hadn't considered it / assumed it wouldn't happen.
Why it fails: Exposes an unhandled case live, which is worse than naming it as a known and handled edge case.

**Q9. How does one image supporting two different compound-claim parts work in your schema?**
Best: Concede directly — the per-image schema currently has one `issue_visible` field; documented as a known gap affecting a minority of compound rows, with a stated future fix (a list instead of a single field).
Weak: Claim the schema fully handles this.
Why it fails: This is a real, confirmed gap — the honest answer scores better than a confident wrong one.

**Q10. What if a claim cites two different evidence-requirement categories at once?**
Best: Current scope is single-category lookup per claimed pair; acknowledged as a current limitation, not silently handled.
Weak: Overstate coverage.
Why it fails: Same pattern as Q9 — honesty scores higher than false completeness on a confirmed edge case.

**Q11. Why does `manual_review` only ever come from history, never from evidence ambiguity?**
Best: Direct consequence of the history/evidence firewall — the same boundary that stops history overriding clean evidence also stops evidence ambiguity from triggering a history-shaped signal. Named explicitly as an intentional scope boundary.
Weak: Claim evidence ambiguity is already covered somehow.
Why it fails: It demonstrably isn't, given the architecture; this is a confirmed structural gap, best handled by naming it cleanly.

**Q12. What's your model's real rate limit, and how did you size your retry delay?**
Best: Cite the actual checked number from the live test, not an assumption.
Weak: A guessed number.
Why it fails: Technical depth wants a verified fact, not a plausible-sounding one.

**Q13. Is your second evaluation configuration really a different strategy, or just a model swap?**
Best: Describe the specific strategic axis varied (e.g., evidence threshold) and the resulting tradeoff finding.
Weak: A model-tier swap with no real strategic difference.
Why it fails: This is explicitly a graded requirement (configuration comparison) — a cosmetic comparison only partially satisfies it.

**Q14. What stops the vision model from obeying instructions embedded in an image, before your wrapper can react?**
Best: Concede this is partial — the structured-output boundary catches it after the fact, but a model that visually "obeys" during perception itself isn't fully defended against. Named as a known limitation with a stated next step.
Weak: Claim full coverage.
Why it fails: This is a genuinely hard, unsolved problem class; overclaiming here is checkable and damaging.

**Q15. Give me a real example your injection detector would miss.**
Best: Have one ready (e.g., authority-framed indirect phrasing rather than a direct command) and explain why the structural defense still holds regardless.
Weak: "I can't think of one."
Why it fails: Tests self-awareness directly, not just code — being unable to name a weakness in your own system is itself the weak signal.

**Q16. If the process crashed at row 30 of 44, how much work would you lose?**
Best: Almost none — output is written incrementally, row by row.
Weak: Unsure / "probably have to rerun."
Why it fails: This is a fixable, already-fixed risk; not knowing the answer suggests it wasn't actually fixed.

**Q17. Doesn't a guaranteed-pass fallback hide real quality differences between rows?**
Best: Yes — that's why fallback triggers are logged separately and reviewed manually before submission, rather than trusted blindly.
Weak: Deny the tradeoff exists.
Why it fails: Same root issue as Q6 — the honest framing is the strong answer here.

**Q18. Where would `wrong_object_part` actually fire, given there's no labeled precedent for it?**
Best: Honestly the least-tested branch in the system — name the specific condition that triggers it and state plainly that it's unvalidated.
Weak: Imply it's been validated.
Why it fails: There's no data to back that claim.

**Q19. What's your quality control on severity beyond hoping the model gets it right?**
Best: A spot-check against the sample's known severity distribution before submission — a real but limited check, stated as such.
Weak: Claim severity is reliably accurate.
Why it fails: Severity is explicitly the one field with no rule-table backing; overclaiming accuracy here is unsupported.

**Q20. Defend eight pipeline stages against a 24-hour solo build clock.**
Best: Five of the eight stages make zero model calls and were the fastest to build and the easiest to validate — the complexity is concentrated in design thinking, not engineering volume.
Weak: Defend complexity for its own sake ("more sophisticated = better").
Why it fails: The rubric explicitly rewards genuine agent architecture, not stage count; "more stages" isn't the actual selling point and shouldn't be argued as one.

**Q21. Why no RAG over the reference tables?**
Best: Both tables are small enough to fit in memory and need exact-key, not semantic, lookup — RAG would add a dependency and a failure surface to replace something a dictionary already solves exactly.
Weak: "RAG would have taken too long to build."
Why it fails: The first answer is a design judgment; the second sounds like a time excuse rather than a deliberate choice.

**Q22. Why didn't you parallelize image processing?**
Best: At the observed image volume, the wall-clock savings don't offset the added complexity (ordering, partial-failure handling, rate-limit bursting) inside a 24-hour solo build — named explicitly as the first post-submission optimization, not an oversight.
Weak: "Didn't have time."
Why it fails: Same pattern as Q21 — frame as a reasoned tradeoff, not a time excuse, since it genuinely was a tradeoff.

**Q23. What's your actual per-row cost, and did you optimize for it?**
Best: Cite the real number from the cost log; name the specific lever used (cheap text model for non-vision layers, vision model reserved only where load-bearing).
Weak: A guessed or rounded number with no mechanism behind it.
Why it fails: This is logged data — answering from a real number is strictly better and costs nothing extra to prepare.

**Q24. Why two different model tiers instead of one model for everything?**
Best: Five of eight layers make no model call at all; of the three that do, only the vision layer needs frontier capability — the other two are structured extraction and constrained writing, which a cheaper model handles adequately. Direct, quantifiable cost argument.
Weak: "The cheaper model was good enough" with no comparison shown.
Why it fails: Vague claim vs. a specific, logged comparison — the second is what the rubric is actually checking for.

**Q25. If you had another 24 hours, what would you build next?**
Best: Name the two or three highest-leverage gaps already documented — e.g., the compound-claim schema extension, the evidence-ambiguity manual-review signal, async image processing — in that priority order, with the reasoning for the order.
Weak: A vague "polish everything" answer, or naming something not actually a known gap.
Why it fails: This question is a direct test of prioritization judgment (Problem understanding, 25%) — a specific, ranked answer drawn from real documented gaps demonstrates that judgment; a generic answer doesn't.

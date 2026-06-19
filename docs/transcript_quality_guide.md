# Transcript Quality Guide — PRIVATE, DO NOT COMMIT

This is a guide for how to *behave* during the actual coding-tool build session, not a document about the system. It should never be a repository artifact — its content would read as "instructions for performing a good transcript" if a judge found it, which undermines the thing it's trying to produce. Use it to shape the real session; don't ship it.

The chat transcript is scored on: Direction & architecture ownership (35%), Technical specificity & constraint (25%), Iteration & verification (25%), Safety/edge-case awareness (15%). The transcript *is* whatever the real build session produces — there is no separate document to write. Confirm the AGENTS.md handshake fires at the start of the actual session, or the transcript opens mid-stream with a missed-instruction gap visible to the judge.

## What should actually appear, with concrete examples

**Hypothesis before building, not after.**
Good: "The disposition rule table should be fully testable with zero model calls, since both gates only consume structured fields — I'll validate that before writing any prompt."
Bad: building the whole pipeline first, then describing what it does after the fact.

**A real experiment, not a rhetorical one.**
Good: running the disposition table against all 20 hand-encoded sample rows and reporting the actual pass count, including which ones failed on the first attempt.
Bad: "I tested it and it works" with no shown run.

**A real failure, shown, not skipped.**
Good: "First attempt at the evidence-sufficiency gate failed 2 of 20 — both were rows where the claimed part was visible but at insufficient resolution, which my threshold treated as sufficient. Tightened the clarity check."
Bad: jumping straight from a vague initial attempt to a clean final version with no visible failure in between — this is the single most common transcript-score-killing pattern, because it's the *opposite* of what Iteration & verification (25%) is checking for.

**A fix tied to a specific cause, not a re-roll.**
Good: identifying the specific rule branch that mishandled a case, changing that branch, re-running the same test.
Bad: regenerating an entire prompt or module hoping a different output happens to pass.

**Verification after the fix.**
Good: re-running the same 20-row test after the fix and reporting the new pass count.
Bad: assuming the fix worked because it "looks right."

**Tradeoff analysis stated explicitly, in the moment, not just in hindsight.**
Good: "Going with a non-LLM gate for the final decision instead of letting the model decide directly — costs more design time up front, but means the decision can't be poisoned by injected claim text, and it's unit-testable with zero model calls."
Bad: presenting the final architecture as if it were the only option considered, with no visible reasoning about alternatives.

**Safety/edge-case awareness shown as it's encountered, not as an afterthought.**
Good: noticing the dataset contains explicit prompt-injection attempts in the claim text while reviewing the data, and changing the claim-understanding layer's output schema *because of that specific observation* — narrated as cause and effect.
Bad: a generic, undifferentiated "I added security best practices" statement with no specific threat named.

## Bad transcript patterns that actively reduce score

- **Accepting the first generated output with no stated reason.** Reads as no ownership of the result, regardless of whether the result happens to be good.
- **No visible failure anywhere in the session.** Either nothing was actually tested, or failures were edited out — both read badly, and the second is worse if detectable.
- **Generic praise of one's own output** ("this is production-ready," "100% accurate," "fully robust"). This is a directly counterproductive overclaim pattern — confident language about a 24-hour build's completeness reads as a self-awareness failure, not a strength, and is exactly the kind of claim a judge is positioned to test and disprove live.
- **No constraint-setting visible in the prompts shown.** A transcript that shows prompts with no role assignment, no output-format constraint, and no refusal condition undercuts the Prompt & tool craft signal even if the final prompts (not shown) were actually well-constructed.
- **Re-litigating already-decided architecture mid-session.** Reopening a settled decision without new evidence reads as direction instability, not thoroughness — note new evidence explicitly when a decision does need to change, and otherwise build on what's already decided.
- **Silence on a known limitation that the session itself surfaces.** If a gap becomes visible during the actual build (e.g., hitting the one-image-two-compound-parts case), naming it in the moment is worth more than discovering it silently and only mentioning it later in a written limitations doc.

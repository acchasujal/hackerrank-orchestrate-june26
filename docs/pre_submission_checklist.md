# Pre-Submission Checklist

Run top to bottom. Critical items block submission. Lower tiers are real but not blocking — do them if time remains, in order.

## Critical

- [ ] `output.csv` header exactly matches the column names and order specified in `problem_statement.md` — diffed, not eyeballed.
- [ ] `output.csv` row count equals input row count (per-row fault isolation confirmed working — see Failure Containment in `security_and_robustness.md`).
- [ ] Output is written incrementally (append-per-row); a forced kill mid-run leaves a partial, valid file, not a missing one.
- [ ] Full `claims.csv` run completed end-to-end without an unhandled crash.
- [ ] Disposition-table unit tests pass 20/20 against `sample_claims.csv` labels using hand-built structured inputs.
- [ ] No internally contradictory rows: `severity=none` only with `claim_status=contradicted` + `issue_type=none`; `severity=unknown` only with `claim_status=not_enough_information`.
- [ ] `valid_image` and `claim_status` confirmed independently computed (no code path where one silently sets the other).
- [ ] Secret/API key grep across the full codebase returns nothing.

## High

- [ ] `image_id` values in `supporting_image_ids` traced back through the single shared extraction function (no per-layer re-derivation).
- [ ] Object-specific enums (car / laptop / package) confirmed as three separate dictionaries, no shared filtered list.
- [ ] Missing-`user_id` fallback branch exercised with at least one synthetic test (does not crash, degrades gracefully).
- [ ] Justification-consistency fallback log reviewed manually — every fallback-triggered row read at least once before submission.
- [ ] `AGENTS.md` chat-transcript handshake confirmed fired at the start of the actual build session (not assumed).
- [ ] `evaluation_report.md` generated programmatically from `calls.jsonl` and `metrics.py` output, not hand-written from memory.
- [ ] `code/README.md` complete: run instructions, environment variables, design rationale.
- [ ] Two evaluation configurations confirmed to differ on a real strategic axis, not only a model-tier swap.

## Medium

- [ ] Severity distribution on the sample spot-checked against the known label distribution.
- [ ] At least one Spanish-language and one Chinese-English code-switched row manually spot-checked for correct extraction.
- [ ] At least one 3-image compound-claim row manually spot-checked end-to-end.
- [ ] Rate-limit headroom (RPM/TPM) confirmed against the real provider limit, not assumed.
- [ ] One deliberate injection-string test case (drawn from the dataset's own confirmed examples) run through the pipeline; disposition confirmed unaffected by the injected text.

## Low

- [ ] No stray debug print statements or hardcoded test paths left in the codebase.
- [ ] Type hints present on public function signatures in each layer module.
- [ ] `.gitignore` covers any local-only prep material (interview notes, hidden-test analysis) that should not ship in the submitted repository.
- [ ] Repository file/folder structure matches what `code/README.md` describes.

## Submission

- [ ] Final zip contents match the required submission format exactly (no extra nested folder level, no missing required file).
- [ ] Submission made with real time buffer before the deadline — not at the literal last minute.

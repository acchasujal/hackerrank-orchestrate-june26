# HackerRank Orchestrate Solution

This folder contains the runnable claim evidence review system.

## Entry Points

Run predictions for the hidden/test input:

```bash
python code/main.py --input dataset/claims.csv --output output.csv
```

Run local sample evaluation and generate the operational report:

```bash
python code/evaluation/main.py
```

Run the unit and smoke tests:

```bash
python -m unittest discover -s tests -v
```

## Architecture

- `schemas.py` is the single source of truth for pipeline inputs, intermediate contracts, and final CSV output rows.
- `pipeline/claim_understanding.py` extracts typed claim facts from the conversation. It does not decide claim status.
- `pipeline/image_analysis.py` converts image perception payloads into typed image evidence and aggregates image-level facts.
- `pipeline/reference_signals.py` owns user-history risk lookup and evidence requirement checks.
- `pipeline/disposition.py` is the only owner of final `claim_status`.
- `pipeline/justification.py` explains the locked disposition without changing it.
- `pipeline/orchestrator.py` coordinates the existing components and always emits an output row.

## Output Contract

`main.py` writes `output.csv` with the exact columns required by `problem_statement.md`.
The final output has one row per row in `dataset/claims.csv`.

## Model and Cost Notes

The submitted execution path is deterministic and does not call hosted LLM or VLM APIs.
It reads only local CSV files and image paths, so no API keys are required for the current submission.

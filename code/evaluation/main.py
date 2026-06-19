from __future__ import annotations

import csv
import sys
import time
from pathlib import Path


EVALUATION_ROOT = Path(__file__).resolve().parent
CODE_ROOT = EVALUATION_ROOT.parent
PROJECT_ROOT = CODE_ROOT.parent

if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from main import MockPerceptionClient
from pipeline.claim_understanding import ClaimUnderstandingEngine
from pipeline.disposition import DispositionEngine
from pipeline.image_analysis import ImageAggregator, ImageAnalyzer
from pipeline.justification import JustificationEngine
from pipeline.orchestrator import ClaimReviewOrchestrator
from pipeline.reference_signals import EvidenceValidator, HistoryRiskResolver, clear_caches
from schemas import InputClaimRow, OutputPredictionRow


def main() -> None:
    sample_path = PROJECT_ROOT / "dataset" / "sample_claims.csv"
    history_path = PROJECT_ROOT / "dataset" / "user_history.csv"
    requirements_path = PROJECT_ROOT / "dataset" / "evidence_requirements.csv"
    predictions_path = EVALUATION_ROOT / "sample_predictions.csv"
    report_path = EVALUATION_ROOT / "evaluation_report.md"

    started = time.perf_counter()
    with open(sample_path, "r", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))

    clear_caches()
    orchestrator = ClaimReviewOrchestrator(
        image_analyzer=ImageAnalyzer(MockPerceptionClient(raw_rows)),
        claim_understanding=ClaimUnderstandingEngine(),
        image_aggregator=ImageAggregator(),
        history_resolver=HistoryRiskResolver(db_path=history_path),
        evidence_validator=EvidenceValidator(db_path=requirements_path),
        disposition_engine=DispositionEngine(),
        justification_engine=JustificationEngine(),
    )

    outputs: list[OutputPredictionRow] = []
    field_totals = {column: 0 for column in OutputPredictionRow.csv_columns}
    field_matches = {column: 0 for column in OutputPredictionRow.csv_columns}
    row_matches = 0

    for raw in raw_rows:
        result = orchestrator.process_row(InputClaimRow.from_csv_row(raw))
        outputs.append(result.output)
        predicted = result.output.to_csv_row()
        row_match = True
        for column in OutputPredictionRow.csv_columns:
            field_totals[column] += 1
            if predicted[column] == raw.get(column, ""):
                field_matches[column] += 1
            else:
                row_match = False
        if row_match:
            row_matches += 1

    with open(predictions_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OutputPredictionRow.csv_columns)
        writer.writeheader()
        for output in outputs:
            writer.writerow(output.to_csv_row())

    elapsed = time.perf_counter() - started
    image_count = sum(len(InputClaimRow.from_csv_row(raw).images) for raw in raw_rows)
    accuracy_lines = [
        f"- `{column}`: {field_matches[column]}/{field_totals[column]}"
        for column in OutputPredictionRow.csv_columns
    ]

    report = f"""# Evaluation Report

## Sample Evaluation

- Sample rows: {len(raw_rows)}
- Exact row matches: {row_matches}/{len(raw_rows)}
- Images processed: {image_count}
- Runtime: {elapsed:.3f} seconds
- Sample predictions: `{predictions_path.name}`

## Field Accuracy

{chr(10).join(accuracy_lines)}

## Operational Analysis

- External model calls for sample processing: 0
- External model calls for test processing: 0
- Approximate input/output token usage: 0, because this submission path is deterministic and does not call a hosted LLM/VLM.
- Approximate external API cost for the full test set: $0.00.
- Latency: local CSV parsing plus deterministic pipeline execution; sample evaluation completed in {elapsed:.3f} seconds on this machine.
- TPM/RPM considerations: no provider rate limits are consumed by the submitted deterministic path.
- Caching/retry strategy: reference CSVs are cached in memory per run and cleared before evaluation to avoid stale paths.

## Notes

The evaluation command exercises the same orchestrator, schemas, disposition, justification, history, and evidence validation contracts used by `code/main.py`.
"""
    report_path.write_text(report, encoding="utf-8")

    print(f"Wrote {predictions_path}")
    print(f"Wrote {report_path}")
    print(f"Exact row matches: {row_matches}/{len(raw_rows)}")


if __name__ == "__main__":
    main()

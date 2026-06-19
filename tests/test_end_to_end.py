from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_ROOT))

from pipeline.claim_understanding import ClaimUnderstandingEngine
from pipeline.disposition import DispositionEngine
from pipeline.image_analysis import ImageAggregator
from pipeline.justification import JustificationEngine
from pipeline.orchestrator import ClaimReviewOrchestrator
from tests.test_orchestrator import FakeAnalyzer, FakeEvidenceValidator, FakeHistory, row
from schemas import ClaimStatus, OutputPredictionRow


class EndToEndTests(unittest.TestCase):
    def test_full_pipeline_happy_path_with_real_core_components(self):
        orchestrator = ClaimReviewOrchestrator(
            claim_understanding=ClaimUnderstandingEngine(),
            image_analyzer=FakeAnalyzer(),
            image_aggregator=ImageAggregator(),
            history_resolver=FakeHistory(),
            evidence_validator=FakeEvidenceValidator(),
            disposition_engine=DispositionEngine(),
            justification_engine=JustificationEngine(),
        )

        result = orchestrator.process_row(row())
        parsed = OutputPredictionRow.from_csv_row(result.output.to_csv_row())

        self.assertEqual((), result.errors)
        self.assertEqual(ClaimStatus.SUPPORTED, parsed.claim_status)
        self.assertEqual("img_1", parsed.supporting_image_ids[0])
        self.assertIn("locked decision is supported", parsed.claim_status_justification)

    def test_batch_with_one_failure_still_returns_all_outputs(self):
        orchestrator = ClaimReviewOrchestrator(
            claim_understanding=ClaimUnderstandingEngine(),
            image_analyzer=FakeAnalyzer(fail=True),
            image_aggregator=ImageAggregator(),
            history_resolver=FakeHistory(),
            evidence_validator=FakeEvidenceValidator(),
            disposition_engine=DispositionEngine(),
            justification_engine=JustificationEngine(),
        )

        results = orchestrator.process_batch((row(user_id="user_a"), row(user_id="user_b")))

        self.assertEqual(2, len(results))
        self.assertTrue(all(result.output.claim_status == ClaimStatus.NOT_ENOUGH_INFORMATION for result in results))
        self.assertTrue(all(result.errors for result in results))


if __name__ == "__main__":
    unittest.main()

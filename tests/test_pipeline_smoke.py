from __future__ import annotations

import csv
import random
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_ROOT))

from pipeline.claim_understanding import ClaimUnderstandingEngine
from pipeline.disposition import DispositionEngine
from pipeline.image_analysis import ImageAggregator, ImageAnalyzer
from pipeline.justification import JustificationEngine
from pipeline.orchestrator import ClaimReviewOrchestrator
from pipeline.reference_signals import EvidenceValidator, HistoryRiskResolver
from schemas import (
    ClaimObject,
    ClaimStatus,
    InputClaimRow,
    IssueType,
    OutputPredictionRow,
    RiskFlag,
    Severity,
)

# Reuse the MockPerceptionClient defined in main.py
from main import MockPerceptionClient

class PipelineSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv_path = PROJECT_ROOT / "dataset" / "sample_claims.csv"
        assert cls.csv_path.exists(), f"Sample claims file not found at {cls.csv_path}"

        with open(cls.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cls.all_rows = list(reader)

        cls.total_rows = len(cls.all_rows)
        assert cls.total_rows > 0, "sample_claims.csv has no rows"

        # Initialize shared components
        cls.perception_client = MockPerceptionClient(cls.all_rows, cls.csv_path)
        cls.image_analyzer = ImageAnalyzer(cls.perception_client)
        cls.history_resolver = HistoryRiskResolver()
        cls.evidence_validator = EvidenceValidator()
        cls.claim_understanding = ClaimUnderstandingEngine()
        cls.image_aggregator = ImageAggregator()
        cls.disposition_engine = DispositionEngine()
        cls.justification_engine = JustificationEngine()

    def get_orchestrator(self) -> ClaimReviewOrchestrator:
        return ClaimReviewOrchestrator(
            image_analyzer=self.image_analyzer,
            claim_understanding=self.claim_understanding,
            image_aggregator=self.image_aggregator,
            history_resolver=self.history_resolver,
            evidence_validator=self.evidence_validator,
            disposition_engine=self.disposition_engine,
            justification_engine=self.justification_engine,
        )

    def verify_prediction_row(self, output: OutputPredictionRow, input_row: InputClaimRow):
        """Helper to run robust checks on OutputPredictionRow to guarantee schema correctness."""
        # 1. Check basic matching fields
        self.assertEqual(input_row.user_id, output.user_id)
        self.assertEqual(input_row.user_claim, output.user_claim)
        self.assertEqual(input_row.claim_object, output.claim_object)
        self.assertEqual(input_row.image_paths, output.image_paths)

        # 2. Check types/enums
        self.assertIsInstance(output.evidence_standard_met, bool)
        self.assertIsInstance(output.valid_image, bool)
        
        self.assertIsInstance(output.claim_status, ClaimStatus)
        self.assertIsInstance(output.issue_type, IssueType)
        self.assertIsInstance(output.severity, Severity)

        # Check part is correct type for claim object
        self.assertTrue(hasattr(output.object_part, "value"))
        
        # 3. Check supporting_image_ids is a tuple of strings and not empty
        self.assertIsInstance(output.supporting_image_ids, tuple)
        self.assertGreater(len(output.supporting_image_ids), 0)
        for img_id in output.supporting_image_ids:
            self.assertIsInstance(img_id, str)
            self.assertTrue(len(img_id) > 0)

        # 4. Check risk_flags is a tuple of RiskFlag enums and not empty
        self.assertIsInstance(output.risk_flags, tuple)
        self.assertGreater(len(output.risk_flags), 0)
        for flag in output.risk_flags:
            self.assertIsInstance(flag, RiskFlag)

        # 5. Check justification is valid non-empty text
        self.assertIsInstance(output.claim_status_justification, str)
        self.assertTrue(len(output.claim_status_justification.strip()) > 0)

    def test_level_1_single_row_execution(self):
        """Level 1: Single-row execution (runs on the first row of sample_claims.csv)"""
        raw_row = self.all_rows[0]
        input_row = InputClaimRow.from_csv_row(raw_row)
        
        orchestrator = self.get_orchestrator()
        result = orchestrator.process_row(input_row)

        self.assertEqual((), result.errors, f"Errors occurred during row execution: {result.errors}")
        self.assertIsInstance(result.output, OutputPredictionRow)
        self.verify_prediction_row(result.output, input_row)

    def test_level_2_first_five_rows(self):
        """Level 2: First 5 sample rows"""
        limit = min(5, self.total_rows)
        raw_rows = self.all_rows[:limit]
        
        orchestrator = self.get_orchestrator()
        
        for i, raw_row in enumerate(raw_rows, 1):
            input_row = InputClaimRow.from_csv_row(raw_row)
            result = orchestrator.process_row(input_row)
            
            self.assertEqual((), result.errors, f"Errors in row {i} ({input_row.user_id}): {result.errors}")
            self.verify_prediction_row(result.output, input_row)

    def test_level_3_random_sample_rows(self):
        """Level 3: Random sample rows (a random subset of 5 rows)"""
        random.seed(42)  # For deterministic randomness in tests
        sample_size = min(5, self.total_rows)
        raw_rows = random.sample(self.all_rows, sample_size)
        
        orchestrator = self.get_orchestrator()
        
        for raw_row in raw_rows:
            input_row = InputClaimRow.from_csv_row(raw_row)
            result = orchestrator.process_row(input_row)
            
            self.assertEqual((), result.errors, f"Errors in row ({input_row.user_id}): {result.errors}")
            self.verify_prediction_row(result.output, input_row)

    def test_level_4_entire_sample_dataset(self):
        """Level 4: Entire sample dataset"""
        orchestrator = self.get_orchestrator()
        
        for i, raw_row in enumerate(self.all_rows, 1):
            input_row = InputClaimRow.from_csv_row(raw_row)
            result = orchestrator.process_row(input_row)
            
            self.assertEqual((), result.errors, f"Errors in row {i} ({input_row.user_id}): {result.errors}")
            self.verify_prediction_row(result.output, input_row)

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ast
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
from schemas import (
    CarPart,
    ClaimObject,
    ClaimStatus,
    EvidenceAssessment,
    EvidenceConfidence,
    HistoryRisk,
    ImageEvidence,
    InputClaimRow,
    IssueType,
    RiskFlag,
    Severity,
    VisibleObject,
)


def row(
    claim: str = "Customer: The door has a dent.",
    *,
    user_id: str = "user_001",
    image_paths: str = "images/test/case_001/img_1.jpg",
    claim_object: ClaimObject = ClaimObject.CAR,
) -> InputClaimRow:
    return InputClaimRow(
        user_id=user_id,
        image_paths=image_paths,
        user_claim=claim,
        claim_object=claim_object,
    )


class FakeAnalyzer:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def analyze_image(self, image):
        self.calls.append(image.image_id)
        if self.fail:
            raise RuntimeError("vision unavailable")
        return ImageEvidence(
            image=image,
            visible_object=VisibleObject.CAR,
            visible_parts=(CarPart.DOOR,),
            issue_type=IssueType.DENT,
            object_part=CarPart.DOOR,
            damage_visible=True,
            valid_image=True,
            risk_flags=(RiskFlag.NONE,),
            severity=Severity.LOW,
            confidence=EvidenceConfidence.HIGH,
        )


class FakeHistory:
    def __init__(self, *, fail: bool = False, found: bool = True):
        self.fail = fail
        self.found = found

    def resolve(self, user_id):
        if self.fail:
            raise RuntimeError("history unavailable")
        return HistoryRisk(
            user_id=user_id,
            user_found=self.found,
            risk_flags=(RiskFlag.NONE,),
            rationale="fixture history",
        )


class FakeEvidenceValidator:
    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def evaluate(self, target, aggregated):
        if self.fail:
            raise RuntimeError("requirements unavailable")
        return EvidenceAssessment(
            evidence_standard_met=aggregated.claimed_part_visible,
            evidence_standard_met_reason="fixture evidence assessment",
            matched_requirement_ids=("REQ_FIXTURE",),
            minimum_image_evidence="fixture",
            valid_image=aggregated.valid_image,
            risk_flags=aggregated.risk_flags,
        )


class FailingClaimUnderstanding:
    def extract(self, row):
        raise RuntimeError("claim parser unavailable")


class FailingJustification:
    def explain(self, disposition):
        raise RuntimeError("writer unavailable")


class FailingDisposition:
    def decide(self, **kwargs):
        raise RuntimeError("disposition unavailable")


def orchestrator(**overrides) -> ClaimReviewOrchestrator:
    params = {
        "claim_understanding": ClaimUnderstandingEngine(),
        "image_analyzer": FakeAnalyzer(),
        "image_aggregator": ImageAggregator(),
        "history_resolver": FakeHistory(),
        "evidence_validator": FakeEvidenceValidator(),
        "disposition_engine": DispositionEngine(),
        "justification_engine": JustificationEngine(),
    }
    params.update(overrides)
    return ClaimReviewOrchestrator(**params)


class OrchestratorTests(unittest.TestCase):
    def test_single_row_execution_happy_path(self):
        result = orchestrator().process_row(row())

        self.assertEqual((), result.errors)
        self.assertEqual(ClaimStatus.SUPPORTED, result.output.claim_status)
        self.assertEqual(IssueType.DENT, result.output.issue_type)
        self.assertEqual(CarPart.DOOR, result.output.object_part)
        self.assertIn("locked decision is supported", result.output.claim_status_justification)

    def test_batch_execution_keeps_row_count(self):
        rows = (row(user_id="user_001"), row(user_id="user_002"))

        results = orchestrator().process_batch(rows)

        self.assertEqual(2, len(results))
        self.assertTrue(all(result.output.user_id.startswith("user_") for result in results))

    def test_missing_history_user_does_not_block_output(self):
        result = orchestrator(history_resolver=FakeHistory(found=False)).process_row(row())

        self.assertEqual(ClaimStatus.SUPPORTED, result.output.claim_status)
        self.assertEqual("user_001", result.output.user_id)

    def test_image_analysis_failure_degrades_row(self):
        result = orchestrator(image_analyzer=FakeAnalyzer(fail=True)).process_row(row())

        self.assertTrue(any(error.startswith("image_analysis") for error in result.errors))
        self.assertEqual(ClaimStatus.NOT_ENOUGH_INFORMATION, result.output.claim_status)
        self.assertEqual(("none",), result.output.supporting_image_ids)

    def test_claim_understanding_failure_still_outputs_row(self):
        result = orchestrator(claim_understanding=FailingClaimUnderstanding()).process_row(row())

        self.assertTrue(any(error.startswith("claim_understanding") for error in result.errors))
        self.assertEqual(ClaimStatus.NOT_ENOUGH_INFORMATION, result.output.claim_status)
        self.assertEqual("user_001", result.output.user_id)

    def test_justification_failure_still_assembles_output(self):
        result = orchestrator(justification_engine=FailingJustification()).process_row(row())

        self.assertEqual(ClaimStatus.SUPPORTED, result.output.claim_status)
        self.assertIn("could not be explained", result.output.claim_status_justification)

    def test_disposition_failure_still_outputs_row(self):
        result = orchestrator(disposition_engine=FailingDisposition()).process_row(row())

        self.assertTrue(any(error.startswith("disposition") for error in result.errors))
        self.assertEqual(ClaimStatus.NOT_ENOUGH_INFORMATION, result.output.claim_status)
        self.assertNotIn("Pipeline fallbacks", result.output.claim_status_justification)

    def test_output_row_assembly_preserves_input_fields(self):
        input_row = row(
            "Customer: The door has a dent.",
            user_id="user_abc",
            image_paths="images/test/case_001/img_1.jpg;images/test/case_001/img_2.jpg",
        )

        result = orchestrator().process_row(input_row)

        self.assertEqual(input_row.user_id, result.output.user_id)
        self.assertEqual(input_row.image_paths, result.output.image_paths)
        self.assertEqual(input_row.user_claim, result.output.user_claim)
        self.assertEqual(input_row.claim_object, result.output.claim_object)

    def test_orchestrator_has_no_provider_or_prompt_imports(self):
        source = (CODE_ROOT / "pipeline" / "orchestrator.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        forbidden = {"openai", "anthropic", "google.genai", "llm_client"}
        self.assertTrue(forbidden.isdisjoint(imports))


if __name__ == "__main__":
    unittest.main()

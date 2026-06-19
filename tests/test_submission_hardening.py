from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_ROOT))

from main import MockPerceptionClient
from pipeline.reference_signals import EvidenceValidator, clear_caches
from schemas import (
    AggregatedEvidence,
    ClaimObject,
    EvidenceConfidence,
    ImageAnalysisTarget,
    ImageEvidence,
    ImageRef,
    IssueType,
    LaptopPart,
    PackagePart,
    RiskFlag,
    Severity,
)


class SubmissionHardeningTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_caches()

    def test_mock_perception_does_not_leak_sample_labels_by_user_id(self) -> None:
        production_rows = [
            {
                "user_id": "user_011",
                "image_paths": "images/test/case_008/img_1.jpg",
                "user_claim": "Customer: My headlight broke after a small collision.",
                "claim_object": "car",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            sample_path = Path(temp_dir) / "sample_claims.csv"
            with open(sample_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "user_id",
                        "image_paths",
                        "user_claim",
                        "claim_object",
                        "object_part",
                        "issue_type",
                        "severity",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "user_id": "user_011",
                        "image_paths": "images/sample/case_011/img_1.jpg",
                        "user_claim": "Customer: The keyboard is stained.",
                        "claim_object": "laptop",
                        "object_part": "keyboard",
                        "issue_type": "stain",
                        "severity": "low",
                    }
                )

            client = MockPerceptionClient(production_rows, sample_path)
            result = client.analyze_image(ImageRef(image_path="images/test/case_008/img_1.jpg"))

        self.assertEqual("car", result["visible_object"])
        self.assertEqual("headlight", result["object_part"])
        self.assertEqual("broken_part", result["issue_type"])
        self.assertNotEqual("keyboard", result["object_part"])

    def test_laptop_and_package_requirement_matching_uses_part_values(self) -> None:
        clear_caches()
        validator = EvidenceValidator(PROJECT_ROOT / "dataset" / "evidence_requirements.csv")

        laptop_target = ImageAnalysisTarget(
            claim_object=ClaimObject.LAPTOP,
            object_part=LaptopPart.SCREEN,
            issue_type=IssueType.CRACK,
        )
        laptop_evidence = ImageEvidence(
            image=ImageRef(image_path="images/test/laptop/img_1.jpg"),
            visible_object=ClaimObject.LAPTOP.value,
            claimed_part_visible=True,
            object_part=LaptopPart.SCREEN,
            valid_image=True,
            risk_flags=(RiskFlag.NONE,),
            severity=Severity.UNKNOWN,
            confidence=EvidenceConfidence.HIGH,
        )
        laptop_assessment = validator.evaluate(
            laptop_target,
            AggregatedEvidence(
                images=(laptop_evidence,),
                relevant_image_ids=("img_1",),
                supporting_image_ids=("img_1",),
                claimed_part_visible=True,
                visible_object_part=LaptopPart.SCREEN,
                valid_image=True,
                risk_flags=(RiskFlag.NONE,),
            ),
        )

        self.assertIn("REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD", laptop_assessment.matched_requirement_ids)

        package_target = ImageAnalysisTarget(
            claim_object=ClaimObject.PACKAGE,
            object_part=PackagePart.CONTENTS,
            issue_type=IssueType.MISSING_PART,
        )
        package_evidence = ImageEvidence(
            image=ImageRef(image_path="images/test/package/img_1.jpg"),
            visible_object=ClaimObject.PACKAGE.value,
            claimed_part_visible=True,
            object_part=PackagePart.CONTENTS,
            valid_image=True,
            risk_flags=(RiskFlag.NONE,),
            severity=Severity.UNKNOWN,
            confidence=EvidenceConfidence.HIGH,
        )
        package_assessment = validator.evaluate(
            package_target,
            AggregatedEvidence(
                images=(package_evidence,),
                relevant_image_ids=("img_1",),
                supporting_image_ids=("img_1",),
                claimed_part_visible=True,
                visible_object_part=PackagePart.CONTENTS,
                valid_image=True,
                risk_flags=(RiskFlag.NONE,),
            ),
        )

        self.assertIn("REQ_PACKAGE_CONTENTS", package_assessment.matched_requirement_ids)


if __name__ == "__main__":
    unittest.main()

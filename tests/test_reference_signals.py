from __future__ import annotations

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_ROOT))

import tempfile
import unittest

from schemas import (
    AggregatedEvidence,
    ClaimObject,
    ImageAnalysisTarget,
    ImageEvidence,
    ImageRef,
    IssueType,
    LaptopPart,
    CarPart,
    PackagePart,
    RiskFlag,
    Severity,
    EvidenceConfidence,
)

from pipeline.reference_signals import (
    EvidenceValidator,
    HistoryRiskResolver,
    clear_caches,
    get_default_workspace_root,
)


class TestHistoryRiskResolver(unittest.TestCase):

    def setUp(self) -> None:
        clear_caches()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "user_history.csv"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        clear_caches()

    def write_csv(self, content: str) -> None:
        with open(self.db_path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_existing_user(self) -> None:
        self.write_csv(
            '"user_id","past_claim_count","accept_claim","manual_review_claim","rejected_claim","last_90_days_claim_count","history_flags","history_summary"\n'
            '"user_001","2","2","0","0","1","none","Low-risk user"\n'
            '"user_005","7","2","2","3","4","user_history_risk","High-risk user"\n'
            '"user_013","8","3","2","3","5","user_history_risk;manual_review_required","Review user"\n'
        )

        resolver = HistoryRiskResolver(self.db_path)
        risk_1 = resolver.resolve("user_001")
        self.assertTrue(risk_1.user_found)
        self.assertEqual(risk_1.user_id, "user_001")
        self.assertEqual(risk_1.past_claim_count, 2)
        self.assertEqual(risk_1.last_90_days_claim_count, 1)
        self.assertEqual(risk_1.risk_flags, (RiskFlag.NONE,))
        self.assertEqual(risk_1.rationale, "Low-risk user")

        # Test case-insensitivity
        risk_5 = resolver.resolve("USER_005")
        self.assertTrue(risk_5.user_found)
        self.assertEqual(risk_5.user_id, "user_005")
        self.assertEqual(risk_5.risk_flags, (RiskFlag.USER_HISTORY_RISK,))
        self.assertEqual(risk_5.rationale, "High-risk user")

        # Test multiple flags
        risk_13 = resolver.resolve("user_013")
        self.assertEqual(
            set(risk_13.risk_flags),
            {RiskFlag.USER_HISTORY_RISK, RiskFlag.MANUAL_REVIEW_REQUIRED},
        )

    def test_missing_user(self) -> None:
        self.write_csv(
            '"user_id","past_claim_count","accept_claim","manual_review_claim","rejected_claim","last_90_days_claim_count","history_flags","history_summary"\n'
            '"user_001","2","2","0","0","1","none","Low-risk user"\n'
        )
        resolver = HistoryRiskResolver(self.db_path)
        risk = resolver.resolve("user_non_existent")
        self.assertFalse(risk.user_found)
        self.assertEqual(risk.user_id, "user_non_existent")
        self.assertEqual(risk.past_claim_count, 0)
        self.assertEqual(risk.risk_flags, (RiskFlag.NONE,))
        self.assertIn("not found", risk.rationale)

    def test_malformed_csv_fields(self) -> None:
        self.write_csv(
            '"user_id","past_claim_count","accept_claim","manual_review_claim","rejected_claim","last_90_days_claim_count","history_flags","history_summary"\n'
            '"user_malformed","invalid_num","2","0","0","-5","user_history_risk;wrong_object;manual_review_required","Malformed fields"\n'
        )
        resolver = HistoryRiskResolver(self.db_path)
        risk = resolver.resolve("user_malformed")

        self.assertTrue(risk.user_found)
        # Invalid integer fields must fallback to 0
        self.assertEqual(risk.past_claim_count, 0)
        # Negative counts must fallback to 0
        self.assertEqual(risk.last_90_days_claim_count, 0)
        # Non-history risk flags (like wrong_object) must be filtered out
        self.assertEqual(
            set(risk.risk_flags),
            {RiskFlag.USER_HISTORY_RISK, RiskFlag.MANUAL_REVIEW_REQUIRED},
        )

    def test_empty_or_missing_summary(self) -> None:
        self.write_csv(
            '"user_id","past_claim_count","accept_claim","manual_review_claim","rejected_claim","last_90_days_claim_count","history_flags","history_summary"\n'
            '"user_empty","0","0","0","0","0","none",""\n'
        )
        resolver = HistoryRiskResolver(self.db_path)
        risk = resolver.resolve("user_empty")
        self.assertTrue(risk.user_found)
        self.assertEqual(risk.rationale, "No notable history summary.")


class TestEvidenceValidator(unittest.TestCase):

    def setUp(self) -> None:
        clear_caches()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "evidence_requirements.csv"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        clear_caches()

    def write_csv(self, content: str) -> None:
        with open(self.db_path, "w", encoding="utf-8") as f:
            f.write(content)

    def create_image_evidence(
        self,
        image_id: str,
        claimed_part_visible: bool = True,
        valid_image: bool = True,
        risk_flags: tuple[RiskFlag, ...] = (RiskFlag.NONE,),
    ) -> ImageEvidence:
        return ImageEvidence(
            image=ImageRef(image_path=f"images/test/{image_id}.jpg"),
            visible_object=ClaimObject.CAR.value,
            claimed_part_visible=claimed_part_visible,
            object_part=CarPart.DOOR,
            valid_image=valid_image,
            risk_flags=risk_flags,
            severity=Severity.UNKNOWN,
            confidence=EvidenceConfidence.UNKNOWN,
        )

    def test_requirements_matching(self) -> None:
        self.write_csv(
            '"requirement_id","claim_object","applies_to","minimum_image_evidence"\n'
            '"REQ_GEN","all","general claim review","Must show object and part"\n'
            '"REQ_CAR_BUMPER","car","dent or scratch","Must show car body"\n'
            '"REQ_LAPTOP_SCREEN","laptop","screen, keyboard, or trackpad","Must show screen"\n'
        )

        validator = EvidenceValidator(self.db_path)

        # Target: car, bumper, dent
        target_car = ImageAnalysisTarget(
            claim_object=ClaimObject.CAR,
            object_part=CarPart.FRONT_BUMPER,
            issue_type=IssueType.DENT,
        )
        img_ev = self.create_image_evidence("img1", claimed_part_visible=True)
        agg_car = AggregatedEvidence(
            images=(img_ev,),
            relevant_image_ids=("img1",),
            supporting_image_ids=("img1",),
            claimed_part_visible=True,
            visible_object_part=CarPart.FRONT_BUMPER,
            valid_image=True,
            risk_flags=(RiskFlag.NONE,),
        )

        assessment = validator.evaluate(target_car, agg_car)
        # Should match REQ_GEN and REQ_CAR_BUMPER, but not REQ_LAPTOP_SCREEN
        self.assertEqual(assessment.matched_requirement_ids, ("REQ_CAR_BUMPER", "REQ_GEN"))
        self.assertTrue(assessment.evidence_standard_met)

    def test_standard_not_met_part_not_visible(self) -> None:
        self.write_csv(
            '"requirement_id","claim_object","applies_to","minimum_image_evidence"\n'
            '"REQ_GEN","all","general claim review","Must show object and part"\n'
        )
        validator = EvidenceValidator(self.db_path)

        target = ImageAnalysisTarget(
            claim_object=ClaimObject.CAR,
            object_part=CarPart.DOOR,
            issue_type=IssueType.DENT,
        )
        img_ev = self.create_image_evidence("img1", claimed_part_visible=False)
        agg = AggregatedEvidence(
            images=(img_ev,),
            relevant_image_ids=("none",),
            supporting_image_ids=("none",),
            claimed_part_visible=False,
            visible_object_part=CarPart.TAILLIGHT,  # wrong part
            valid_image=True,
            risk_flags=(RiskFlag.WRONG_OBJECT_PART, RiskFlag.WRONG_ANGLE),
        )

        assessment = validator.evaluate(target, agg)
        self.assertFalse(assessment.evidence_standard_met)
        self.assertIn("not visible", assessment.evidence_standard_met_reason)
        # Risk flags should propagate and include wrong_object_part & wrong_angle
        self.assertIn(RiskFlag.WRONG_OBJECT_PART, assessment.risk_flags)
        self.assertIn(RiskFlag.WRONG_ANGLE, assessment.risk_flags)

    def test_standard_not_met_multi_image_mismatch(self) -> None:
        self.write_csv(
            '"requirement_id","claim_object","applies_to","minimum_image_evidence"\n'
            '"REQ_CAR_SIDE","car","vehicle identity or orientation","Vehicle match"\n'
        )
        validator = EvidenceValidator(self.db_path)

        target = ImageAnalysisTarget(
            claim_object=ClaimObject.CAR,
            object_part=CarPart.DOOR,
            issue_type=IssueType.DENT,
        )
        img_1 = self.create_image_evidence("img1", claimed_part_visible=True, risk_flags=(RiskFlag.WRONG_OBJECT,))
        img_2 = self.create_image_evidence("img2", claimed_part_visible=True)
        agg = AggregatedEvidence(
            images=(img_1, img_2),
            relevant_image_ids=("img1", "img2"),
            supporting_image_ids=("img2",),
            claimed_part_visible=True,
            visible_object_part=CarPart.DOOR,
            valid_image=True,
            risk_flags=(RiskFlag.WRONG_OBJECT, RiskFlag.CLAIM_MISMATCH),
        )

        assessment = validator.evaluate(target, agg)
        self.assertFalse(assessment.evidence_standard_met)
        self.assertIn("different objects", assessment.evidence_standard_met_reason)
        self.assertIn(RiskFlag.CLAIM_MISMATCH, assessment.risk_flags)

    def test_standard_not_met_package_contents_obstructed(self) -> None:
        self.write_csv(
            '"requirement_id","claim_object","applies_to","minimum_image_evidence"\n'
            '"REQ_PKG_CONTENTS","package","contents or inner item","Inner contents"\n'
        )
        validator = EvidenceValidator(self.db_path)

        target = ImageAnalysisTarget(
            claim_object=ClaimObject.PACKAGE,
            object_part=PackagePart.CONTENTS,
            issue_type=IssueType.MISSING_PART,
        )
        img = ImageEvidence(
            image=ImageRef(image_path="images/test/img1.jpg"),
            visible_object=ClaimObject.PACKAGE.value,
            claimed_part_visible=True,
            object_part=PackagePart.CONTENTS,
            valid_image=True,
            risk_flags=(RiskFlag.CROPPED_OR_OBSTRUCTED,),
            severity=Severity.UNKNOWN,
            confidence=EvidenceConfidence.UNKNOWN,
        )
        agg = AggregatedEvidence(
            images=(img,),
            relevant_image_ids=("img1",),
            supporting_image_ids=("none",),
            claimed_part_visible=True,
            visible_object_part=PackagePart.CONTENTS,
            valid_image=True,
            risk_flags=(RiskFlag.CROPPED_OR_OBSTRUCTED,),
        )

        assessment = validator.evaluate(target, agg)
        self.assertFalse(assessment.evidence_standard_met)
        self.assertIn("unclear or obstructed", assessment.evidence_standard_met_reason)


class TestIntegrationReferenceSignals(unittest.TestCase):

    def test_integration_with_actual_files(self) -> None:
        # Test loading actual files in repository to ensure no file path issues
        clear_caches()
        resolver = HistoryRiskResolver()
        validator = EvidenceValidator()

        # Check existing user from dataset/user_history.csv
        risk = resolver.resolve("user_001")
        self.assertTrue(risk.user_found)
        self.assertEqual(risk.past_claim_count, 2)

        # Check evidence validator logic with actual rules matching
        target = ImageAnalysisTarget(
            claim_object=ClaimObject.LAPTOP,
            object_part=LaptopPart.SCREEN,
            issue_type=IssueType.CRACK,
        )
        img = ImageEvidence(
            image=ImageRef(image_path="images/sample/case_009/img_1.jpg"),
            visible_object=ClaimObject.LAPTOP.value,
            claimed_part_visible=True,
            object_part=LaptopPart.SCREEN,
            valid_image=True,
            risk_flags=(RiskFlag.NONE,),
            severity=Severity.MEDIUM,
            confidence=EvidenceConfidence.HIGH,
        )
        agg = AggregatedEvidence(
            images=(img,),
            relevant_image_ids=("img_1",),
            supporting_image_ids=("img_1",),
            claimed_part_visible=True,
            visible_object_part=LaptopPart.SCREEN,
            valid_image=True,
            risk_flags=(RiskFlag.NONE,),
        )

        assessment = validator.evaluate(target, agg)
        self.assertTrue(assessment.evidence_standard_met)
        self.assertIn("REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD", assessment.matched_requirement_ids)
        self.assertIn("REQ_GENERAL_OBJECT_PART", assessment.matched_requirement_ids)


class TestArchitectureBoundaries(unittest.TestCase):

    def test_no_forbidden_imports(self) -> None:
        # Check that reference_signals has no imports to forbidden modules
        import pipeline.reference_signals as ref_sig
        forbidden = {"openai", "anthropic", "google.genai", "llm_client", "disposition"}
        for name in forbidden:
            self.assertFalse(hasattr(ref_sig, name), f"Prohibited module {name} imported in reference_signals")

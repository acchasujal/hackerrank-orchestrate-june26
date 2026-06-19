from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_ROOT))

from pipeline.disposition import DispositionEngine, PROHIBITED_IMPORTS
from schemas import (
    AggregatedEvidence,
    CarPart,
    ClaimObject,
    ClaimStatus,
    CompoundDispositionInput,
    EvidenceAssessment,
    EvidenceConfidence,
    HistoryRisk,
    ImageAnalysisTarget,
    ImageEvidence,
    ImageRef,
    IssueType,
    RiskFlag,
    Severity,
    VisibleObject,
)


def image_ref(image_id: str = "img_1") -> ImageRef:
    return ImageRef(image_path=f"images/test/case_001/{image_id}.jpg")


def target(
    *,
    object_part=CarPart.FRONT_BUMPER,
    issue_type=IssueType.BROKEN_PART,
) -> ImageAnalysisTarget:
    return ImageAnalysisTarget(
        claim_object=ClaimObject.CAR,
        object_part=object_part,
        issue_type=issue_type,
    )


def image_evidence(
    *,
    image_id: str = "img_1",
    object_part=CarPart.FRONT_BUMPER,
    issue_type=IssueType.BROKEN_PART,
    visible_parts=None,
    damage_visible: bool = True,
    valid_image: bool = True,
    risk_flags=(RiskFlag.NONE,),
    severity=Severity.LOW,
    visible_object=VisibleObject.CAR,
) -> ImageEvidence:
    return ImageEvidence(
        image=image_ref(image_id),
        visible_object=visible_object,
        visible_parts=tuple(visible_parts if visible_parts is not None else (object_part,)),
        issue_type=issue_type,
        object_part=object_part,
        damage_visible=damage_visible,
        valid_image=valid_image,
        risk_flags=risk_flags,
        severity=severity,
        confidence=EvidenceConfidence.HIGH,
    )


def aggregated(
    *,
    images=None,
    supporting=("img_1",),
    relevant=("img_1",),
    claim_object_match=True,
    claimed_part_visible=True,
    visible_issue_type=IssueType.BROKEN_PART,
    visible_object_part=CarPart.FRONT_BUMPER,
    damage_visible=True,
    valid_image=True,
    risk_flags=(RiskFlag.NONE,),
) -> AggregatedEvidence:
    return AggregatedEvidence(
        images=tuple(images if images is not None else (image_evidence(),)),
        relevant_image_ids=relevant,
        supporting_image_ids=supporting,
        claim_object_match=claim_object_match,
        claimed_part_visible=claimed_part_visible,
        visible_issue_type=visible_issue_type,
        visible_object_part=visible_object_part,
        damage_visible=damage_visible,
        valid_image=valid_image,
        risk_flags=risk_flags,
        summary="test fixture",
    )


def evidence(
    *,
    standard_met: bool = True,
    valid_image: bool = True,
    risk_flags=(RiskFlag.NONE,),
) -> EvidenceAssessment:
    return EvidenceAssessment(
        evidence_standard_met=standard_met,
        evidence_standard_met_reason="fixture evidence reason",
        matched_requirement_ids=("REQ_TEST",),
        minimum_image_evidence="fixture requirement",
        valid_image=valid_image,
        risk_flags=risk_flags,
    )


class DispositionTests(unittest.TestCase):
    def setUp(self):
        self.engine = DispositionEngine()

    def decide(self, **overrides):
        params = {
            "user_id": "user_001",
            "target": target(),
            "aggregated": aggregated(),
            "evidence": evidence(),
        }
        params.update(overrides)
        return self.engine.decide(**params)

    def test_supported_path(self):
        result = self.decide()

        self.assertEqual(ClaimStatus.SUPPORTED, result.claim_status)
        self.assertEqual(("img_1",), result.supporting_image_ids)
        self.assertEqual(Severity.LOW, result.severity)

    def test_insufficient_evidence_forces_not_enough_information(self):
        result = self.decide(evidence=evidence(standard_met=False))

        self.assertEqual(ClaimStatus.NOT_ENOUGH_INFORMATION, result.claim_status)
        self.assertEqual(("none",), result.supporting_image_ids)
        self.assertEqual(Severity.UNKNOWN, result.severity)

    def test_damage_not_visible_contradicts_when_target_part_visible(self):
        result = self.decide(
            aggregated=aggregated(
                supporting=("none",),
                visible_issue_type=IssueType.NONE,
                damage_visible=False,
                risk_flags=(RiskFlag.DAMAGE_NOT_VISIBLE,),
                images=(
                    image_evidence(
                        issue_type=IssueType.NONE,
                        damage_visible=False,
                        severity=Severity.NONE,
                    ),
                ),
            )
        )

        self.assertEqual(ClaimStatus.CONTRADICTED, result.claim_status)
        self.assertEqual(IssueType.NONE, result.issue_type)
        self.assertEqual(Severity.NONE, result.severity)

    def test_wrong_object_with_sufficient_evidence_is_contradicted(self):
        result = self.decide(
            aggregated=aggregated(
                claim_object_match=False,
                risk_flags=(RiskFlag.WRONG_OBJECT,),
                supporting=("none",),
            )
        )

        self.assertEqual(ClaimStatus.CONTRADICTED, result.claim_status)
        self.assertIn(RiskFlag.WRONG_OBJECT, result.risk_flags)
        self.assertIn(RiskFlag.CLAIM_MISMATCH, result.risk_flags)

    def test_wrong_object_with_insufficient_evidence_stays_not_enough_information(self):
        result = self.decide(
            evidence=evidence(standard_met=False),
            aggregated=aggregated(
                claim_object_match=False,
                risk_flags=(RiskFlag.WRONG_OBJECT,),
                supporting=("none",),
            ),
        )

        self.assertEqual(ClaimStatus.NOT_ENOUGH_INFORMATION, result.claim_status)

    def test_target_part_not_visible_is_not_enough_information(self):
        result = self.decide(
            aggregated=aggregated(
                claimed_part_visible=False,
                visible_issue_type=IssueType.UNKNOWN,
                visible_object_part=CarPart.REAR_BUMPER,
                damage_visible=False,
                supporting=("none",),
                risk_flags=(RiskFlag.WRONG_OBJECT_PART,),
            )
        )

        self.assertEqual(ClaimStatus.NOT_ENOUGH_INFORMATION, result.claim_status)
        self.assertIn(RiskFlag.WRONG_OBJECT_PART, result.risk_flags)

    def test_different_part_damaged_is_contradicted_claim_mismatch(self):
        result = self.decide(
            aggregated=aggregated(
                claimed_part_visible=False,
                visible_issue_type=IssueType.DENT,
                visible_object_part=CarPart.REAR_BUMPER,
                damage_visible=True,
                supporting=("none",),
                risk_flags=(RiskFlag.WRONG_OBJECT_PART,),
                images=(
                    image_evidence(
                        object_part=CarPart.REAR_BUMPER,
                        visible_parts=(CarPart.REAR_BUMPER,),
                        issue_type=IssueType.DENT,
                        severity=Severity.MEDIUM,
                    ),
                ),
            )
        )

        self.assertEqual(ClaimStatus.CONTRADICTED, result.claim_status)
        self.assertEqual(IssueType.DENT, result.issue_type)
        self.assertEqual(CarPart.REAR_BUMPER, result.object_part)
        self.assertIn(RiskFlag.CLAIM_MISMATCH, result.risk_flags)

    def test_claim_mismatch_blocks_support(self):
        result = self.decide(
            aggregated=aggregated(risk_flags=(RiskFlag.CLAIM_MISMATCH,))
        )

        self.assertNotEqual(ClaimStatus.SUPPORTED, result.claim_status)
        self.assertEqual(ClaimStatus.NOT_ENOUGH_INFORMATION, result.claim_status)

    def test_valid_image_independence(self):
        result = self.decide(
            aggregated=aggregated(valid_image=False),
            evidence=evidence(valid_image=False),
        )

        self.assertEqual(ClaimStatus.SUPPORTED, result.claim_status)
        self.assertFalse(result.valid_image)

    def test_history_firewall_merges_flags_without_changing_status(self):
        history = HistoryRisk(
            user_id="user_001",
            user_found=True,
            risk_flags=(RiskFlag.USER_HISTORY_RISK, RiskFlag.MANUAL_REVIEW_REQUIRED),
            rationale="fixture",
        )

        result = self.decide(history=history)

        self.assertEqual(ClaimStatus.SUPPORTED, result.claim_status)
        self.assertIn(RiskFlag.USER_HISTORY_RISK, result.risk_flags)
        self.assertIn(RiskFlag.MANUAL_REVIEW_REQUIRED, result.risk_flags)

    def test_missing_history_is_safe(self):
        result = self.decide(history=None)

        self.assertEqual(ClaimStatus.SUPPORTED, result.claim_status)
        self.assertEqual((RiskFlag.NONE,), result.risk_flags)

    def test_supporting_image_validation_blocks_impossible_supported_output(self):
        result = self.decide(
            aggregated=aggregated(supporting=("none",), damage_visible=True)
        )

        self.assertNotEqual(ClaimStatus.SUPPORTED, result.claim_status)

    def test_supported_unknown_perception_severity_stays_unknown(self):
        result = self.decide(
            aggregated=aggregated(
                images=(image_evidence(severity=Severity.UNKNOWN),),
            )
        )

        self.assertEqual(ClaimStatus.SUPPORTED, result.claim_status)
        self.assertEqual(Severity.UNKNOWN, result.severity)

    def test_issue_type_none_forces_severity_none(self):
        result = self.decide(
            aggregated=aggregated(
                supporting=("none",),
                visible_issue_type=IssueType.NONE,
                damage_visible=False,
                images=(image_evidence(issue_type=IssueType.NONE, damage_visible=False, severity=Severity.NONE),),
            )
        )

        self.assertEqual(ClaimStatus.CONTRADICTED, result.claim_status)
        self.assertEqual(Severity.NONE, result.severity)

    def test_sufficient_secondary_contradiction_overrides_primary_support(self):
        secondary = CompoundDispositionInput(
            target=target(object_part=CarPart.REAR_BUMPER, issue_type=IssueType.DENT),
            aggregated=aggregated(
                supporting=("none",),
                visible_issue_type=IssueType.NONE,
                visible_object_part=CarPart.REAR_BUMPER,
                damage_visible=False,
                images=(
                    image_evidence(
                        object_part=CarPart.REAR_BUMPER,
                        visible_parts=(CarPart.REAR_BUMPER,),
                        issue_type=IssueType.NONE,
                        damage_visible=False,
                        severity=Severity.NONE,
                    ),
                ),
            ),
            evidence=evidence(standard_met=True),
        )

        result = self.decide(secondary_results=(secondary,))

        self.assertEqual(ClaimStatus.CONTRADICTED, result.claim_status)
        self.assertEqual(CarPart.REAR_BUMPER, result.object_part)

    def test_insufficient_secondary_does_not_override_primary_support(self):
        secondary = CompoundDispositionInput(
            target=target(object_part=CarPart.REAR_BUMPER, issue_type=IssueType.DENT),
            aggregated=aggregated(
                supporting=("none",),
                visible_issue_type=IssueType.NONE,
                visible_object_part=CarPart.REAR_BUMPER,
                damage_visible=False,
            ),
            evidence=evidence(standard_met=False),
        )

        result = self.decide(secondary_results=(secondary,))

        self.assertEqual(ClaimStatus.SUPPORTED, result.claim_status)
        self.assertEqual(CarPart.FRONT_BUMPER, result.object_part)

    def test_no_llm_or_decision_layer_import_guardrail(self):
        source = (CODE_ROOT / "pipeline" / "disposition.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        self.assertTrue(PROHIBITED_IMPORTS.isdisjoint(imports))
        self.assertNotIn("claim_status_justification", source)
        self.assertNotIn("analyze_image", source)
        self.assertNotIn("VerificationPolicy", source)


if __name__ == "__main__":
    unittest.main()

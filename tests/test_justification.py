from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_ROOT))

from pipeline.justification import JustificationEngine, PROHIBITED_IMPORTS, audit_justification
from schemas import CarPart, ClaimObject, ClaimStatus, Disposition, IssueType, RiskFlag, Severity


def disposition(
    *,
    status=ClaimStatus.SUPPORTED,
    issue=IssueType.DENT,
    part=CarPart.DOOR,
    evidence_met=True,
    reason="The relevant part is visible",
    risks=(RiskFlag.NONE,),
    image_ids=("img_1",),
    valid_image=True,
    severity=Severity.LOW,
) -> Disposition:
    return Disposition(
        user_id="user_001",
        claim_object=ClaimObject.CAR,
        evidence_standard_met=evidence_met,
        evidence_standard_met_reason=reason,
        risk_flags=risks,
        issue_type=issue,
        object_part=part,
        claim_status=status,
        supporting_image_ids=image_ids,
        valid_image=valid_image,
        severity=severity,
    )


class JustificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = JustificationEngine()

    def test_engine_input_is_disposition_only(self):
        signature = inspect.signature(JustificationEngine.explain)
        self.assertEqual(["self", "disposition"], list(signature.parameters))

    def test_supported_justification_explains_locked_decision(self):
        result = self.engine.explain(disposition())

        self.assertIn("locked decision is supported", result.claim_status_justification)
        self.assertIn("dent", result.claim_status_justification)
        self.assertIn("door", result.claim_status_justification)
        self.assertEqual(("img_1",), result.cited_image_ids)
        self.assertTrue(audit_justification(result)[0])

    def test_contradicted_justification_explains_locked_decision(self):
        result = self.engine.explain(
            disposition(
                status=ClaimStatus.CONTRADICTED,
                issue=IssueType.SCRATCH,
                risks=(RiskFlag.CLAIM_MISMATCH,),
                severity=Severity.LOW,
            )
        )

        text = result.claim_status_justification
        self.assertIn("locked decision is contradicted", text)
        self.assertIn("scratch", text)
        self.assertIn("claim mismatch", text)
        self.assertTrue(audit_justification(result)[0])

    def test_not_enough_information_justification(self):
        result = self.engine.explain(
            disposition(
                status=ClaimStatus.NOT_ENOUGH_INFORMATION,
                issue=IssueType.UNKNOWN,
                evidence_met=False,
                reason="The target part is not visible",
                image_ids=("none",),
                severity=Severity.UNKNOWN,
            )
        )

        text = result.claim_status_justification
        self.assertIn("locked decision is not enough information", text)
        self.assertIn("target part is not visible", text)
        self.assertEqual(("none",), result.cited_image_ids)
        self.assertTrue(audit_justification(result)[0])

    def test_issue_type_none_mentions_no_matching_damage(self):
        result = self.engine.explain(
            disposition(
                status=ClaimStatus.CONTRADICTED,
                issue=IssueType.NONE,
                severity=Severity.NONE,
            )
        )

        self.assertIn("no matching damage is visible", result.claim_status_justification)
        self.assertTrue(audit_justification(result)[0])

    def test_severity_none_does_not_invent_damage_severity(self):
        result = self.engine.explain(
            disposition(
                status=ClaimStatus.CONTRADICTED,
                issue=IssueType.NONE,
                severity=Severity.NONE,
            )
        )

        text = f" {result.claim_status_justification.lower()} "
        self.assertNotIn(" low ", text)
        self.assertNotIn(" medium ", text)
        self.assertNotIn(" high ", text)
        self.assertTrue(audit_justification(result)[0])

    def test_fallback_template_is_always_used(self):
        result = self.engine.explain(disposition())

        self.assertTrue(result.fallback_used)
        self.assertGreater(len(result.claim_status_justification), 20)

    def test_audit_catches_status_contradiction(self):
        result = self.engine.explain(disposition())
        bad = result.model_copy(update={"claim_status_justification": "The locked decision is contradicted."})

        passed, violations = audit_justification(bad)

        self.assertFalse(passed)
        self.assertIn("supported justification contains contradicted", violations)

    def test_audit_catches_issue_type_none_contradiction(self):
        result = self.engine.explain(
            disposition(status=ClaimStatus.CONTRADICTED, issue=IssueType.NONE, severity=Severity.NONE)
        )
        bad = result.model_copy(update={"claim_status_justification": "The locked decision is contradicted because image img_1 shows dent on the door."})

        passed, violations = audit_justification(bad)

        self.assertFalse(passed)
        self.assertIn("issue_type=none must describe absence of visible matching damage", violations)

    def test_no_status_generation_or_mutation(self):
        locked = disposition(status=ClaimStatus.CONTRADICTED, issue=IssueType.SCRATCH, severity=Severity.LOW)
        result = self.engine.explain(locked)

        self.assertIs(result.disposition, locked)
        self.assertEqual(ClaimStatus.CONTRADICTED, result.disposition.claim_status)
        self.assertEqual(Severity.LOW, result.disposition.severity)

    def test_forbidden_imports_and_boundary_terms(self):
        source = (CODE_ROOT / "pipeline" / "justification.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        self.assertTrue(PROHIBITED_IMPORTS.isdisjoint(imports))
        self.assertNotIn("InputClaimRow", source)
        self.assertNotIn("ImageRef", source)
        self.assertNotIn("EvidenceAssessment", source)
        self.assertNotIn("ClaimUnderstanding", source)


if __name__ == "__main__":
    unittest.main()

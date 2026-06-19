from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_ROOT))

from pipeline.claim_understanding import ClaimUnderstandingEngine
from schemas import InputClaimRow, ClaimObject, IssueType

# Ground truth semantic claims for each user/case in sample_claims.csv.
# These represent what is actually asserted in the customer's text transcript.
EXPECTED_SEMANTIC_CLAIMS = {
    "user_001": {"part": "rear_bumper", "issue": "dent", "compound": False},
    "user_002": {"part": "front_bumper", "issue": "scratch", "compound": False},
    "user_004": {"part": "windshield", "issue": "crack", "compound": False},
    "user_007": {"part": "side_mirror", "issue": "broken_part", "compound": False},
    "user_005": {"part": "rear_bumper", "issue": "broken_part", "compound": False},
    "user_006": {"part": "headlight", "issue": "crack", "compound": False},
    "user_003": {"part": "door", "issue": "dent", "compound": False},
    "user_008": {"part": "hood", "issue": "scratch", "compound": False},
    "user_009": {"part": "screen", "issue": "crack", "compound": False},
    "user_010": {"part": "hinge", "issue": "broken_part", "compound": True},
    "user_011": {"part": "keyboard", "issue": "stain", "compound": False},
    "user_012": {"part": "corner", "issue": "dent", "compound": False},
    "user_018": {"part": "screen", "issue": "glass_shatter", "compound": False},
    "user_020": {"part": "trackpad", "issue": "broken_part", "compound": False},
    "user_015": {"part": "package_corner", "issue": "crushed_packaging", "compound": False},
    "user_030": {"part": "seal", "issue": "torn_packaging", "compound": False},
    "user_031": {"part": "package_side", "issue": "water_damage", "compound": False},
    "user_032": {"part": "contents", "issue": "missing_part", "compound": False},
    "user_033": {"part": "box", "issue": "crushed_packaging", "compound": False},
    "user_034": {"part": "seal", "issue": "torn_packaging", "compound": False},
}

class ClaimUnderstandingDatasetTests(unittest.TestCase):
    def test_dataset_extraction_accuracy(self):
        engine = ClaimUnderstandingEngine()
        csv_path = PROJECT_ROOT / "dataset" / "sample_claims.csv"
        
        self.assertTrue(csv_path.exists(), f"Sample claims file not found at {csv_path}")
        
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            
        print("\n" + "="*80)
        print("CLAIM UNDERSTANDING ENGINE DATASET DIAGNOSTIC REPORT")
        print("="*80)
        
        matches_part = 0
        matches_issue = 0
        matches_compound = 0
        unknown_count = 0
        total_rows = len(reader)
        
        row_diagnostics = []
        
        for i, row in enumerate(reader, 1):
            input_row = InputClaimRow.from_csv_row(row)
            user_id = input_row.user_id
            
            # Execute extraction
            understanding = engine.extract(input_row)
            
            # Get semantic expectation
            expect = EXPECTED_SEMANTIC_CLAIMS.get(user_id)
            if not expect:
                print(f"Warning: No semantic expectation for user {user_id}")
                continue
                
            actual_part = understanding.primary_claim.object_part.value
            actual_issue = understanding.primary_claim.issue_type.value
            actual_compound = understanding.is_compound
            
            expected_part = expect["part"]
            expected_issue = expect["issue"]
            expected_compound = expect["compound"]
            
            part_ok = (actual_part == expected_part)
            issue_ok = (actual_issue == expected_issue)
            compound_ok = (actual_compound == expected_compound)
            
            if part_ok:
                matches_part += 1
            if issue_ok:
                matches_issue += 1
            if compound_ok:
                matches_compound += 1
                
            is_unknown = (actual_issue == "unknown" or actual_part == "unknown")
            if is_unknown:
                unknown_count += 1
                
            mismatch_reasons = []
            if not part_ok:
                mismatch_reasons.append(f"part: expected {expected_part!r}, got {actual_part!r}")
            if not issue_ok:
                mismatch_reasons.append(f"issue: expected {expected_issue!r}, got {actual_issue!r}")
            if not compound_ok:
                mismatch_reasons.append(f"compound: expected {expected_compound}, got {actual_compound}")
                
            status = "PASS" if (part_ok and issue_ok and compound_ok) else "FAIL"
            reason_str = "; ".join(mismatch_reasons) if mismatch_reasons else "All matched"
            
            print(f"Row {i:02d} ({user_id}): {status} | Part: {actual_part} | Issue: {actual_issue} | Compound: {actual_compound} | Reason: {reason_str}")
            row_diagnostics.append({
                "row_num": i,
                "user_id": user_id,
                "part_ok": part_ok,
                "issue_ok": issue_ok,
                "compound_ok": compound_ok,
                "is_unknown": is_unknown,
                "reason": reason_str
            })
            
        part_acc = (matches_part / total_rows) * 100
        issue_acc = (matches_issue / total_rows) * 100
        compound_acc = (matches_compound / total_rows) * 100
        unknown_rate = (unknown_count / total_rows) * 100
        
        print("-"*80)
        print("SUMMARY METRICS:")
        print(f"  Part Extraction Accuracy: {part_acc:.1f}% ({matches_part}/{total_rows})")
        print(f"  Issue Extraction Accuracy: {issue_acc:.1f}% ({matches_issue}/{total_rows})")
        print(f"  Compound Detection Accuracy: {compound_acc:.1f}% ({matches_compound}/{total_rows})")
        print(f"  Unknown Rate: {unknown_rate:.1f}% ({unknown_count}/{total_rows})")
        print("="*80)
        
        # We assert a high-quality regression guardrail based on actual performance.
        # Guardrail: Part accuracy >= 95%, Issue accuracy >= 95%
        self.assertGreaterEqual(part_acc, 95.0, "Part extraction accuracy below baseline guardrail")
        self.assertGreaterEqual(issue_acc, 95.0, "Issue extraction accuracy below baseline guardrail")

if __name__ == "__main__":
    unittest.main()

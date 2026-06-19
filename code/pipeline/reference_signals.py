from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from schemas import (
    AggregatedEvidence,
    ClaimObject,
    EvidenceAssessment,
    HistoryRisk,
    ImageAnalysisTarget,
    IssueType,
    ObjectPart,
    RiskFlag,
    validate_risk_flags,
)

logger = logging.getLogger(__name__)

# Module-level caches
_user_history_cache: dict[str, dict[str, Any]] | None = None
_requirements_cache: list[dict[str, str]] | None = None


def get_default_workspace_root() -> Path:
    """Returns the workspace root directory (three levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent


def clear_caches() -> None:
    """Clears the in-memory caches. Useful for unit testing."""
    global _user_history_cache, _requirements_cache
    _user_history_cache = None
    _requirements_cache = None


def _load_user_history(db_path: Path) -> dict[str, dict[str, Any]]:
    """Loads and parses the user history CSV into a dictionary."""
    cache = {}
    if not db_path.exists():
        raise FileNotFoundError(f"User history file not found at: {db_path}")

    with open(db_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            user_id = row.get("user_id", "").strip()
            if not user_id:
                continue

            # Parse past_claim_count
            try:
                past_claim_count = int(row.get("past_claim_count", 0))
                if past_claim_count < 0:
                    past_claim_count = 0
            except (ValueError, TypeError):
                past_claim_count = 0

            # Parse last_90_days_claim_count
            try:
                last_90_days_claim_count = int(row.get("last_90_days_claim_count", 0))
                if last_90_days_claim_count < 0:
                    last_90_days_claim_count = 0
            except (ValueError, TypeError):
                last_90_days_claim_count = 0

            # Parse history flags
            raw_flags = row.get("history_flags", "").strip()
            # Allowed history flags according to schemas.py HistoryRisk
            allowed_flags = {RiskFlag.NONE, RiskFlag.USER_HISTORY_RISK, RiskFlag.MANUAL_REVIEW_REQUIRED}
            parsed_flags = []
            if raw_flags:
                for flag_str in raw_flags.split(";"):
                    flag_str = flag_str.strip()
                    if not flag_str:
                        continue
                    try:
                        flag_enum = RiskFlag(flag_str)
                        if flag_enum in allowed_flags:
                            parsed_flags.append(flag_enum)
                    except ValueError:
                        # Ignore invalid flags to avoid crashing
                        pass

            if not parsed_flags:
                parsed_flags = [RiskFlag.NONE]

            cache[user_id.lower()] = {
                "user_id": user_id,  # Preserve original casing
                "past_claim_count": past_claim_count,
                "last_90_days_claim_count": last_90_days_claim_count,
                "history_flags": tuple(parsed_flags),
                "history_summary": row.get("history_summary", "").strip() or "No notable history summary.",
            }
    return cache


def _load_evidence_requirements(db_path: Path) -> list[dict[str, str]]:
    """Loads and parses the evidence requirements CSV."""
    cache = []
    if not db_path.exists():
        raise FileNotFoundError(f"Evidence requirements file not found at: {db_path}")

    with open(db_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            req_id = row.get("requirement_id", "").strip()
            if not req_id:
                continue
            cache.append({
                "requirement_id": req_id,
                "claim_object": row.get("claim_object", "").strip().lower(),
                "applies_to": row.get("applies_to", "").strip().lower(),
                "minimum_image_evidence": row.get("minimum_image_evidence", "").strip(),
            })
    return cache


class HistoryRiskResolver:
    """Sole owner of user history risk evaluation.

    Preserves the history firewall by not accessing claim text, images, or final status.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        global _user_history_cache
        if db_path is None:
            self.db_path = get_default_workspace_root() / "dataset" / "user_history.csv"
        else:
            self.db_path = Path(db_path)

        if _user_history_cache is None:
            _user_history_cache = _load_user_history(self.db_path)

    def resolve(self, user_id: str) -> HistoryRisk:
        """Resolves history risk for a user.

        If user_id is missing or malformed, defaults to user_found=False.
        """
        user_key = user_id.strip().lower()
        record = _user_history_cache.get(user_key)

        if not record:
            return HistoryRisk(
                user_id=user_id,
                user_found=False,
                past_claim_count=0,
                last_90_days_claim_count=0,
                risk_flags=(RiskFlag.NONE,),
                rationale="User not found in claim history database.",
            )

        return HistoryRisk(
            user_id=record["user_id"],
            user_found=True,
            past_claim_count=record["past_claim_count"],
            last_90_days_claim_count=record["last_90_days_claim_count"],
            risk_flags=record["history_flags"],
            rationale=record["history_summary"],
        )


class EvidenceValidator:
    """Determines evidence standard met based on minimum requirements and aggregated facts.

    Never owns or influences claim_status or disposition.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        global _requirements_cache
        if db_path is None:
            self.db_path = get_default_workspace_root() / "dataset" / "evidence_requirements.csv"
        else:
            self.db_path = Path(db_path)

        if _requirements_cache is None:
            _requirements_cache = _load_evidence_requirements(self.db_path)

    def evaluate(
        self,
        target: ImageAnalysisTarget,
        aggregated: AggregatedEvidence,
    ) -> EvidenceAssessment:
        """Validates if aggregated evidence satisfies minimum image requirements."""
        applicable_reqs = []
        is_multi_image = len(aggregated.images) > 1
        target_part = target.object_part.value

        # Match applicable requirements
        for req in _requirements_cache:
            req_object = req["claim_object"]
            applies_to = req["applies_to"]

            # Match object type
            if req_object != "all" and req_object != target.claim_object.value:
                continue

            # Match conditions
            applies = False
            if applies_to == "general claim review":
                applies = True
            elif applies_to == "reviewability":
                applies = True
            elif applies_to == "multi-image rows":
                applies = is_multi_image
            elif applies_to == "dent or scratch":
                applies = (target.claim_object == ClaimObject.CAR and 
                           target.issue_type in {IssueType.DENT, IssueType.SCRATCH})
            elif applies_to == "crack, broken, or missing part":
                applies = (target.claim_object == ClaimObject.CAR and 
                           target.issue_type in {IssueType.CRACK, IssueType.GLASS_SHATTER, 
                                                 IssueType.BROKEN_PART, IssueType.MISSING_PART})
            elif applies_to == "vehicle identity or orientation":
                applies = (target.claim_object == ClaimObject.CAR)
            elif applies_to == "screen, keyboard, or trackpad":
                applies = (target.claim_object == ClaimObject.LAPTOP and 
                           target_part in {"screen", "keyboard", "trackpad"})
            elif applies_to == "hinge, lid, corner, body, or port":
                applies = (target.claim_object == ClaimObject.LAPTOP and 
                           target_part in {"hinge", "lid", "corner", "port", "base", "body"})
            elif applies_to == "crushed, torn, or seal damage":
                applies = (target.claim_object == ClaimObject.PACKAGE and 
                           (target.issue_type in {IssueType.CRUSHED_PACKAGING, IssueType.TORN_PACKAGING} or 
                            target_part == "seal"))
            elif applies_to == "water, stain, or label damage":
                applies = (target.claim_object == ClaimObject.PACKAGE and 
                           (target.issue_type in {IssueType.WATER_DAMAGE, IssueType.STAIN} or 
                            target_part == "label"))
            elif applies_to == "contents or inner item":
                applies = (target.claim_object == ClaimObject.PACKAGE and 
                           target_part in {"contents", "item"})

            if applies:
                applicable_reqs.append(req)

        # Assess standard met conditions for each applicable requirement
        req_checks = {}
        failed_req_ids = []

        for req in applicable_reqs:
            req_id = req["requirement_id"]
            applies_to = req["applies_to"]
            met = True

            # Evaluate by applies_to condition (generic rules engine)
            if applies_to in {
                "general claim review",
                "multi-image rows",
                "dent or scratch",
                "crack, broken, or missing part",
                "screen, keyboard, or trackpad",
                "hinge, lid, corner, body, or port",
                "crushed, torn, or seal damage",
                "water, stain, or label damage"
            }:
                met = aggregated.claimed_part_visible
            elif applies_to == "vehicle identity or orientation":
                if is_multi_image and RiskFlag.WRONG_OBJECT in aggregated.risk_flags:
                    met = False
            elif applies_to == "contents or inner item":
                met = aggregated.claimed_part_visible and (RiskFlag.CROPPED_OR_OBSTRUCTED not in aggregated.risk_flags)
            elif applies_to == "reviewability":
                met = aggregated.valid_image

            req_checks[req_id] = met
            if not met:
                failed_req_ids.append(req_id)

        evidence_standard_met = len(failed_req_ids) == 0
        matched_req_ids = tuple(sorted(req["requirement_id"] for req in applicable_reqs))
        minimum_evidence = " | ".join(req["minimum_image_evidence"] for req in applicable_reqs)

        # Generate evidence reason
        if evidence_standard_met:
            reason = f"The claimed part is visible and the evidence is sufficient to evaluate the {target.claim_object.value} claim."
        else:
            if not aggregated.claimed_part_visible:
                reason = f"The claimed part '{target.object_part.value}' is not visible in the submitted images."
            elif is_multi_image and RiskFlag.WRONG_OBJECT in aggregated.risk_flags:
                reason = "The submitted images show different objects, violating vehicle/object identity requirements."
            elif target_part in {"contents", "item"} and RiskFlag.CROPPED_OR_OBSTRUCTED in aggregated.risk_flags:
                reason = "The package contents are unclear or obstructed, so the missing contents cannot be verified."
            elif not aggregated.valid_image:
                reason = "No usable or valid images were submitted to review the claim."
            else:
                reason = f"The submitted evidence does not meet the minimum requirements: {', '.join(failed_req_ids)}."

        # Propagate validator-specific risk flags
        new_risk_flags = list(aggregated.risk_flags)
        if not evidence_standard_met:
            if not aggregated.claimed_part_visible:
                if RiskFlag.WRONG_OBJECT_PART not in new_risk_flags:
                    new_risk_flags.append(RiskFlag.WRONG_OBJECT_PART)
                if RiskFlag.WRONG_ANGLE not in new_risk_flags:
                    new_risk_flags.append(RiskFlag.WRONG_ANGLE)
            if is_multi_image and RiskFlag.WRONG_OBJECT in aggregated.risk_flags:
                if RiskFlag.CLAIM_MISMATCH not in new_risk_flags:
                    new_risk_flags.append(RiskFlag.CLAIM_MISMATCH)

        # Ensure enums format correctly
        final_flags = []
        for flag in new_risk_flags:
            if flag == RiskFlag.NONE:
                continue
            if flag not in final_flags:
                final_flags.append(flag)

        if not final_flags:
            final_flags = [RiskFlag.NONE]

        return EvidenceAssessment(
            evidence_standard_met=evidence_standard_met,
            evidence_standard_met_reason=reason,
            matched_requirement_ids=matched_req_ids,
            minimum_image_evidence=minimum_evidence,
            valid_image=aggregated.valid_image,
            risk_flags=tuple(final_flags),
        )

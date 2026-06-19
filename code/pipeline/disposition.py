from __future__ import annotations

from collections.abc import Sequence

from schemas import (
    AggregatedEvidence,
    CarPart,
    ClaimObject,
    ClaimStatus,
    CompoundDispositionInput,
    Disposition,
    EvidenceAssessment,
    HistoryRisk,
    ImageAnalysisTarget,
    ImageEvidence,
    IssueType,
    LaptopPart,
    ObjectPart,
    PackagePart,
    RiskFlag,
    Severity,
)


CONCRETE_ISSUES = {
    IssueType.DENT,
    IssueType.SCRATCH,
    IssueType.CRACK,
    IssueType.GLASS_SHATTER,
    IssueType.BROKEN_PART,
    IssueType.MISSING_PART,
    IssueType.TORN_PACKAGING,
    IssueType.CRUSHED_PACKAGING,
    IssueType.WATER_DAMAGE,
    IssueType.STAIN,
}

UNKNOWN_PART_BY_OBJECT = {
    ClaimObject.CAR: CarPart.UNKNOWN,
    ClaimObject.LAPTOP: LaptopPart.UNKNOWN,
    ClaimObject.PACKAGE: PackagePart.UNKNOWN,
}

PROHIBITED_IMPORTS = frozenset(
    {
        "llm_client",
        "openai",
        "anthropic",
        "google.genai",
        "pipeline.image_analysis",
    }
)


class DispositionEngine:
    """Sole deterministic owner of final claim_status.

    Gate 1 decides whether the evidence is sufficient to evaluate the claim.
    Gate 2 decides content match from typed facts only. This module never reads
    raw claim text, images, prompts, verification policy, or justification text.
    """

    def decide(
        self,
        *,
        user_id: str,
        target: ImageAnalysisTarget,
        aggregated: AggregatedEvidence,
        evidence: EvidenceAssessment,
        history: HistoryRisk | None = None,
        secondary_results: Sequence[CompoundDispositionInput] = (),
    ) -> Disposition:
        risk_flags = _merge_risk_flags(evidence.risk_flags, aggregated.risk_flags)
        if history is not None:
            risk_flags = _merge_risk_flags(risk_flags, history.risk_flags)

        disposition = self._decide_primary(
            user_id=user_id,
            target=target,
            aggregated=aggregated,
            evidence=evidence,
            risk_flags=risk_flags,
        )
        return self._apply_compound_overrides(
            base=disposition,
            user_id=user_id,
            history=history,
            secondary_results=secondary_results,
        )

    def last_resort(
        self,
        *,
        user_id: str,
        claim_object: ClaimObject,
        reason: str,
    ) -> Disposition:
        """Crash-containment fallback owned by the disposition layer."""

        return Disposition(
            user_id=user_id,
            claim_object=claim_object,
            evidence_standard_met=False,
            evidence_standard_met_reason=reason,
            risk_flags=(RiskFlag.MANUAL_REVIEW_REQUIRED,),
            issue_type=IssueType.UNKNOWN,
            object_part=UNKNOWN_PART_BY_OBJECT[claim_object],
            claim_status=ClaimStatus.NOT_ENOUGH_INFORMATION,
            supporting_image_ids=("none",),
            valid_image=False,
            severity=Severity.UNKNOWN,
        )

    def _decide_primary(
        self,
        *,
        user_id: str,
        target: ImageAnalysisTarget,
        aggregated: AggregatedEvidence,
        evidence: EvidenceAssessment,
        risk_flags: tuple[RiskFlag, ...],
    ) -> Disposition:
        if not evidence.evidence_standard_met:
            return _build_disposition(
                user_id=user_id,
                target=target,
                aggregated=aggregated,
                evidence=evidence,
                risk_flags=risk_flags,
                claim_status=ClaimStatus.NOT_ENOUGH_INFORMATION,
                issue_type=_issue_or_unknown(aggregated.visible_issue_type),
                object_part=_part_or_target(aggregated.visible_object_part, target.object_part),
                supporting_image_ids=("none",),
                severity=Severity.UNKNOWN,
            )

        if _has_flag(risk_flags, RiskFlag.WRONG_OBJECT) or aggregated.claim_object_match is False:
            return _build_disposition(
                user_id=user_id,
                target=target,
                aggregated=aggregated,
                evidence=evidence,
                risk_flags=_merge_risk_flags(risk_flags, (RiskFlag.WRONG_OBJECT, RiskFlag.CLAIM_MISMATCH)),
                claim_status=ClaimStatus.CONTRADICTED,
                issue_type=_issue_or_target(aggregated.visible_issue_type, target.issue_type),
                object_part=_part_or_target(aggregated.visible_object_part, target.object_part),
                supporting_image_ids=_relevant_ids(aggregated),
                severity=_perception_severity_or_unknown(aggregated),
            )

        different_part_damaged = (
            aggregated.damage_visible
            and _is_concrete_issue(aggregated.visible_issue_type)
            and not _same_part(aggregated.visible_object_part, target.object_part)
        )
        if different_part_damaged:
            return _build_disposition(
                user_id=user_id,
                target=target,
                aggregated=aggregated,
                evidence=evidence,
                risk_flags=_merge_risk_flags(risk_flags, (RiskFlag.CLAIM_MISMATCH,)),
                claim_status=ClaimStatus.CONTRADICTED,
                issue_type=aggregated.visible_issue_type,
                object_part=aggregated.visible_object_part,
                supporting_image_ids=_relevant_ids(aggregated),
                severity=_perception_severity_or_unknown(aggregated),
            )

        if not aggregated.claimed_part_visible:
            return _build_disposition(
                user_id=user_id,
                target=target,
                aggregated=aggregated,
                evidence=evidence,
                risk_flags=_merge_risk_flags(risk_flags, (RiskFlag.WRONG_OBJECT_PART,)),
                claim_status=ClaimStatus.NOT_ENOUGH_INFORMATION,
                issue_type=_issue_or_unknown(aggregated.visible_issue_type),
                object_part=target.object_part,
                supporting_image_ids=("none",),
                severity=Severity.UNKNOWN,
            )

        if (
            aggregated.supporting_image_ids != ("none",)
            and aggregated.damage_visible
            and _is_concrete_issue(aggregated.visible_issue_type)
            and not _has_flag(risk_flags, RiskFlag.CLAIM_MISMATCH)
        ):
            return _build_disposition(
                user_id=user_id,
                target=target,
                aggregated=aggregated,
                evidence=evidence,
                risk_flags=risk_flags,
                claim_status=ClaimStatus.SUPPORTED,
                issue_type=aggregated.visible_issue_type,
                object_part=aggregated.visible_object_part,
                supporting_image_ids=aggregated.supporting_image_ids,
                severity=_perception_severity_or_unknown(aggregated),
            )

        if (
            _has_flag(risk_flags, RiskFlag.DAMAGE_NOT_VISIBLE)
            or aggregated.visible_issue_type == IssueType.NONE
            or not aggregated.damage_visible
        ):
            return _build_disposition(
                user_id=user_id,
                target=target,
                aggregated=aggregated,
                evidence=evidence,
                risk_flags=_merge_risk_flags(risk_flags, (RiskFlag.DAMAGE_NOT_VISIBLE,)),
                claim_status=ClaimStatus.CONTRADICTED,
                issue_type=IssueType.NONE,
                object_part=target.object_part,
                supporting_image_ids=_relevant_ids(aggregated),
                severity=Severity.NONE,
            )

        return _build_disposition(
            user_id=user_id,
            target=target,
            aggregated=aggregated,
            evidence=evidence,
            risk_flags=risk_flags,
            claim_status=ClaimStatus.NOT_ENOUGH_INFORMATION,
            issue_type=_issue_or_unknown(aggregated.visible_issue_type),
            object_part=_part_or_target(aggregated.visible_object_part, target.object_part),
            supporting_image_ids=("none",),
            severity=Severity.UNKNOWN,
        )

    def _apply_compound_overrides(
        self,
        *,
        base: Disposition,
        user_id: str,
        history: HistoryRisk | None,
        secondary_results: Sequence[CompoundDispositionInput],
    ) -> Disposition:
        final = base
        for secondary in secondary_results:
            secondary_risk_flags = _merge_risk_flags(
                secondary.evidence.risk_flags,
                secondary.aggregated.risk_flags,
                history.risk_flags if history is not None else (RiskFlag.NONE,),
            )
            secondary_disposition = self._decide_primary(
                user_id=user_id,
                target=secondary.target,
                aggregated=secondary.aggregated,
                evidence=secondary.evidence,
                risk_flags=secondary_risk_flags,
            )
            if (
                secondary.evidence.evidence_standard_met
                and secondary_disposition.claim_status == ClaimStatus.CONTRADICTED
            ):
                final = secondary_disposition.model_copy(
                    update={
                        "risk_flags": _merge_risk_flags(final.risk_flags, secondary_disposition.risk_flags),
                    }
                )
        return final


def _build_disposition(
    *,
    user_id: str,
    target: ImageAnalysisTarget,
    aggregated: AggregatedEvidence,
    evidence: EvidenceAssessment,
    risk_flags: tuple[RiskFlag, ...],
    claim_status: ClaimStatus,
    issue_type: IssueType,
    object_part: ObjectPart,
    supporting_image_ids: tuple[str, ...],
    severity: Severity,
) -> Disposition:
    return Disposition(
        user_id=user_id,
        claim_object=target.claim_object,
        evidence_standard_met=evidence.evidence_standard_met,
        evidence_standard_met_reason=evidence.evidence_standard_met_reason,
        risk_flags=risk_flags,
        issue_type=issue_type,
        object_part=object_part,
        claim_status=claim_status,
        supporting_image_ids=_ids_or_none(supporting_image_ids),
        valid_image=aggregated.valid_image and evidence.valid_image,
        severity=severity,
    )


def _merge_risk_flags(*flag_groups: tuple[RiskFlag, ...]) -> tuple[RiskFlag, ...]:
    merged: list[RiskFlag] = []
    for flags in flag_groups:
        for flag in flags:
            if flag == RiskFlag.NONE:
                continue
            if flag not in merged:
                merged.append(flag)
    return tuple(merged) if merged else (RiskFlag.NONE,)


def _ids_or_none(image_ids: tuple[str, ...]) -> tuple[str, ...]:
    ids = tuple(image_id for image_id in image_ids if image_id != "none")
    return ids if ids else ("none",)


def _relevant_ids(aggregated: AggregatedEvidence) -> tuple[str, ...]:
    if aggregated.relevant_image_ids != ("none",):
        return aggregated.relevant_image_ids
    if aggregated.supporting_image_ids != ("none",):
        return aggregated.supporting_image_ids
    return ("none",)


def _has_flag(risk_flags: tuple[RiskFlag, ...], flag: RiskFlag) -> bool:
    return flag in risk_flags


def _is_concrete_issue(issue_type: IssueType) -> bool:
    return issue_type in CONCRETE_ISSUES


def _same_part(left: ObjectPart, right: ObjectPart) -> bool:
    return left.value == right.value


def _issue_or_unknown(issue_type: IssueType) -> IssueType:
    return issue_type if issue_type != IssueType.NONE else IssueType.UNKNOWN


def _issue_or_target(issue_type: IssueType, target_issue: IssueType) -> IssueType:
    return issue_type if issue_type != IssueType.UNKNOWN else target_issue


def _part_or_target(part: ObjectPart, target_part: ObjectPart) -> ObjectPart:
    return part if part.value != "unknown" else target_part


def _perception_severity_or_unknown(aggregated: AggregatedEvidence) -> Severity:
    for image in _candidate_images_for_severity(aggregated):
        if image.severity not in {Severity.UNKNOWN, Severity.NONE}:
            return image.severity
    return Severity.UNKNOWN


def _candidate_images_for_severity(aggregated: AggregatedEvidence) -> tuple[ImageEvidence, ...]:
    preferred_ids = set()
    if aggregated.supporting_image_ids != ("none",):
        preferred_ids.update(aggregated.supporting_image_ids)
    elif aggregated.relevant_image_ids != ("none",):
        preferred_ids.update(aggregated.relevant_image_ids)

    if preferred_ids:
        preferred = tuple(image for image in aggregated.images if image.image.image_id in preferred_ids)
        if preferred:
            return preferred
    return aggregated.images

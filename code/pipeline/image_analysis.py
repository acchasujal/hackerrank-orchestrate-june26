from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from schemas import (
    AggregatedEvidence,
    CarPart,
    ClaimObject,
    EvidenceConfidence,
    ImageAnalysisTarget,
    ImageEvidence,
    ImageRef,
    IssueType,
    LaptopPart,
    ObjectPart,
    PackagePart,
    RiskFlag,
    Severity,
    VerificationRecommendation,
    VisibleObject,
    validate_risk_flags,
)


class ImagePerceptionClient(Protocol):
    """Claim-blind image perception provider.

    Implementations may call a VLM, read cached structured output, or use a
    local fixture. They must not receive raw claim text or ClaimUnderstanding.
    """

    def analyze_image(self, image: ImageRef) -> Mapping[str, Any]:
        """Return objective structured facts for one image."""

    def analyze_images(self, images: Sequence[ImageRef]) -> Sequence[Mapping[str, Any]]:
        """Return objective structured facts for multiple images in a single call."""


UNKNOWN_PART_BY_OBJECT: dict[VisibleObject, ObjectPart] = {
    VisibleObject.CAR: CarPart.UNKNOWN,
    VisibleObject.LAPTOP: LaptopPart.UNKNOWN,
    VisibleObject.PACKAGE: PackagePart.UNKNOWN,
    VisibleObject.UNKNOWN: CarPart.UNKNOWN,
}

VISIBLE_OBJECT_BY_CLAIM_OBJECT: dict[ClaimObject, VisibleObject] = {
    ClaimObject.CAR: VisibleObject.CAR,
    ClaimObject.LAPTOP: VisibleObject.LAPTOP,
    ClaimObject.PACKAGE: VisibleObject.PACKAGE,
}

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

DISQUALIFYING_SUPPORT_FLAGS = {
    RiskFlag.WRONG_OBJECT,
    RiskFlag.WRONG_OBJECT_PART,
    RiskFlag.CLAIM_MISMATCH,
    RiskFlag.POSSIBLE_MANIPULATION,
    RiskFlag.NON_ORIGINAL_IMAGE,
}

DEFAULT_VERIFICATION_TRIGGERS = {
    RiskFlag.CLAIM_MISMATCH,
    RiskFlag.POSSIBLE_MANIPULATION,
    RiskFlag.NON_ORIGINAL_IMAGE,
    RiskFlag.TEXT_INSTRUCTION_PRESENT,
    RiskFlag.WRONG_OBJECT,
}


def _dedupe_flags(flags: Sequence[RiskFlag]) -> tuple[RiskFlag, ...]:
    ordered: list[RiskFlag] = []
    for flag in flags:
        if flag == RiskFlag.NONE:
            continue
        if flag not in ordered:
            ordered.append(flag)
    return tuple(ordered) if ordered else (RiskFlag.NONE,)


def _dedupe_strings(values: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for value in values:
        if value == "none":
            continue
        if value not in ordered:
            ordered.append(value)
    return tuple(ordered) if ordered else ("none",)


def _enum_value(enum_type: type[Any], value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return enum_type(value)
    except ValueError:
        return default


def _visible_object_matches_target(image: ImageEvidence, target: ImageAnalysisTarget) -> bool | None:
    if image.visible_object == VisibleObject.UNKNOWN:
        return None
    return image.visible_object == VISIBLE_OBJECT_BY_CLAIM_OBJECT[target.claim_object]


def _part_matches_target(part: ObjectPart, target: ImageAnalysisTarget) -> bool:
    return part.value == target.object_part.value


def _issue_matches_target(issue_type: IssueType, target: ImageAnalysisTarget) -> bool:
    if target.issue_type == IssueType.UNKNOWN:
        return issue_type in CONCRETE_ISSUES
    if target.issue_type == IssueType.NONE:
        return issue_type == IssueType.NONE
    return issue_type == target.issue_type


def _default_part_for_visible_object(visible_object: VisibleObject) -> ObjectPart:
    return UNKNOWN_PART_BY_OBJECT.get(visible_object, CarPart.UNKNOWN)


class ImageAnalyzer:
    """Converts one claim-blind perception payload into ImageEvidence."""

    def __init__(self, perception_client: ImagePerceptionClient) -> None:
        self._perception_client = perception_client

    def analyze_image(self, image: ImageRef) -> ImageEvidence:
        payload = dict(self._perception_client.analyze_image(image))
        return self._payload_to_evidence(image, payload)

    def analyze_images(self, images: Sequence[ImageRef]) -> Sequence[ImageEvidence]:
        if not hasattr(self._perception_client, "analyze_images"):
            return [self.analyze_image(img) for img in images]
            
        payloads = self._perception_client.analyze_images(images)
        evidence_list = []
        for img, p in zip(images, payloads):
            try:
                evidence_list.append(self._payload_to_evidence(img, dict(p)))
            except Exception as e:
                # If a single image fails Pydantic validation or parsing, emit fallback for just that image
                from schemas import ImageAnalysisTarget, IssueType, ClaimObject
                from pipeline.orchestrator import _fallback_image_evidence, UNKNOWN_PART_BY_OBJECT
                # Try to extract the claim_object from the payload, default to CAR
                vo_str = dict(p).get("visible_object", "car")
                co = ClaimObject.CAR
                if vo_str == "laptop": co = ClaimObject.LAPTOP
                elif vo_str == "package": co = ClaimObject.PACKAGE
                target = ImageAnalysisTarget(claim_object=co, object_part=UNKNOWN_PART_BY_OBJECT[co], issue_type=IssueType.UNKNOWN)
                evidence_list.append(_fallback_image_evidence(img, target))
        return evidence_list

    def _payload_to_evidence(self, image: ImageRef, payload: dict[str, Any]) -> ImageEvidence:
        visible_object = _enum_value(VisibleObject, payload.get("visible_object"), VisibleObject.UNKNOWN)
        object_part = payload.get("object_part") or _default_part_for_visible_object(visible_object)
        risk_flags = list(validate_risk_flags(payload.get("risk_flags", (RiskFlag.NONE,))))

        embedded_text_detected = bool(payload.get("embedded_text_detected", False))
        if embedded_text_detected and RiskFlag.TEXT_INSTRUCTION_PRESENT not in risk_flags:
            risk_flags.append(RiskFlag.TEXT_INSTRUCTION_PRESENT)

        issue_type = _enum_value(IssueType, payload.get("issue_type"), IssueType.UNKNOWN)
        damage_visible = bool(payload.get("damage_visible", issue_type in CONCRETE_ISSUES))

        return ImageEvidence(
            image=image,
            visible_object=visible_object,
            claim_object_match=None,
            visible_parts=tuple(payload.get("visible_parts", ())),
            claimed_part_visible=False,
            issue_type=issue_type,
            object_part=object_part,
            damage_visible=damage_visible,
            valid_image=bool(payload.get("valid_image", True)),
            risk_flags=_dedupe_flags(risk_flags),
            severity=_enum_value(Severity, payload.get("severity"), Severity.UNKNOWN),
            confidence=_enum_value(EvidenceConfidence, payload.get("confidence"), EvidenceConfidence.UNKNOWN),
            embedded_text_detected=embedded_text_detected,
            embedded_text_excerpt=payload.get("embedded_text_excerpt"),
            summary=str(payload.get("summary", "")),
        )


class ImageAggregator:
    """Pure deterministic merge of per-image facts against a minimal target."""

    def aggregate(
        self,
        images: Sequence[ImageEvidence],
        target: ImageAnalysisTarget,
    ) -> AggregatedEvidence:
        if not images:
            raise ValueError("aggregate requires at least one image")

        risk_flags: list[RiskFlag] = []
        relevant_ids: list[str] = []
        supporting_ids: list[str] = []
        known_object_matches: list[bool] = []

        claimed_part_visible = False
        damage_visible = False
        best_issue = IssueType.UNKNOWN
        best_part: ObjectPart = target.object_part

        for image in images:
            risk_flags.extend(image.risk_flags)
            object_match = _visible_object_matches_target(image, target)
            if object_match is not None:
                known_object_matches.append(object_match)

            part_visible = any(_part_matches_target(part, target) for part in image.visible_parts)
            part_visible = part_visible or _part_matches_target(image.object_part, target)
            claimed_part_visible = claimed_part_visible or part_visible

            is_relevant = image.valid_image and (object_match is not False) and (
                part_visible or image.visible_object == VISIBLE_OBJECT_BY_CLAIM_OBJECT[target.claim_object]
            )
            if is_relevant:
                relevant_ids.append(image.image.image_id)

            image_has_matching_damage = (
                image.valid_image
                and object_match is not False
                and part_visible
                and image.damage_visible
                and _issue_matches_target(image.issue_type, target)
            )
            image_has_disqualifying_flag = bool(set(image.risk_flags) & DISQUALIFYING_SUPPORT_FLAGS)
            if image_has_matching_damage and not image_has_disqualifying_flag:
                supporting_ids.append(image.image.image_id)
                damage_visible = True
                best_issue = image.issue_type
                best_part = image.object_part
            elif image.damage_visible and best_issue in {IssueType.UNKNOWN, IssueType.NONE}:
                best_issue = image.issue_type
                best_part = image.object_part

        known_visible_objects = {
            image.visible_object for image in images if image.visible_object != VisibleObject.UNKNOWN
        }
        if len(known_visible_objects) > 1:
            risk_flags.extend((RiskFlag.CLAIM_MISMATCH, RiskFlag.MANUAL_REVIEW_REQUIRED))

        if known_object_matches and not any(known_object_matches):
            risk_flags.extend((RiskFlag.WRONG_OBJECT, RiskFlag.CLAIM_MISMATCH))

        if not claimed_part_visible:
            risk_flags.extend((RiskFlag.WRONG_OBJECT_PART, RiskFlag.WRONG_ANGLE))

        if not any(image.damage_visible for image in images):
            risk_flags.append(RiskFlag.DAMAGE_NOT_VISIBLE)

        valid_image = any(image.valid_image for image in images)
        claim_object_match = any(known_object_matches) if known_object_matches else None

        if supporting_ids:
            visible_issue_type = best_issue
        elif claimed_part_visible and not any(image.damage_visible for image in images):
            visible_issue_type = IssueType.NONE
        else:
            visible_issue_type = best_issue

        summary = self._build_summary(
            claim_object_match=claim_object_match,
            claimed_part_visible=claimed_part_visible,
            damage_visible=damage_visible,
            supporting_ids=supporting_ids,
        )

        return AggregatedEvidence(
            images=tuple(images),
            relevant_image_ids=_dedupe_strings(relevant_ids),
            supporting_image_ids=_dedupe_strings(supporting_ids),
            claim_object_match=claim_object_match,
            claimed_part_visible=claimed_part_visible,
            visible_issue_type=visible_issue_type,
            visible_object_part=best_part,
            damage_visible=damage_visible,
            valid_image=valid_image,
            risk_flags=_dedupe_flags(risk_flags),
            summary=summary,
        )

    @staticmethod
    def _build_summary(
        *,
        claim_object_match: bool | None,
        claimed_part_visible: bool,
        damage_visible: bool,
        supporting_ids: Sequence[str],
    ) -> str:
        if supporting_ids:
            return f"Matching damage visible in {', '.join(supporting_ids)}."
        if claim_object_match is False:
            return "No image clearly matches the claimed object."
        if not claimed_part_visible:
            return "The claimed part is not clearly visible in the submitted images."
        if not damage_visible:
            return "The claimed part is visible, but matching damage is not visible."
        return "Images contain visible damage, but it does not cleanly match the target."


class VerificationPolicy:
    """Owns API escalation recommendations and enforces a hard call budget."""

    def __init__(
        self,
        *,
        max_verification_calls: int,
        max_calls_per_row: int = 1,
        trigger_flags: set[RiskFlag] | None = None,
    ) -> None:
        if max_verification_calls < 0:
            raise ValueError("max_verification_calls must be non-negative")
        if max_calls_per_row < 0:
            raise ValueError("max_calls_per_row must be non-negative")
        self.max_verification_calls = max_verification_calls
        self.max_calls_per_row = max_calls_per_row
        self.trigger_flags = trigger_flags or set(DEFAULT_VERIFICATION_TRIGGERS)
        self.calls_used = 0

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_verification_calls - self.calls_used)

    def recommend(
        self,
        aggregated: AggregatedEvidence,
        *,
        reserve_budget: bool = True,
    ) -> VerificationRecommendation:
        budget_used_before = self.calls_used
        triggers = tuple(flag for flag in aggregated.risk_flags if flag in self.trigger_flags)
        triggers = _dedupe_flags(triggers)
        verification_needed = triggers != (RiskFlag.NONE,)
        requested_calls = min(1 if verification_needed else 0, self.max_calls_per_row)
        allowed_by_budget = requested_calls > 0 and self.remaining_calls >= requested_calls
        reserved_call_count = requested_calls if allowed_by_budget else 0

        if reserve_budget:
            self.calls_used += reserved_call_count

        reason = self._reason(
            verification_needed=verification_needed,
            allowed_by_budget=allowed_by_budget,
            triggers=triggers,
        )

        return VerificationRecommendation(
            verification_needed=verification_needed,
            allowed_by_budget=allowed_by_budget,
            reserved_call_count=reserved_call_count,
            trigger_flags=triggers,
            reason=reason,
            budget_limit=self.max_verification_calls,
            budget_used_before=budget_used_before,
            budget_remaining_after=self.remaining_calls,
        )

    @staticmethod
    def _reason(
        *,
        verification_needed: bool,
        allowed_by_budget: bool,
        triggers: tuple[RiskFlag, ...],
    ) -> str:
        if not verification_needed:
            return "No verification trigger flags were present."
        rendered = ", ".join(flag.value for flag in triggers)
        if allowed_by_budget:
            return f"Verification reserved for trigger flags: {rendered}."
        return f"Verification needed for trigger flags but blocked by budget: {rendered}."


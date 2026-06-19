from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pipeline.claim_understanding import ClaimUnderstandingEngine
from pipeline.disposition import DispositionEngine
from pipeline.image_analysis import ImageAggregator, ImageAnalyzer
from pipeline.justification import JustificationEngine
from pipeline.reference_signals import EvidenceValidator, HistoryRiskResolver
from schemas import (
    AggregatedEvidence,
    CarPart,
    ClaimObject,
    CompoundDispositionInput,
    Disposition,
    EvidenceAssessment,
    EvidenceConfidence,
    HistoryRisk,
    ImageAnalysisTarget,
    ImageEvidence,
    InputClaimRow,
    IssueType,
    LaptopPart,
    OutputPredictionRow,
    PackagePart,
    RiskFlag,
    Severity,
    VisibleObject,
)


@dataclass(frozen=True)
class RowExecutionResult:
    output: OutputPredictionRow
    errors: tuple[str, ...] = ()


UNKNOWN_PART_BY_OBJECT = {
    ClaimObject.CAR: CarPart.UNKNOWN,
    ClaimObject.LAPTOP: LaptopPart.UNKNOWN,
    ClaimObject.PACKAGE: PackagePart.UNKNOWN,
}


class ClaimReviewOrchestrator:
    """Coordinates pipeline components without owning their business logic."""

    def __init__(
        self,
        *,
        image_analyzer: ImageAnalyzer,
        claim_understanding: ClaimUnderstandingEngine | None = None,
        image_aggregator: ImageAggregator | None = None,
        history_resolver: HistoryRiskResolver | None = None,
        evidence_validator: EvidenceValidator | None = None,
        disposition_engine: DispositionEngine | None = None,
        justification_engine: JustificationEngine | None = None,
    ) -> None:
        self.claim_understanding = claim_understanding or ClaimUnderstandingEngine()
        self.image_analyzer = image_analyzer
        self.image_aggregator = image_aggregator or ImageAggregator()
        self.history_resolver = history_resolver or HistoryRiskResolver()
        self.evidence_validator = evidence_validator or EvidenceValidator()
        self.disposition_engine = disposition_engine or DispositionEngine()
        self.justification_engine = justification_engine or JustificationEngine()

    def process_row(self, row: InputClaimRow) -> RowExecutionResult:
        errors: list[str] = []
        try:
            understanding = self.claim_understanding.extract(row)
        except Exception as exc:
            errors.append(f"claim_understanding: {exc}")
            disposition = self._safe_fallback_disposition(
                row=row,
                reason="Claim understanding failed before typed extraction.",
                errors=errors,
            )
            return RowExecutionResult(output=_assemble_output(row, disposition, self.justification_engine), errors=tuple(errors))

        primary_target = ImageAnalysisTarget.from_claim(understanding.primary_claim, understanding.claim_object)

        image_evidence: list[ImageEvidence] = []
        if hasattr(self.image_analyzer, "analyze_images"):
            try:
                # Returns a sequence, so we convert it to list
                image_evidence = list(self.image_analyzer.analyze_images(row.images))
            except Exception as exc:
                # If the batch call fails completely, fallback all images
                for image in row.images:
                    errors.append(f"image_analysis_batch:{image.image_id}: {exc}")
                    image_evidence.append(_fallback_image_evidence(image, primary_target))
        else:
            for image in row.images:
                try:
                    image_evidence.append(self.image_analyzer.analyze_image(image))
                except Exception as exc:
                    errors.append(f"image_analysis:{image.image_id}: {exc}")
                    image_evidence.append(_fallback_image_evidence(image, primary_target))

        try:
            history = self.history_resolver.resolve(row.user_id)
        except Exception as exc:
            errors.append(f"history: {exc}")
            history = _fallback_history(row.user_id)

        try:
            aggregated = self.image_aggregator.aggregate(tuple(image_evidence), primary_target)
        except Exception as exc:
            errors.append(f"aggregation: {exc}")
            aggregated = _fallback_aggregation(tuple(image_evidence), primary_target)

        try:
            evidence = self.evidence_validator.evaluate(primary_target, aggregated)
        except Exception as exc:
            errors.append(f"evidence_validation: {exc}")
            evidence = _fallback_evidence(aggregated, "Evidence validation failed.")

        secondary_results = self._secondary_results(
            secondary_claims=understanding.secondary_claims,
            claim_object=understanding.claim_object,
            image_evidence=tuple(image_evidence),
            errors=errors,
        )

        try:
            disposition = self.disposition_engine.decide(
                user_id=row.user_id,
                target=primary_target,
                aggregated=aggregated,
                evidence=evidence,
                history=history,
                secondary_results=secondary_results,
            )
        except Exception as exc:
            errors.append(f"disposition: {exc}")
            disposition = self._last_resort_disposition(row, "Disposition failed after upstream processing.")

        return RowExecutionResult(output=_assemble_output(row, disposition, self.justification_engine, errors), errors=tuple(errors))

    def process_batch(self, rows: Iterable[InputClaimRow]) -> tuple[RowExecutionResult, ...]:
        return tuple(self.process_row(row) for row in rows)

    def _secondary_results(
        self,
        *,
        secondary_claims: Sequence,
        claim_object: ClaimObject,
        image_evidence: tuple[ImageEvidence, ...],
        errors: list[str],
    ) -> tuple[CompoundDispositionInput, ...]:
        results: list[CompoundDispositionInput] = []
        for index, claim in enumerate(secondary_claims):
            target = ImageAnalysisTarget.from_claim(claim, claim_object)
            try:
                aggregated = self.image_aggregator.aggregate(image_evidence, target)
            except Exception as exc:
                errors.append(f"secondary_aggregation:{index}: {exc}")
                aggregated = _fallback_aggregation(image_evidence, target)
            try:
                evidence = self.evidence_validator.evaluate(target, aggregated)
            except Exception as exc:
                errors.append(f"secondary_evidence_validation:{index}: {exc}")
                evidence = _fallback_evidence(aggregated, "Secondary evidence validation failed.")
            results.append(CompoundDispositionInput(target=target, aggregated=aggregated, evidence=evidence))
        return tuple(results)

    def _safe_fallback_disposition(
        self,
        *,
        row: InputClaimRow,
        reason: str,
        errors: Sequence[str],
    ) -> Disposition:
        target = ImageAnalysisTarget(
            claim_object=row.claim_object,
            object_part=UNKNOWN_PART_BY_OBJECT[row.claim_object],
            issue_type=IssueType.UNKNOWN,
        )
        image_evidence = tuple(_fallback_image_evidence(image, target) for image in row.images)
        aggregated = _fallback_aggregation(image_evidence, target)
        evidence = _fallback_evidence(aggregated, reason)
        history = _fallback_history(row.user_id)
        try:
            return self.disposition_engine.decide(
                user_id=row.user_id,
                target=target,
                aggregated=aggregated,
                evidence=evidence,
                history=history,
            )
        except Exception as exc:
            errors.append(f"fallback_disposition: {exc}")
            return self._last_resort_disposition(row, reason)

    def _last_resort_disposition(self, row: InputClaimRow, reason: str) -> Disposition:
        return _last_resort_disposition(row, reason)


def _assemble_output(
    row: InputClaimRow,
    disposition: Disposition,
    justification_engine: JustificationEngine,
    errors: Sequence[str] = (),
) -> OutputPredictionRow:
    try:
        justification = justification_engine.explain(disposition)
        text = justification.claim_status_justification
    except Exception as exc:
        text = f"The locked decision could not be explained by the justification layer: {exc}."
    return OutputPredictionRow.from_input_and_disposition(row, disposition, text)


def _fallback_image_evidence(image, target: ImageAnalysisTarget) -> ImageEvidence:
    return ImageEvidence(
        image=image,
        visible_object=VisibleObject.UNKNOWN,
        visible_parts=(),
        claimed_part_visible=False,
        issue_type=IssueType.UNKNOWN,
        object_part=UNKNOWN_PART_BY_OBJECT[target.claim_object],
        damage_visible=False,
        valid_image=False,
        risk_flags=(RiskFlag.MANUAL_REVIEW_REQUIRED,),
        severity=Severity.UNKNOWN,
        confidence=EvidenceConfidence.UNKNOWN,
        summary="Image analysis failed.",
    )


def _fallback_history(user_id: str) -> HistoryRisk:
    return HistoryRisk(
        user_id=user_id,
        user_found=False,
        risk_flags=(RiskFlag.NONE,),
        rationale="History lookup failed.",
    )


def _fallback_aggregation(images: tuple[ImageEvidence, ...], target: ImageAnalysisTarget) -> AggregatedEvidence:
    if not images:
        images = (_fallback_image_evidence(_fallback_image_ref(), target),)
    return AggregatedEvidence(
        images=images,
        relevant_image_ids=("none",),
        supporting_image_ids=("none",),
        claim_object_match=None,
        claimed_part_visible=False,
        visible_issue_type=IssueType.UNKNOWN,
        visible_object_part=target.object_part,
        damage_visible=False,
        valid_image=any(image.valid_image for image in images),
        risk_flags=(RiskFlag.MANUAL_REVIEW_REQUIRED,),
        summary="Aggregation failed.",
    )


def _fallback_evidence(aggregated: AggregatedEvidence, reason: str) -> EvidenceAssessment:
    return EvidenceAssessment(
        evidence_standard_met=False,
        evidence_standard_met_reason=reason,
        matched_requirement_ids=(),
        minimum_image_evidence="",
        valid_image=aggregated.valid_image,
        risk_flags=(RiskFlag.MANUAL_REVIEW_REQUIRED,),
    )


def _last_resort_disposition(row: InputClaimRow, reason: str) -> Disposition:
    return DispositionEngine().last_resort(
        user_id=row.user_id,
        claim_object=row.claim_object,
        reason=reason,
    )


def _fallback_image_ref():
    from schemas import ImageRef

    return ImageRef(image_path="images/unavailable/img_unknown.jpg")

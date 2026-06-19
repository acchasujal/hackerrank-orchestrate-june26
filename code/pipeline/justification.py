from __future__ import annotations

from schemas import ClaimStatus, Disposition, IssueType, JustificationDraft, RiskFlag, Severity


Justification = JustificationDraft

PROHIBITED_IMPORTS = frozenset(
    {
        "pipeline.disposition",
        "pipeline.image_analysis",
        "pipeline.reference_signals",
        "pipeline.claim_understanding",
        "llm_client",
        "openai",
        "anthropic",
        "google.genai",
    }
)


class JustificationEngine:
    """Explains a locked Disposition without changing or creating decisions."""

    def explain(self, disposition: Disposition) -> Justification:
        text = _template_for(disposition)
        return Justification(
            disposition=disposition,
            claim_status_justification=text,
            cited_image_ids=_cited_image_ids(disposition),
            fallback_used=True,
        )


def _template_for(disposition: Disposition) -> str:
    if disposition.claim_status == ClaimStatus.SUPPORTED:
        return _supported_template(disposition)
    if disposition.claim_status == ClaimStatus.CONTRADICTED:
        return _contradicted_template(disposition)
    return _not_enough_information_template(disposition)


def _supported_template(disposition: Disposition) -> str:
    issue = _human(disposition.issue_type.value)
    part = _human(disposition.object_part.value)
    image_text = _image_text(disposition.supporting_image_ids)
    risk_text = _risk_text(disposition)
    return f"The locked decision is supported because {image_text} show {issue} on the {part}.{risk_text}"


def _contradicted_template(disposition: Disposition) -> str:
    part = _human(disposition.object_part.value)
    image_text = _image_text(disposition.supporting_image_ids)
    risk_text = _risk_text(disposition)
    if disposition.issue_type == IssueType.NONE:
        return f"The locked decision is contradicted because {image_text} show the {part} but no matching damage is visible.{risk_text}"
    issue = _human(disposition.issue_type.value)
    return f"The locked decision is contradicted because {image_text} show {issue} involving the {part}, which does not match the claimed evidence pattern.{risk_text}"


def _not_enough_information_template(disposition: Disposition) -> str:
    part = _human(disposition.object_part.value)
    reason = disposition.evidence_standard_met_reason.rstrip(".")
    risk_text = _risk_text(disposition)
    return f"The locked decision is not enough information because {reason}; the {part} cannot be verified reliably from the submitted evidence.{risk_text}"


def _risk_text(disposition: Disposition) -> str:
    risk_flags = tuple(flag for flag in disposition.risk_flags if flag != RiskFlag.NONE)
    if not risk_flags:
        return ""
    rendered = ", ".join(_human(flag.value) for flag in risk_flags)
    return f" Risk flags recorded: {rendered}."


def _image_text(image_ids: tuple[str, ...]) -> str:
    ids = tuple(image_id for image_id in image_ids if image_id != "none")
    if not ids:
        return "the available images"
    if len(ids) == 1:
        return f"image {ids[0]}"
    return "images " + ", ".join(ids)


def _cited_image_ids(disposition: Disposition) -> tuple[str, ...]:
    if disposition.supporting_image_ids != ("none",):
        return disposition.supporting_image_ids
    return ("none",)


def _human(value: str) -> str:
    return value.replace("_", " ")


def audit_justification(justification: Justification) -> tuple[bool, tuple[str, ...]]:
    """Non-generative consistency check against the locked disposition."""

    text = justification.claim_status_justification.lower()
    disposition = justification.disposition
    violations: list[str] = []

    if disposition.claim_status.value.replace("_", " ") not in text:
        violations.append("missing locked claim_status")
    if disposition.issue_type not in {IssueType.UNKNOWN, IssueType.NONE} and _human(disposition.issue_type.value) not in text:
        violations.append("missing locked issue_type")
    if _human(disposition.object_part.value) not in text:
        violations.append("missing locked object_part")
    if disposition.issue_type == IssueType.NONE and "no matching damage" not in text:
        violations.append("issue_type=none must describe absence of visible matching damage")
    if disposition.severity == Severity.NONE and any(word in text for word in (" low ", " medium ", " high ")):
        violations.append("severity=none justification mentions damage severity")
    if disposition.claim_status == ClaimStatus.SUPPORTED and "not enough information" in text:
        violations.append("supported justification contains not enough information")
    if disposition.claim_status == ClaimStatus.SUPPORTED and "contradicted" in text:
        violations.append("supported justification contains contradicted")
    if disposition.claim_status == ClaimStatus.CONTRADICTED and "supported" in text:
        violations.append("contradicted justification contains supported")

    return not violations, tuple(violations)

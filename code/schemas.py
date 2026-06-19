from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, ClassVar, Iterable, Mapping, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, field_validator, model_validator


INPUT_COLUMNS: tuple[str, ...] = (
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
)

OUTPUT_COLUMNS: tuple[str, ...] = (
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
    "evidence_standard_met",
    "evidence_standard_met_reason",
    "risk_flags",
    "issue_type",
    "object_part",
    "claim_status",
    "claim_status_justification",
    "supporting_image_ids",
    "valid_image",
    "severity",
)

SENTINEL_NONE = "none"


class SchemaModel(BaseModel):
    """Base contract for all pipeline boundaries."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ClaimObject(StrEnum):
    CAR = "car"
    LAPTOP = "laptop"
    PACKAGE = "package"


class RequirementObject(StrEnum):
    ALL = "all"
    CAR = "car"
    LAPTOP = "laptop"
    PACKAGE = "package"


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_ENOUGH_INFORMATION = "not_enough_information"


class IssueType(StrEnum):
    DENT = "dent"
    SCRATCH = "scratch"
    CRACK = "crack"
    GLASS_SHATTER = "glass_shatter"
    BROKEN_PART = "broken_part"
    MISSING_PART = "missing_part"
    TORN_PACKAGING = "torn_packaging"
    CRUSHED_PACKAGING = "crushed_packaging"
    WATER_DAMAGE = "water_damage"
    STAIN = "stain"
    NONE = "none"
    UNKNOWN = "unknown"


class CarPart(StrEnum):
    FRONT_BUMPER = "front_bumper"
    REAR_BUMPER = "rear_bumper"
    DOOR = "door"
    HOOD = "hood"
    WINDSHIELD = "windshield"
    SIDE_MIRROR = "side_mirror"
    HEADLIGHT = "headlight"
    TAILLIGHT = "taillight"
    FENDER = "fender"
    QUARTER_PANEL = "quarter_panel"
    BODY = "body"
    UNKNOWN = "unknown"


class LaptopPart(StrEnum):
    SCREEN = "screen"
    KEYBOARD = "keyboard"
    TRACKPAD = "trackpad"
    HINGE = "hinge"
    LID = "lid"
    CORNER = "corner"
    PORT = "port"
    BASE = "base"
    BODY = "body"
    UNKNOWN = "unknown"


class PackagePart(StrEnum):
    BOX = "box"
    PACKAGE_CORNER = "package_corner"
    PACKAGE_SIDE = "package_side"
    SEAL = "seal"
    LABEL = "label"
    CONTENTS = "contents"
    ITEM = "item"
    UNKNOWN = "unknown"


ObjectPart: TypeAlias = CarPart | LaptopPart | PackagePart


PARTS_BY_OBJECT: dict[ClaimObject, frozenset[str]] = {
    ClaimObject.CAR: frozenset(part.value for part in CarPart),
    ClaimObject.LAPTOP: frozenset(part.value for part in LaptopPart),
    ClaimObject.PACKAGE: frozenset(part.value for part in PackagePart),
}


class RiskFlag(StrEnum):
    NONE = "none"
    BLURRY_IMAGE = "blurry_image"
    CROPPED_OR_OBSTRUCTED = "cropped_or_obstructed"
    LOW_LIGHT_OR_GLARE = "low_light_or_glare"
    WRONG_ANGLE = "wrong_angle"
    WRONG_OBJECT = "wrong_object"
    WRONG_OBJECT_PART = "wrong_object_part"
    DAMAGE_NOT_VISIBLE = "damage_not_visible"
    CLAIM_MISMATCH = "claim_mismatch"
    POSSIBLE_MANIPULATION = "possible_manipulation"
    NON_ORIGINAL_IMAGE = "non_original_image"
    TEXT_INSTRUCTION_PRESENT = "text_instruction_present"
    USER_HISTORY_RISK = "user_history_risk"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class Severity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class VisibleObject(StrEnum):
    CAR = "car"
    LAPTOP = "laptop"
    PACKAGE = "package"
    UNKNOWN = "unknown"


class EvidenceConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


def _require_non_empty(value: str, field_name: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} must be non-empty")
    return str(value).strip()


def _split_semicolon(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [item.strip() for item in value.split(";")]
    elif isinstance(value, Iterable):
        items = [str(item).strip() for item in value]
    else:
        raise TypeError("expected a semicolon-separated string or iterable")
    return tuple(item for item in items if item)


def _semicolon_or_none(values: Iterable[str | StrEnum]) -> str:
    rendered = [str(value.value if isinstance(value, StrEnum) else value) for value in values]
    rendered = [value for value in rendered if value and value != SENTINEL_NONE]
    return ";".join(rendered) if rendered else SENTINEL_NONE


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError("expected boolean or 'true'/'false'")


def _bool_to_csv(value: bool) -> str:
    return "true" if value else "false"


def image_id_from_path(image_path: str) -> str:
    """Return the image ID required by the spec: filename without extension."""

    path = _require_non_empty(image_path, "image_path")
    name = PurePosixPath(path.replace("\\", "/")).name or PureWindowsPath(path).name
    stem = name.rsplit(".", 1)[0]
    return _require_non_empty(stem, "image_id")


def validate_image_ids(value: Any) -> tuple[str, ...]:
    ids = _split_semicolon(value)
    if not ids:
        return (SENTINEL_NONE,)
    if SENTINEL_NONE in ids and len(ids) > 1:
        raise ValueError("'none' cannot be combined with image IDs")
    for image_id in ids:
        if any(char in image_id for char in (";", "/", "\\")):
            raise ValueError(f"invalid image_id: {image_id!r}")
    return ids


def validate_risk_flags(value: Any) -> tuple[RiskFlag, ...]:
    raw_flags = _split_semicolon(value)
    if not raw_flags:
        return (RiskFlag.NONE,)
    flags = tuple(RiskFlag(flag) for flag in raw_flags)
    if RiskFlag.NONE in flags and len(flags) > 1:
        raise ValueError("'none' cannot be combined with other risk flags")
    return flags


def allowed_parts_for_object(claim_object: ClaimObject) -> frozenset[str]:
    return PARTS_BY_OBJECT[claim_object]


def assert_part_matches_object(claim_object: ClaimObject, object_part: ObjectPart) -> None:
    if object_part.value not in allowed_parts_for_object(claim_object):
        raise ValueError(f"{object_part.value!r} is not valid for claim_object={claim_object.value!r}")


class ImageRef(SchemaModel):
    image_path: str
    image_id: str

    @model_validator(mode="before")
    @classmethod
    def _populate_image_id(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            values = dict(data)
            image_path = values.get("image_path")
            if image_path is not None and not values.get("image_id"):
                values["image_id"] = image_id_from_path(str(image_path))
            return values
        return data

    @field_validator("image_path")
    @classmethod
    def _validate_image_path(cls, value: str) -> str:
        return _require_non_empty(value, "image_path")

    @model_validator(mode="after")
    def _default_image_id(self) -> ImageRef:
        expected_id = image_id_from_path(self.image_path)
        if self.image_id != expected_id:
            raise ValueError(f"image_id {self.image_id!r} does not match path-derived ID {expected_id!r}")
        return self


class InputClaimRow(SchemaModel):
    user_id: str
    image_paths: tuple[str, ...]
    user_claim: str
    claim_object: ClaimObject

    @field_validator("user_id", "user_claim")
    @classmethod
    def _non_empty_text(cls, value: str, info: Any) -> str:
        return _require_non_empty(value, info.field_name)

    @field_validator("image_paths", mode="before")
    @classmethod
    def _parse_image_paths(cls, value: Any) -> tuple[str, ...]:
        paths = _split_semicolon(value)
        if not paths:
            raise ValueError("image_paths must contain at least one image")
        return paths

    @property
    def images(self) -> tuple[ImageRef, ...]:
        return tuple(ImageRef(image_path=path) for path in self.image_paths)

    @classmethod
    def from_csv_row(cls, row: Mapping[str, Any]) -> InputClaimRow:
        return cls.model_validate({column: row.get(column) for column in INPUT_COLUMNS})


class EvidenceRequirementRow(SchemaModel):
    requirement_id: str
    claim_object: RequirementObject
    applies_to: str
    minimum_image_evidence: str

    @field_validator("requirement_id", "applies_to", "minimum_image_evidence")
    @classmethod
    def _non_empty_text(cls, value: str, info: Any) -> str:
        return _require_non_empty(value, info.field_name)


class UserHistoryRow(SchemaModel):
    user_id: str
    past_claim_count: NonNegativeInt
    accept_claim: NonNegativeInt
    manual_review_claim: NonNegativeInt
    rejected_claim: NonNegativeInt
    last_90_days_claim_count: NonNegativeInt
    history_flags: tuple[RiskFlag, ...]
    history_summary: str

    @field_validator("user_id", "history_summary")
    @classmethod
    def _non_empty_text(cls, value: str, info: Any) -> str:
        return _require_non_empty(value, info.field_name)

    @field_validator("history_flags", mode="before")
    @classmethod
    def _parse_history_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)


class DamageClaim(SchemaModel):
    issue_type: IssueType
    object_part: ObjectPart
    issue_family: str = Field(default="unknown")
    source_text: str = Field(default="")

    @field_validator("issue_family")
    @classmethod
    def _non_empty_family(cls, value: str) -> str:
        return _require_non_empty(value, "issue_family")


class ClaimUnderstanding(SchemaModel):
    """Structured claim-text output; intentionally has no final decision fields."""

    user_id: str
    claim_object: ClaimObject
    primary_claim: DamageClaim
    secondary_claims: tuple[DamageClaim, ...] = ()
    normalized_claim: str
    detected_language: str = "unknown"
    is_compound: bool = False
    injection_attempt_detected: bool = False
    injection_rationale: str = ""

    forbidden_decision_fields: ClassVar[frozenset[str]] = frozenset(
        {"claim_status", "severity", "risk_flags", "valid_image", "evidence_standard_met"}
    )

    @field_validator("user_id", "normalized_claim", "detected_language")
    @classmethod
    def _non_empty_text(cls, value: str, info: Any) -> str:
        return _require_non_empty(value, info.field_name)

    @model_validator(mode="after")
    def _validate_claim_parts(self) -> ClaimUnderstanding:
        assert_part_matches_object(self.claim_object, self.primary_claim.object_part)
        for claim in self.secondary_claims:
            assert_part_matches_object(self.claim_object, claim.object_part)
        if bool(self.secondary_claims) and not self.is_compound:
            raise ValueError("secondary_claims require is_compound=True")
        return self


class ImageAnalysisTarget(SchemaModel):
    """Minimal claim-derived target allowed into deterministic image matching."""

    claim_object: ClaimObject
    object_part: ObjectPart
    issue_type: IssueType

    @model_validator(mode="after")
    def _validate_target_part(self) -> ImageAnalysisTarget:
        assert_part_matches_object(self.claim_object, self.object_part)
        return self

    @classmethod
    def from_claim(cls, claim: DamageClaim, claim_object: ClaimObject) -> ImageAnalysisTarget:
        return cls(
            claim_object=claim_object,
            object_part=claim.object_part,
            issue_type=claim.issue_type,
        )


class ImageEvidence(SchemaModel):
    image: ImageRef
    visible_object: VisibleObject = VisibleObject.UNKNOWN
    claim_object_match: bool | None = None
    visible_parts: tuple[ObjectPart, ...] = ()
    claimed_part_visible: bool = False
    issue_type: IssueType = IssueType.UNKNOWN
    object_part: ObjectPart
    damage_visible: bool = False
    valid_image: bool = True
    risk_flags: tuple[RiskFlag, ...] = (RiskFlag.NONE,)
    severity: Severity = Severity.UNKNOWN
    confidence: EvidenceConfidence = EvidenceConfidence.UNKNOWN
    embedded_text_detected: bool = False
    embedded_text_excerpt: str | None = None
    summary: str = ""

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)

    @model_validator(mode="after")
    def _validate_image_contract(self) -> ImageEvidence:
        if self.embedded_text_detected and RiskFlag.TEXT_INSTRUCTION_PRESENT not in self.risk_flags:
            raise ValueError("embedded_text_detected requires text_instruction_present risk flag")
        if not self.valid_image and self.confidence == EvidenceConfidence.HIGH:
            raise ValueError("invalid images cannot have high evidence confidence")
        return self


class VerificationRecommendation(SchemaModel):
    """Separate escalation contract; never contains disposition or justification fields."""

    verification_needed: bool
    allowed_by_budget: bool
    reserved_call_count: NonNegativeInt
    trigger_flags: tuple[RiskFlag, ...] = (RiskFlag.NONE,)
    reason: str
    budget_limit: NonNegativeInt
    budget_used_before: NonNegativeInt
    budget_remaining_after: NonNegativeInt

    @field_validator("verification_needed", "allowed_by_budget", mode="before")
    @classmethod
    def _parse_bool_fields(cls, value: Any) -> bool:
        return _parse_bool(value)

    @field_validator("trigger_flags", mode="before")
    @classmethod
    def _parse_trigger_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)

    @field_validator("reason")
    @classmethod
    def _non_empty_reason(cls, value: str) -> str:
        return _require_non_empty(value, "reason")

    @model_validator(mode="after")
    def _validate_budget_contract(self) -> VerificationRecommendation:
        if not self.verification_needed and self.reserved_call_count != 0:
            raise ValueError("reserved_call_count must be zero when verification is not needed")
        if not self.allowed_by_budget and self.reserved_call_count != 0:
            raise ValueError("reserved_call_count must be zero when budget does not allow escalation")
        if self.trigger_flags == (RiskFlag.NONE,) and self.verification_needed:
            raise ValueError("verification_needed=True requires concrete trigger flags")
        return self


class AggregatedEvidence(SchemaModel):
    images: tuple[ImageEvidence, ...]
    relevant_image_ids: tuple[str, ...] = (SENTINEL_NONE,)
    supporting_image_ids: tuple[str, ...] = (SENTINEL_NONE,)
    claim_object_match: bool | None = None
    claimed_part_visible: bool = False
    visible_issue_type: IssueType = IssueType.UNKNOWN
    visible_object_part: ObjectPart
    damage_visible: bool = False
    valid_image: bool = True
    risk_flags: tuple[RiskFlag, ...] = (RiskFlag.NONE,)
    summary: str = ""

    @field_validator("relevant_image_ids", "supporting_image_ids", mode="before")
    @classmethod
    def _parse_image_ids(cls, value: Any) -> tuple[str, ...]:
        return validate_image_ids(value)

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)

    @model_validator(mode="after")
    def _validate_aggregation(self) -> AggregatedEvidence:
        image_ids = {image.image.image_id for image in self.images}
        for image_id in (*self.relevant_image_ids, *self.supporting_image_ids):
            if image_id != SENTINEL_NONE and image_id not in image_ids:
                raise ValueError(f"image_id {image_id!r} is not present in images")
        if not self.images:
            raise ValueError("aggregation requires at least one image")
        return self


class HistoryRisk(SchemaModel):
    user_id: str
    user_found: bool
    past_claim_count: NonNegativeInt = 0
    last_90_days_claim_count: NonNegativeInt = 0
    risk_flags: tuple[RiskFlag, ...] = (RiskFlag.NONE,)
    rationale: str = ""

    @field_validator("user_id")
    @classmethod
    def _non_empty_user(cls, value: str) -> str:
        return _require_non_empty(value, "user_id")

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)

    @model_validator(mode="after")
    def _history_flags_are_history_only(self) -> HistoryRisk:
        allowed = {RiskFlag.NONE, RiskFlag.USER_HISTORY_RISK, RiskFlag.MANUAL_REVIEW_REQUIRED}
        extra = set(self.risk_flags) - allowed
        if extra:
            values = ", ".join(sorted(flag.value for flag in extra))
            raise ValueError(f"history risk cannot emit evidence-derived flags: {values}")
        return self


class EvidenceAssessment(SchemaModel):
    evidence_standard_met: bool
    evidence_standard_met_reason: str
    matched_requirement_ids: tuple[str, ...] = ()
    minimum_image_evidence: str = ""
    valid_image: bool
    risk_flags: tuple[RiskFlag, ...] = (RiskFlag.NONE,)

    @field_validator("evidence_standard_met", "valid_image", mode="before")
    @classmethod
    def _parse_bool_fields(cls, value: Any) -> bool:
        return _parse_bool(value)

    @field_validator("evidence_standard_met_reason")
    @classmethod
    def _non_empty_reason(cls, value: str) -> str:
        return _require_non_empty(value, "evidence_standard_met_reason")

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)


class CompoundDispositionInput(SchemaModel):
    """Typed secondary claim result consumed only by the disposition layer."""

    target: ImageAnalysisTarget
    aggregated: AggregatedEvidence
    evidence: EvidenceAssessment


class Disposition(SchemaModel):
    user_id: str
    claim_object: ClaimObject
    evidence_standard_met: bool
    evidence_standard_met_reason: str
    risk_flags: tuple[RiskFlag, ...]
    issue_type: IssueType
    object_part: ObjectPart
    claim_status: ClaimStatus
    supporting_image_ids: tuple[str, ...]
    valid_image: bool
    severity: Severity

    @field_validator("user_id", "evidence_standard_met_reason")
    @classmethod
    def _non_empty_text(cls, value: str, info: Any) -> str:
        return _require_non_empty(value, info.field_name)

    @field_validator("evidence_standard_met", "valid_image", mode="before")
    @classmethod
    def _parse_bool_fields(cls, value: Any) -> bool:
        return _parse_bool(value)

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)

    @field_validator("supporting_image_ids", mode="before")
    @classmethod
    def _parse_supporting_ids(cls, value: Any) -> tuple[str, ...]:
        return validate_image_ids(value)

    @model_validator(mode="after")
    def _validate_disposition(self) -> Disposition:
        assert_part_matches_object(self.claim_object, self.object_part)
        if not self.evidence_standard_met and self.claim_status == ClaimStatus.SUPPORTED:
            raise ValueError("unsupported evidence_standard_met=False cannot produce claim_status=supported")
        if self.claim_status == ClaimStatus.SUPPORTED and self.supporting_image_ids == (SENTINEL_NONE,):
            raise ValueError("supported claims require at least one supporting image ID")
        if self.claim_status == ClaimStatus.SUPPORTED and self.issue_type in {IssueType.NONE, IssueType.UNKNOWN}:
            raise ValueError("supported claims require a concrete visible issue type")
        if self.issue_type == IssueType.NONE and self.severity != Severity.NONE:
            raise ValueError("issue_type=none requires severity=none")
        return self


class JustificationDraft(SchemaModel):
    disposition: Disposition
    claim_status_justification: str
    cited_image_ids: tuple[str, ...] = (SENTINEL_NONE,)
    fallback_used: bool = False

    @field_validator("claim_status_justification")
    @classmethod
    def _non_empty_justification(cls, value: str) -> str:
        return _require_non_empty(value, "claim_status_justification")

    @field_validator("cited_image_ids", mode="before")
    @classmethod
    def _parse_cited_ids(cls, value: Any) -> tuple[str, ...]:
        return validate_image_ids(value)


class JustificationAudit(SchemaModel):
    draft: JustificationDraft
    passed: bool
    violations: tuple[str, ...] = ()
    repaired_justification: str | None = None

    @field_validator("passed", mode="before")
    @classmethod
    def _parse_passed(cls, value: Any) -> bool:
        return _parse_bool(value)

    @model_validator(mode="after")
    def _validate_audit_result(self) -> JustificationAudit:
        if not self.passed and not self.violations:
            raise ValueError("failed audits must include at least one violation")
        return self


class OutputPredictionRow(SchemaModel):
    user_id: str
    image_paths: tuple[str, ...]
    user_claim: str
    claim_object: ClaimObject
    evidence_standard_met: bool
    evidence_standard_met_reason: str
    risk_flags: tuple[RiskFlag, ...]
    issue_type: IssueType
    object_part: ObjectPart
    claim_status: ClaimStatus
    claim_status_justification: str
    supporting_image_ids: tuple[str, ...]
    valid_image: bool
    severity: Severity

    csv_columns: ClassVar[tuple[str, ...]] = OUTPUT_COLUMNS

    @field_validator("user_id", "user_claim", "evidence_standard_met_reason", "claim_status_justification")
    @classmethod
    def _non_empty_text(cls, value: str, info: Any) -> str:
        return _require_non_empty(value, info.field_name)

    @field_validator("image_paths", mode="before")
    @classmethod
    def _parse_image_paths(cls, value: Any) -> tuple[str, ...]:
        paths = _split_semicolon(value)
        if not paths:
            raise ValueError("image_paths must contain at least one image")
        return paths

    @field_validator("evidence_standard_met", "valid_image", mode="before")
    @classmethod
    def _parse_bool_fields(cls, value: Any) -> bool:
        return _parse_bool(value)

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value: Any) -> tuple[RiskFlag, ...]:
        return validate_risk_flags(value)

    @field_validator("supporting_image_ids", mode="before")
    @classmethod
    def _parse_supporting_ids(cls, value: Any) -> tuple[str, ...]:
        return validate_image_ids(value)

    @model_validator(mode="after")
    def _validate_output_consistency(self) -> OutputPredictionRow:
        assert_part_matches_object(self.claim_object, self.object_part)
        if not self.evidence_standard_met and self.claim_status == ClaimStatus.SUPPORTED:
            raise ValueError("evidence_standard_met=False cannot produce claim_status=supported")
        if self.claim_status == ClaimStatus.SUPPORTED and self.supporting_image_ids == (SENTINEL_NONE,):
            raise ValueError("supported claims require supporting image IDs")
        if self.claim_status == ClaimStatus.SUPPORTED and self.issue_type in {IssueType.NONE, IssueType.UNKNOWN}:
            raise ValueError("supported claims require a concrete issue_type")
        if self.issue_type == IssueType.NONE and self.severity != Severity.NONE:
            raise ValueError("issue_type=none requires severity=none")
        return self

    @classmethod
    def from_input_and_disposition(
        cls,
        input_row: InputClaimRow,
        disposition: Disposition,
        claim_status_justification: str,
    ) -> OutputPredictionRow:
        return cls(
            user_id=input_row.user_id,
            image_paths=input_row.image_paths,
            user_claim=input_row.user_claim,
            claim_object=input_row.claim_object,
            evidence_standard_met=disposition.evidence_standard_met,
            evidence_standard_met_reason=disposition.evidence_standard_met_reason,
            risk_flags=disposition.risk_flags,
            issue_type=disposition.issue_type,
            object_part=disposition.object_part,
            claim_status=disposition.claim_status,
            claim_status_justification=claim_status_justification,
            supporting_image_ids=disposition.supporting_image_ids,
            valid_image=disposition.valid_image,
            severity=disposition.severity,
        )

    @classmethod
    def from_csv_row(cls, row: Mapping[str, Any]) -> OutputPredictionRow:
        return cls.model_validate({column: row.get(column) for column in OUTPUT_COLUMNS})

    def to_csv_row(self) -> dict[str, str]:
        row = {
            "user_id": self.user_id,
            "image_paths": _semicolon_or_none(self.image_paths),
            "user_claim": self.user_claim,
            "claim_object": self.claim_object.value,
            "evidence_standard_met": _bool_to_csv(self.evidence_standard_met),
            "evidence_standard_met_reason": self.evidence_standard_met_reason,
            "risk_flags": _semicolon_or_none(self.risk_flags),
            "issue_type": self.issue_type.value,
            "object_part": self.object_part.value,
            "claim_status": self.claim_status.value,
            "claim_status_justification": self.claim_status_justification,
            "supporting_image_ids": _semicolon_or_none(self.supporting_image_ids),
            "valid_image": _bool_to_csv(self.valid_image),
            "severity": self.severity.value,
        }
        return {column: row[column] for column in OUTPUT_COLUMNS}


def validate_output_header(columns: Iterable[str]) -> None:
    actual = tuple(columns)
    if actual != OUTPUT_COLUMNS:
        raise ValueError(f"output columns must be exactly {OUTPUT_COLUMNS!r}; got {actual!r}")


def validate_input_header(columns: Iterable[str]) -> None:
    actual = tuple(columns)
    if actual[: len(INPUT_COLUMNS)] != INPUT_COLUMNS:
        raise ValueError(f"input columns must start with {INPUT_COLUMNS!r}; got {actual!r}")

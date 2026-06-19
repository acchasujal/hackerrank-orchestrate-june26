from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from schemas import (
    CarPart,
    ClaimObject,
    ClaimUnderstanding,
    DamageClaim,
    InputClaimRow,
    IssueType,
    LaptopPart,
    ObjectPart,
    PackagePart,
)


PROHIBITED_IMPORTS = frozenset(
    {
        "pipeline.disposition",
        "pipeline.image_analysis",
        "pipeline.reference_signals",
        "pipeline.justification",
        "llm_client",
        "openai",
        "anthropic",
        "google.genai",
    }
)

CORRECTION_MARKERS = (
    "actually",
    "i meant",
    "i mean",
    "sorry",
    "correction",
    "instead",
    "rather",
    "not the",
    "not my",
)

COMPOUND_MARKERS = (
    "two things",
    "two issues",
    "multiple parts",
    "both",
    "plus",
    "together",
    "also",
    "and the",
    "and my",
    "y tambien",
    "tambien",
    "和",
)

INJECTION_PATTERNS = (
    r"\bapprove\b",
    r"\bapproved\b",
    r"\baccept\b",
    r"\bskip\s+manual\s+review\b",
    r"\bignore\s+(all\s+)?previous\s+instructions\b",
    r"\bmark\s+this\s+row\b",
    r"\bsystem\s+reading\s+this\b",
    r"\bfollow\s+(the\s+)?note\b",
    r"\bshould\s+be\s+approved\b",
    r"\bclaim\s+approve\s+kar\s+dena\b",
    r"支持",
    r"批准",
)

NEGATION_PATTERNS = (
    r"not\s+(?:my\s+)?main\s+concern",
    r"not\s+claiming",
    r"not\s+reporting",
    r"nahi\s+kar",
    r"nahi\s+claim",
    r"no\s+reclam",
    r"not\s+(?:going\s+to\s+)?claim",
    r"not\s+what\s+i\s+want\s+to\s+claim",
)


@dataclass(frozen=True)
class _Turn:
    speaker: str
    text: str


@dataclass(frozen=True)
class _Hit:
    start: int
    end: int
    value: IssueType | ObjectPart
    phrase: str


@dataclass(frozen=True)
class _ClaimHit:
    claim: DamageClaim
    position: int


ISSUE_PHRASES: tuple[tuple[IssueType, tuple[str, ...]], ...] = (
    (IssueType.GLASS_SHATTER, ("shattered", "shatter", "碎了", "破碎")),
    (IssueType.CRACK, ("cracked", "crack", "cracking", "fisura", "agriet", "裂", "裂纹")),
    (IssueType.SCRATCH, ("scratched", "scratch", "scrape", "scraped", "rayon", "rayado", "raspon")),
    (IssueType.DENT, ("dented", "dents", "dent", "hail dents", "hail damage", "abolladura", "abollado")),
    (IssueType.BROKEN_PART, ("dano", "danado", "dañado")),
    (IssueType.MISSING_PART, ("missing", "faltante", "perdido", "丢失", "不见")),
    (IssueType.TORN_PACKAGING, ("torn", "ripped", "opened", "tear", "rasgado", "rota", "撕", "破了")),
    (IssueType.CRUSHED_PACKAGING, ("crushed", "crush ho gaya", "aplastado", "压坏", "压扁")),
    (IssueType.WATER_DAMAGE, ("water damage", "water damaged", "wet", "mojado", "agua", "pani", "水损", "湿")),
    (IssueType.STAIN, ("stain", "stained", "mancha", "污渍")),
    (IssueType.BROKEN_PART, ("broken", "broke", "damaged", "damage", "affected", "tuta", "toot", "kharab", "roto", "dañado", "坏", "损坏")),
)

CAR_PART_PHRASES: tuple[tuple[CarPart, tuple[str, ...]], ...] = (
    (CarPart.FRONT_BUMPER, ("front bumper", "front side", "front end")),
    (CarPart.REAR_BUMPER, ("rear bumper", "back bumper", "back of the car", "rear side", "parachoques trasero", "parachoques de atras")),
    (CarPart.SIDE_MIRROR, ("side mirror", "mirror")),
    (CarPart.WINDSHIELD, ("windshield", "front glass", "glass", "rear glass", "back glass", "rear windshield", "front windshield", "glass pane")),
    (CarPart.HEADLIGHT, ("headlight", "head light")),
    (CarPart.TAILLIGHT, ("taillight", "tail light")),
    (CarPart.QUARTER_PANEL, ("quarter panel",)),
    (CarPart.FENDER, ("fender",)),
    (CarPart.DOOR, ("door panel", "door")),
    (CarPart.HOOD, ("hood", "bonnet")),
    (CarPart.BODY, ("body",)),
)

LAPTOP_PART_PHRASES: tuple[tuple[LaptopPart, tuple[str, ...]], ...] = (
    (LaptopPart.SCREEN, ("screen", "display", "pantalla", "屏幕")),
    (LaptopPart.KEYBOARD, ("keyboard", "key", "teclado", "键盘")),
    (LaptopPart.TRACKPAD, ("trackpad", "touchpad", "触控板")),
    (LaptopPart.HINGE, ("hinge", "bisagra", "铰链")),
    (LaptopPart.LID, ("lid", "cover", "tapa")),
    (LaptopPart.CORNER, ("corner", "esquina", "角")),
    (LaptopPart.PORT, ("port", "puerto", "接口")),
    (LaptopPart.BASE, ("base", "bottom", "底部")),
    (LaptopPart.BODY, ("body", "case", "casing", "carcasa")),
)

PACKAGE_PART_PHRASES: tuple[tuple[PackagePart, tuple[str, ...]], ...] = (
    (PackagePart.PACKAGE_CORNER, ("package corner", "box corner", "corner", "esquina")),
    (PackagePart.PACKAGE_SIDE, ("package side", "box side", "side", "lado", "surface")),
    (PackagePart.CONTENTS, ("contents", "items", "inside", "contenido", "物品", "里面")),
    (PackagePart.SEAL, ("seal", "sello", "封口")),
    (PackagePart.LABEL, ("label", "etiqueta", "标签")),
    (PackagePart.BOX, ("delivery box", "package", "box", "paquete", "caja", "包裹", "盒子")),
    (PackagePart.ITEM, ("item", "producto", "商品")),
)

PART_PHRASES_BY_OBJECT = {
    ClaimObject.CAR: CAR_PART_PHRASES,
    ClaimObject.LAPTOP: LAPTOP_PART_PHRASES,
    ClaimObject.PACKAGE: PACKAGE_PART_PHRASES,
}

UNKNOWN_PART_BY_OBJECT = {
    ClaimObject.CAR: CarPart.UNKNOWN,
    ClaimObject.LAPTOP: LaptopPart.UNKNOWN,
    ClaimObject.PACKAGE: PackagePart.UNKNOWN,
}


class ClaimUnderstandingEngine:
    """Deterministic claim-text extractor with no disposition authority."""

    def extract(self, row: InputClaimRow) -> ClaimUnderstanding:
        turns = _split_turns(row.user_claim)
        customer_texts = _customer_texts(turns)
        raw_customer_text = " | ".join(customer_texts) if customer_texts else row.user_claim
        analysis_text, correction_detected = _analysis_scope(customer_texts)
        injection_detected, injection_rationale = _detect_injection(row.user_claim)
        detected_language = _detect_language(raw_customer_text)

        claim_hits = _extract_claims(analysis_text, row.claim_object)
        if not claim_hits and correction_detected:
            claim_hits = _extract_claims(raw_customer_text, row.claim_object)
        if not claim_hits:
            claim_hits = [_fallback_claim(analysis_text or raw_customer_text, row.claim_object)]

        compound = (not correction_detected or _has_compound_marker(analysis_text)) and _is_compound(
            analysis_text,
            claim_hits,
        )
        
        if compound:
            selected_claims = claim_hits
            primary = selected_claims[0].claim
            secondary = tuple(hit.claim for hit in selected_claims[1:])
        else:
            # Single claim resolution: use best part and best issue found anywhere in analysis_text
            part_hits = _find_part_hits(analysis_text or raw_customer_text, row.claim_object)
            issue_hits = _find_issue_hits(analysis_text or raw_customer_text)
            
            # Apply negations
            part_hits = [h for h in part_hits if not _is_negated(analysis_text or raw_customer_text, h.start, h.end)]
            issue_hits = [h for h in issue_hits if not _is_negated(analysis_text or raw_customer_text, h.start, h.end)]
            
            best_part = _find_best_part(part_hits, row.claim_object)
            best_issue = _find_best_issue(issue_hits)
            
            primary = DamageClaim(
                issue_type=best_issue,
                object_part=best_part,
                issue_family=_issue_family(best_issue),
                source_text=_source_excerpt(analysis_text or raw_customer_text, 0, len(analysis_text or raw_customer_text)),
            )
            secondary = ()

        return ClaimUnderstanding(
            user_id=row.user_id,
            claim_object=row.claim_object,
            primary_claim=primary,
            secondary_claims=secondary,
            normalized_claim=_normalized_claim(row.claim_object, primary, secondary),
            detected_language=detected_language,
            is_compound=bool(secondary),
            injection_attempt_detected=injection_detected,
            injection_rationale=injection_rationale,
        )


def _split_turns(transcript: str) -> tuple[_Turn, ...]:
    turns: list[_Turn] = []
    for raw_part in transcript.split("|"):
        part = raw_part.strip()
        if not part:
            continue
        match = re.match(r"^([^:]{1,30}):\s*(.*)$", part)
        if match:
            turns.append(_Turn(speaker=match.group(1).strip().lower(), text=match.group(2).strip()))
        else:
            turns.append(_Turn(speaker="unknown", text=part))
    return tuple(turns)


def _customer_texts(turns: Sequence[_Turn]) -> tuple[str, ...]:
    texts = [turn.text for turn in turns if turn.speaker in {"customer", "user", "claimant"}]
    return tuple(texts)


def _analysis_scope(customer_texts: Sequence[str]) -> tuple[str, bool]:
    if not customer_texts:
        return "", False
    for index in range(len(customer_texts) - 1, -1, -1):
        lowered = customer_texts[index].lower()
        marker_positions = []
        for marker in CORRECTION_MARKERS:
            pattern = r"\b" + re.escape(marker.strip()) + r"\b"
            match = re.search(pattern, lowered)
            if match:
                marker_positions.append(match.start())
        if marker_positions:
            start = min(marker_positions)
            current = customer_texts[index][start:]
            return " | ".join((current, *customer_texts[index + 1 :])), True
    return " | ".join(customer_texts), False


def _detect_injection(text: str) -> tuple[bool, str]:
    lowered = text.lower()
    matched: list[str] = []
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            matched.append(pattern)
    if not matched:
        return False, ""
    return True, "instruction-like claim text detected: " + ", ".join(matched[:3])


def _detect_language(text: str) -> str:
    lowered = text.lower()
    labels: list[str] = []
    if re.search(r"[\u4e00-\u9fff]", text):
        labels.append("chinese")
    if any(token in lowered for token in ("pantalla", "paquete", "caja", "sello", "abolladura", "mojado", "bisagra")):
        labels.append("spanish")
    if any(token in lowered for token in ("mera", "mein", "hai", "haan", "kya", "ho gaya", "kar dena", "tuta", "toot")):
        labels.append("hinglish")
    if re.search(r"[a-zA-Z]", text):
        labels.append("english")
    deduped = tuple(dict.fromkeys(labels))
    if not deduped:
        return "unknown"
    if len(deduped) == 1:
        return deduped[0]
    return "mixed:" + "+".join(deduped)


def _extract_claims(text: str, claim_object: ClaimObject) -> list[_ClaimHit]:
    part_hits = _find_part_hits(text, claim_object)
    issue_hits = _find_issue_hits(text)
    
    part_hits = [h for h in part_hits if not _is_negated(text, h.start, h.end)]
    issue_hits = [h for h in issue_hits if not _is_negated(text, h.start, h.end)]
    
    claims: list[_ClaimHit] = []

    for part_hit in part_hits:
        issue_hit = _nearest_issue(part_hit, issue_hits)
        issue = issue_hit.value if issue_hit else IssueType.UNKNOWN
        start = min(part_hit.start, issue_hit.start if issue_hit else part_hit.start)
        end = max(part_hit.end, issue_hit.end if issue_hit else part_hit.end)
        claims.append(
            _ClaimHit(
                claim=DamageClaim(
                    issue_type=issue,
                    object_part=part_hit.value,
                    issue_family=_issue_family(issue),
                    source_text=_source_excerpt(text, start, end),
                ),
                position=start,
            )
        )

    if not claims and issue_hits:
        unknown_part = UNKNOWN_PART_BY_OBJECT[claim_object]
        for issue_hit in issue_hits:
            claims.append(
                _ClaimHit(
                    claim=DamageClaim(
                        issue_type=issue_hit.value,
                        object_part=unknown_part,
                        issue_family=_issue_family(issue_hit.value),
                        source_text=_source_excerpt(text, issue_hit.start, issue_hit.end),
                    ),
                    position=issue_hit.start,
                )
            )

    return _dedupe_claim_hits(claims)


def _find_part_hits(text: str, claim_object: ClaimObject) -> list[_Hit]:
    hits: list[_Hit] = []
    for part, phrases in PART_PHRASES_BY_OBJECT[claim_object]:
        for phrase in phrases:
            hits.extend(_phrase_hits(text, phrase, part))
            
    filtered: list[_Hit] = []
    sorted_hits = sorted(hits, key=lambda h: (h.start, -(h.end - h.start)))
    for hit in sorted_hits:
        is_sub_hit = False
        for accepted in filtered:
            if accepted.start <= hit.start and hit.end <= accepted.end:
                is_sub_hit = True
                break
        if not is_sub_hit:
            filtered.append(hit)
    return filtered


def _find_issue_hits(text: str) -> list[_Hit]:
    hits: list[_Hit] = []
    for issue, phrases in ISSUE_PHRASES:
        for phrase in phrases:
            hits.extend(_phrase_hits(text, phrase, issue))
            
    filtered: list[_Hit] = []
    sorted_hits = sorted(hits, key=lambda h: (h.start, -(h.end - h.start)))
    for hit in sorted_hits:
        is_sub_hit = False
        for accepted in filtered:
            if accepted.start <= hit.start and hit.end <= accepted.end:
                is_sub_hit = True
                break
        if not is_sub_hit:
            filtered.append(hit)
    return filtered


def _phrase_hits(text: str, phrase: str, value: IssueType | ObjectPart) -> list[_Hit]:
    flags = re.IGNORECASE
    if re.search(r"^[\w\s]+$", phrase, flags=re.ASCII):
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    else:
        pattern = re.escape(phrase)
    return [_Hit(match.start(), match.end(), value, phrase) for match in re.finditer(pattern, text, flags)]


def _nearest_issue(part_hit: _Hit, issue_hits: Sequence[_Hit]) -> _Hit | None:
    if not issue_hits:
        return None
    nearby = sorted(issue_hits, key=lambda hit: (abs(hit.start - part_hit.start), hit.start))
    best = nearby[0]
    if abs(best.start - part_hit.start) <= 120:
        return best
    return None


def _dedupe_claim_hits(claims: Iterable[_ClaimHit]) -> list[_ClaimHit]:
    deduped: list[_ClaimHit] = []
    seen: set[tuple[str, str]] = set()
    for hit in sorted(claims, key=lambda item: item.position):
        key = (hit.claim.issue_type.value, hit.claim.object_part.value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped


def _last_explicit_claim(claims: Sequence[_ClaimHit]) -> _ClaimHit:
    concrete = [hit for hit in claims if hit.claim.issue_type != IssueType.UNKNOWN or hit.claim.object_part.value != "unknown"]
    if not concrete:
        concrete = list(claims)
    if not concrete:
        return None
    concrete.sort(key=lambda hit: (
        _part_specificity(hit.claim.object_part),
        _issue_specificity(hit.claim.issue_type),
        hit.position,
    ))
    return concrete[-1]


def _is_compound(text: str, claims: Sequence[_ClaimHit]) -> bool:
    distinct_parts = {hit.claim.object_part.value for hit in claims if hit.claim.object_part.value != "unknown"}
    distinct_pairs = {(hit.claim.issue_type.value, hit.claim.object_part.value) for hit in claims}
    return _has_compound_marker(text) and (len(distinct_parts) > 1 or len(distinct_pairs) > 1)


def _has_compound_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in COMPOUND_MARKERS)


def _fallback_claim(text: str, claim_object: ClaimObject) -> _ClaimHit:
    return _ClaimHit(
        claim=DamageClaim(
            issue_type=IssueType.UNKNOWN,
            object_part=UNKNOWN_PART_BY_OBJECT[claim_object],
            issue_family="unknown",
            source_text=_source_excerpt(text, 0, min(len(text), 80)),
        ),
        position=0,
    )


def _issue_family(issue_type: IssueType) -> str:
    if issue_type in {IssueType.DENT, IssueType.SCRATCH}:
        return "dent or scratch"
    if issue_type in {IssueType.CRACK, IssueType.GLASS_SHATTER, IssueType.BROKEN_PART, IssueType.MISSING_PART}:
        return "crack, broken, or missing part"
    if issue_type in {IssueType.TORN_PACKAGING, IssueType.CRUSHED_PACKAGING}:
        return "crushed, torn, or seal damage"
    if issue_type in {IssueType.WATER_DAMAGE, IssueType.STAIN}:
        return "water, stain, or label damage"
    if issue_type == IssueType.NONE:
        return "no visible issue claimed"
    return "unknown"


def _source_excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 70)
    right = min(len(text), end + 70)
    return text[left:right].strip()


def _normalized_claim(
    claim_object: ClaimObject,
    primary: DamageClaim,
    secondary: Sequence[DamageClaim],
) -> str:
    claims = (primary, *secondary)
    rendered = [f"{claim.object_part.value}:{claim.issue_type.value}" for claim in claims]
    return f"{claim_object.value} " + " + ".join(rendered)


def _is_negated(text: str, start: int, end: int) -> bool:
    left = max(0, start - 25)
    right = min(len(text), end + 35)
    window = text[left:right].lower()
    for pattern in NEGATION_PATTERNS:
        if re.search(pattern, window):
            return True
    extended_right = min(len(text), end + 90)
    extended_window = text[left:extended_right].lower()
    if re.search(r"not\s+what\s+i\s+want\s+to\s+claim", extended_window):
        return True
    return False


def _part_specificity(part: ObjectPart) -> int:
    val = part.value
    # Level 2: Specific components
    if val in {
        "headlight", "taillight", "windshield", "side_mirror",
        "screen", "keyboard", "trackpad", "hinge", "port",
        "seal", "label", "contents", "item"
    }:
        return 2
    # Level 1: Panels and areas
    if val in {
        "front_bumper", "rear_bumper", "door", "hood", "fender",
        "quarter_panel", "corner", "package_corner", "package_side"
    }:
        return 1
    # Level 0: Whole/Generic
    return 0


def _issue_specificity(issue: IssueType) -> int:
    if issue in {IssueType.WATER_DAMAGE, IssueType.CRUSHED_PACKAGING, IssueType.TORN_PACKAGING, IssueType.GLASS_SHATTER}:
        return 3
    if issue in {IssueType.DENT, IssueType.SCRATCH, IssueType.CRACK, IssueType.STAIN, IssueType.MISSING_PART}:
        return 2
    if issue in {IssueType.BROKEN_PART}:
        return 1
    return 0


def _find_best_part(part_hits: Sequence[_Hit], claim_object: ClaimObject) -> ObjectPart:
    if not part_hits:
        return UNKNOWN_PART_BY_OBJECT[claim_object]
    sorted_parts = sorted(part_hits, key=lambda h: (_part_specificity(h.value), h.start))
    return sorted_parts[-1].value


def _find_best_issue(issue_hits: Sequence[_Hit]) -> IssueType:
    if not issue_hits:
        return IssueType.UNKNOWN
    sorted_issues = sorted(issue_hits, key=lambda h: (_issue_specificity(h.value), h.start))
    return sorted_issues[-1].value

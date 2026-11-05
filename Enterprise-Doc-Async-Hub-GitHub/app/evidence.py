import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.parser import SourceDocument

FIELD_NAMES = ("party_a", "contract_amount", "currency")


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: Literal["party_a", "contract_amount", "currency"]
    value: str = Field(min_length=1, max_length=255)
    source_id: str = Field(pattern=r"^s\d{5}$")
    quote: str = Field(min_length=1, max_length=600)


class Findings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidates: list[Candidate] = Field(max_length=30)
    review_reasons: list[str] = Field(max_length=10)


def amount_supported(value: str, quote: str) -> bool:
    if not re.fullmatch(r"\d{1,15}(?:\.\d{1,2})?", value):
        return False
    expected = Decimal(value)
    for match in re.finditer(r"(?<![\d.,])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)(?![\d.,])\s*(万|亿)?", quote):
        scale = {None: 1, "万": 10000, "亿": 100000000}[match.group(2)]
        if Decimal(match.group(1).replace(",", "")) * scale == expected:
            return True
    return False


def supported(candidate: Candidate, document: SourceDocument) -> tuple[bool, str]:
    source = next((item for item in document.sources if item.id == candidate.source_id), None)
    if source is None or candidate.quote not in source.text:
        return False, "SOURCE_OR_QUOTE_NOT_FOUND"
    if candidate.field == "contract_amount":
        anchors = ("总金额", "总价", "合同金额", "合同价款", "合计", "总额", "total")
        ok = any(word in candidate.quote.lower() for word in anchors)
        ok = ok and amount_supported(candidate.value, candidate.quote)
    elif candidate.field == "party_a":
        after_label = re.split(r"甲方\s*[:：]?", candidate.quote, maxsplit=1)
        ok = len(after_label) == 2 and candidate.value in re.split(r"乙方|\n", after_label[-1])[0]
    else:
        names = {"CNY": ("人民币", "CNY", "RMB"), "USD": ("美元", "USD"),
                 "EUR": ("欧元", "EUR"), "JPY": ("日元", "JPY"), "HKD": ("港币", "HKD")}
        ok = any(word in candidate.quote.upper() for word in names.get(candidate.value, ()))
    return bool(ok), "SUPPORTED" if ok else "VALUE_OR_ROLE_NOT_SUPPORTED"


def reconcile(findings: Findings, document: SourceDocument, read_ids: set[str]) -> dict:
    evidence = []
    values = {field: set() for field in FIELD_NAMES}
    reasons = set(findings.review_reasons)
    for candidate in findings.candidates:
        ok, reason = supported(candidate, document)
        source = next((item for item in document.sources if item.id == candidate.source_id), None)
        evidence.append({**candidate.model_dump(), "supported": ok, "check": reason,
                         "location": source.location if source else None})
        if ok:
            value = candidate.value
            if candidate.field == "contract_amount":
                value = f"{Decimal(value):.2f}"
            values[candidate.field].add(value)
        else:
            reasons.add(f"INVALID_EVIDENCE:{candidate.field}")
    fields = {}
    conflicts = {}
    for field, alternatives in values.items():
        fields[field] = next(iter(alternatives)) if len(alternatives) == 1 else None
        if len(alternatives) > 1:
            conflicts[field] = sorted(alternatives)
            reasons.add(f"CONFLICT:{field}")
        elif not alternatives:
            reasons.add(f"MISSING:{field}")
    total = len(document.sources)
    read = len(read_ids & {item.id for item in document.sources})
    if read < total:
        reasons.add("INCOMPLETE_SOURCE_COVERAGE")
    return {"fields": fields, "evidence": evidence, "conflicts": conflicts,
            "review_status": "NEEDS_REVIEW" if reasons else "SUPPORTED",
            "review_reasons": sorted(reasons), "coverage": {"read": read, "total": total}}

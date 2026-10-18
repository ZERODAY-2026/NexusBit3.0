"""Structured key-terms table built from rule facts.

Each rule fact is an exact document span, so every value here is verified by construction. The fact's
own sentence decides which field it belongs to. A fact that fits no field is left out of the table
(it still appears among the raw facts), so the table never guesses.
"""
from __future__ import annotations

import re

from lexlocal.models import Chunk, Document, Fact, KeyTerm

# Field order is display order.
FIELDS = ["Parties", "Term", "Lock-in", "Probation", "Rent", "Salary", "Deposit", "Notice period",
          "Penalties and charges", "Restriction period", "Key dates", "Governing law and courts"]

_KW = {
    "deposit": r"\bdeposit\b",
    "penalty": r"penalt|\blate\b|\bfine\b|liquidated|forfeit|interest\s+(?:at|of)|repay|reimburse|\bbond\b|deduct|damages"
               r"|delay|training\s+cost|\bresign",
    "rent": r"\brent\b|licen[cs]e\s+fee|\blease\s+rent|monthly\s+(?:rent|charge|fee|compensation)",
    "salary": r"\bsalary\b|\bctc\b|cost\s+to\s+company|remuneration|stipend|\bwages?\b|compensation|\bpay\b|bonus",
    "lockin": r"lock[- ]?in",
    "probation": r"probation",
    "term": r"\bterm\b|tenancy|period\s+of|commenc|licen[cs]e\s+period|valid\s+for|duration",
    "restriction": r"after\s+leaving|non[- ]?compete|not\s+(?:join|solicit|work)|after\s+(?:the\s+)?(?:termination|cessation)",
    "start": r"\bfrom\b|commenc|with\s+effect\s+from|effective|joining|starting|start",
    "end": r"\bend(?:ing|s)?\b|expir|until|till|up\s+to",
    "signed": r"made|executed|signed|entered\s+into|dated",
}


def _has(key: str, text: str) -> bool:
    return re.search(_KW[key], text, re.IGNORECASE) is not None


def _local(f: Fact, doc: Document, width: int = 120) -> str:
    """Words around the fact, clipped to its sentence: decides fields when a sentence holds two facts."""
    q0 = doc.text.rfind(f.quote, 0, f.end + len(f.quote))
    lo, hi = (q0, q0 + len(f.quote)) if 0 <= q0 <= f.start else (0, len(doc.text))
    return doc.text[max(f.start - width, lo):min(f.end + width // 2, hi)]


def _date_label(f: Fact, doc: Document) -> str:
    before = doc.text[max(f.start - 60, 0):f.start]
    if _has("end", before):
        return "End date"
    if _has("start", before):
        return "Start date"
    if _has("signed", f.quote[: max(f.quote.find(f.value), 0) + 1] or before):
        return "Signed on"
    return "Date"


def classify(f: Fact, doc: Document, doc_type: str,
             notice_spans: list[tuple[int, int]] = ()) -> tuple[str, str] | None:
    """(field, label) for a fact, or None if it doesn't clearly belong to a field."""
    s, near = f.quote, _local(f, doc)
    if f.type == "party":
        return "Parties", "Party"
    if f.type == "role":
        return "Parties", "Role"
    if f.type == "governing_law":
        return "Governing law and courts", "Courts" if "court" in f.value.lower() else "Law"
    if f.type == "notice_period":
        return "Notice period", "Notice"
    if f.type == "date":
        return "Key dates", _date_label(f, doc)
    if f.type in ("amount", "percentage"):
        if _has("deposit", near):
            return "Deposit", "Amount"
        if _has("penalty", near):
            return "Penalties and charges", "Amount" if f.type == "amount" else "Rate"
        if doc_type == "employment" and _has("salary", near):
            return "Salary", "Bonus" if "bonus" in near.lower() else "Amount"
        if doc_type != "employment" and _has("rent", near):
            return ("Rent", "Escalation") if f.type == "percentage" else ("Rent", "Monthly")
        return None
    if f.type == "duration":
        if re.search(r"\baged?\b", near, re.IGNORECASE):
            return None  # "aged about 58 years"
        if any(s <= f.start < e for s, e in notice_spans):
            return None  # "15 days' written notice" is already listed as a notice period
        for key, field in (("lockin", "Lock-in"), ("probation", "Probation"), ("restriction", "Restriction period")):
            if _has(key, s):
                return field, "Period"
        if _has("term", s) and not _has("penalty", s):
            return "Term", "Period"
    return None


def build_key_terms(facts: list[Fact], chunks: list[Chunk], doc: Document, doc_type: str) -> list[KeyTerm]:
    out: list[KeyTerm] = []
    seen: set[tuple[str, str]] = set()
    notice_spans = [(f.start, f.end) for f in facts if f.type == "notice_period"]
    for f in facts:
        hit = classify(f, doc, doc_type, notice_spans)
        if not hit or f.quote not in doc.text:  # quote must be verbatim document text
            continue
        field, lbl = hit
        if (field, f.value.lower()) in seen:
            continue
        seen.add((field, f.value.lower()))
        chunk = next((c for c in chunks if c.start <= f.start < c.end), None)
        out.append(KeyTerm(field=field, label=lbl, value=f.value, quote=f.quote, page=f.page,
                           chunk_id=chunk.id if chunk else ""))
    order = {name: i for i, name in enumerate(FIELDS)}
    return sorted(out, key=lambda k: order.get(k.field, 99))


# Fields a reader would expect for each document type; shown as "not found" when the rules find nothing.
EXPECTED = {
    "rental": ["Parties", "Term", "Rent", "Deposit", "Notice period", "Governing law and courts"],
    "employment": ["Parties", "Salary", "Probation", "Notice period", "Governing law and courts"],
}

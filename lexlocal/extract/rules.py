"""Deterministic extraction of facts (parties, dates, amounts, durations, notice periods,
percentages, governing law). Every Fact carries an exact span of the document text, so it
is verified by construction and can corroborate numbers in LLM explanations."""
from __future__ import annotations

import re

from lexlocal.models import Document, Fact

_MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_NUMWORD = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty[- ]five|forty|sixty|ninety)"

PATTERNS: dict[str, re.Pattern] = {
    "amount": re.compile(
        r"(?:₹|\bRs\.?|\bINR|\bRupees)\s?[\d,]+(?:\.\d{1,2})?(?:\s?(?:/-|lakhs?|lacs?|crores?))?"
        r"|\b[\d,]{3,}(?:\.\d{1,2})?\s?(?:/-\s?)?(?:rupees|INR)\b",
        re.IGNORECASE,
    ),
    "date": re.compile(
        r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"
        rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?{_MONTHS},?\s+\d{{4}}\b"
        rf"|\b{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b",
        re.IGNORECASE,
    ),
    "duration": re.compile(
        rf"\b(?:\d{{1,3}}|{_NUMWORD})(?:\s*\(\s*(?:\d{{1,3}}|{_NUMWORD})\s*\))?\s*(?:calendar\s+|working\s+|business\s+)?(?:days?|weeks?|months?|years?)\b",
        re.IGNORECASE,
    ),
    "percentage": re.compile(r"\b\d{1,3}(?:\.\d{1,2})?\s?(?:%|per\s?cent|percent)", re.IGNORECASE),
    "governing_law": re.compile(
        # (?-i:...) keeps place names capitalised: under IGNORECASE, [A-Z] would also swallow "and the courts ...".
        r"(?:governed\s+by|construed\s+in\s+accordance\s+with|subject\s+to)\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?the\s+laws\s+of\s+"
        r"(?:the\s+)?(?:(?-i:State)\s+of\s+)?(?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})"
        r"|(?:exclusive\s+)?jurisdiction\s+of\s+(?:the\s+)?courts?\s+(?:at|of|in)\s+(?-i:[A-Z][a-z]{2,30}(?:\s+[A-Z][a-z]+)?)"
        r"|courts?\s+(?:at|of|in)\s+(?-i:[A-Z][a-z]{2,30})\s+shall\s+have\s+(?:exclusive\s+)?jurisdiction",
        re.IGNORECASE,
    ),
    "party": re.compile(
        r"(?:between|by and between)\s+(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|M/s\.?)?\s*([A-Z][A-Za-z.&' ]{2,60}?)(?:,|\s+\(|\s+son|\s+daughter|\s+wife|\s+aged|\s+residing|\s+having|\s+hereinafter)"
        r"|\b(?:and|AND|And)\s+(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|M/s\.?)\s*([A-Z][A-Za-z.&' ]{2,60}?)(?:,|\s+\(|\s+son|\s+daughter|\s+wife|\s+aged|\s+residing|\s+having|\s+hereinafter)",
    ),
    "role": re.compile(
        r"hereinafter\s+(?:called|referred\s+to\s+as|known\s+as)\s+(?:the\s+)?[\"“']?(Landlord|Tenant|Lessor|Lessee|Licensor|Licensee|Owner|Employer|Employee|Company)[\"”']?",
        re.IGNORECASE,
    ),
}

_NOTICE = re.compile(
    rf"(?:(?:\d{{1,3}}|{_NUMWORD})(?:\s*\(\s*(?:\d{{1,3}}|{_NUMWORD})\s*\))?\s*(?:days?|weeks?|months?)['’]?s?\s+(?:prior\s+|advance\s+)?(?:written\s+)?notice"
    rf"|notice\s+(?:period\s+)?of\s+(?:at\s+least\s+)?(?:\d{{1,3}}|{_NUMWORD})(?:\s*\(\s*(?:\d{{1,3}}|{_NUMWORD})\s*\))?\s*(?:days?|weeks?|months?))",
    re.IGNORECASE,
)


# ". " after these is not a sentence end ("Rs. 25,000", "No. 14", "Mr. Kumar", "Pvt. Ltd. having").
_ABBREV = re.compile(r"(?:\b(?:Rs|No|Nos|Mr|Mrs|Ms|Dr|Shri|Smt|Pvt|Ltd|Co|St|vs|viz|i\.e|e\.g|cl|art|sec)|\b[A-Z])$", re.IGNORECASE)


def _is_stop(text: str, i: int) -> bool:
    return not _ABBREV.search(text[max(0, i - 6):i])


def _next_stop(text: str, pos: int) -> int:
    i = text.find(". ", pos)
    while i != -1 and not _is_stop(text, i):
        i = text.find(". ", i + 2)
    return i


def _last_stop(text: str, pos: int) -> int:
    i = text.rfind(". ", 0, pos)
    while i != -1 and not _is_stop(text, i):
        i = text.rfind(". ", 0, i)
    return i


def _sentence_around(text: str, start: int, end: int, limit: int = 260) -> tuple[int, int]:
    """Expand [start,end) to the enclosing sentence (exact offsets), capped at `limit`."""
    s = max(_last_stop(text, start), text.rfind("\n", 0, start))
    s = 0 if s < 0 else s + 1
    e_candidates = [i for i in (_next_stop(text, end), text.find("\n", end)) if i != -1]
    e = min(e_candidates) + 1 if e_candidates else len(text)
    if e - s > limit:
        s = max(s, start - limit // 2)
        e = min(e, end + limit // 2)
    while s < start and text[s].isspace():
        s += 1
    return s, e


def extract_facts(doc: Document) -> list[Fact]:
    text = doc.text
    facts: list[Fact] = []
    seen: set[tuple[str, str]] = set()

    def add(ftype: str, value: str, ms: int, me: int):
        value = re.sub(r"\s+", " ", value).strip(" ,.")
        # The same duration can mean different things in different clauses (term vs lock-in), so durations
        # are de-duplicated per sentence; other facts once per document.
        key = (ftype, value.lower()) if ftype != "duration" else (ftype, value.lower(), _sentence_around(text, ms, me)[0])
        if not value or key in seen:
            return
        seen.add(key)
        s, e = _sentence_around(text, ms, me)
        facts.append(Fact(type=ftype, value=value, quote=text[s:e].strip(), page=doc.page_for_offset(ms), start=ms, end=me))

    for ftype, pat in PATTERNS.items():
        for m in pat.finditer(text):
            if ftype in ("party", "role"):
                g = next((g for g in m.groups() if g), None)
                if g:
                    add("party" if ftype == "party" else "role", g, m.start(), m.end())
            else:
                add(ftype, m.group(0), m.start(), m.end())
    for m in _NOTICE.finditer(text):
        add("notice_period", m.group(0), m.start(), m.end())
    return facts


def numbers_in(text: str) -> set[str]:
    """Normalized numeric tokens (digits only, commas removed) for corroboration checks."""
    return {n.replace(",", "").lstrip("0") or "0" for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


_WORD2NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
             "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15",
             "twenty": "20", "thirty": "30", "forty": "40", "sixty": "60", "ninety": "90"}


def numbers_with_words(text: str) -> set[str]:
    nums = numbers_in(text)
    low = text.lower()
    for w, n in _WORD2NUM.items():
        if re.search(rf"\b{w}\b", low):
            nums.add(n)
    return nums

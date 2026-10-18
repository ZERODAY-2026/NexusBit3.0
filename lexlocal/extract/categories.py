"""Lexicon-based clause category tagging. Cheap, deterministic, used to route chunks to
the right LLM category prompt and as a fallback when the LLM is unavailable."""
from __future__ import annotations

import re

from lexlocal.models import Chunk

CATEGORIES: dict[str, dict] = {
    "payments": {
        "label": "Payments",
        "terms": ["rent", "salary", "remuneration", "ctc", "compensation", "deposit", "advance", "fee", "fees",
                  "payable", "pay ", "paid", "₹", "rs.", "inr", "rupees", "maintenance charge", "electricity",
                  "water charges", "escalation", "increment", "bonus", "reimburse"],
    },
    "penalties": {
        "label": "Penalties & deductions",
        "terms": ["penalty", "penalties", "late fee", "interest", "forfeit", "forfeiture", "liquidated damages",
                  "deduct", "deduction", "fine", "compensate", "damages", "recover", "bond", "clawback"],
    },
    "deadlines": {
        "label": "Deadlines & duration",
        "terms": ["on or before", "within", "commence", "commencement", "period of", "term of", "expiry",
                  "expire", "lock-in", "lock in", "probation", "months", "renewal", "renew", "due date", "by the"],
    },
    "notice": {
        "label": "Notice periods",
        "terms": ["notice", "intimation", "prior written", "advance notice", "inform in writing"],
    },
    "termination": {
        "label": "Termination",
        "terms": ["terminate", "termination", "vacate", "evict", "eviction", "dismiss", "resign", "resignation",
                  "cancel", "end this agreement", "relieve", "summary", "breach"],
    },
    "obligations": {
        "label": "Your obligations",
        "terms": ["shall", "must", "agrees to", "undertakes", "responsible for", "required to", "obliged",
                  "shall not", "keep the premises", "comply", "maintain"],
    },
    "rights": {
        "label": "Rights",
        "terms": ["entitled", "right to", "may ", "permitted", "allowed", "access", "inspect", "enjoy",
                  "peaceful", "leave", "holiday"],
    },
    "restrictions": {
        "label": "Restrictions & confidentiality",
        "terms": ["not permitted", "prohibited", "shall not", "sublet", "sub-let", "non-compete", "non compete",
                  "non-solicit", "confidential", "intellectual property", "exclusive", "pets", "alteration",
                  "restrain", "restriction"],
    },
    "liability": {
        "label": "Liability & disputes",
        "terms": ["indemnify", "indemnity", "liable", "liability", "arbitration", "arbitrator", "jurisdiction",
                  "governing law", "dispute", "court", "waive", "force majeure"],
    },
}

_COMPILED = {
    cat: [re.compile(r"(?<![a-z])" + re.escape(t.strip()) + (r"(?![a-z])" if t[-1].isalnum() else ""), re.I)
          for t in spec["terms"]]
    for cat, spec in CATEGORIES.items()
}


def score(text: str) -> dict[str, int]:
    return {cat: sum(len(p.findall(text)) for p in pats) for cat, pats in _COMPILED.items()}


def tag_chunks(chunks: list[Chunk]) -> None:
    for c in chunks:
        s = score(c.text)
        # obligations/rights terms are very common; require more evidence for them
        c.categories = [cat for cat, n in s.items() if n >= (3 if cat in ("obligations", "rights") else 1)]


def chunks_for(category: str, chunks: list[Chunk], limit: int) -> list[Chunk]:
    ranked = sorted(
        (c for c in chunks if category in c.categories),
        key=lambda c: -score(c.text)[category] / (1 + len(c.text) / 1500),
    )
    return ranked[:limit]


def label(category: str) -> str:
    return CATEGORIES.get(category, {}).get("label", category.title())


def detect_doc_type(text: str) -> str:
    low = text.lower()
    rental = sum(low.count(w) for w in ("tenant", "landlord", "lessee", "lessor", "licensee", "licensor", "rent", "premises"))
    employ = sum(low.count(w) for w in ("employee", "employer", "employment", "salary", "probation", "designation"))
    if rental == employ == 0:
        return "other"
    return "rental" if rental >= employ else "employment"

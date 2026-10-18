"""Confidence for a displayed finding, from independent signals.

Signals (each 0..1, or absent when it does not apply):
  match        verifier quote-match score (100 = exact)
  agreement    rule-LLM agreement: a rule-extracted fact inside the quote is restated in the explanation (1),
               the quote holds facts the explanation does not mention (0.5), or no facts to compare (absent)
  category     the cited clause was tagged with the finding's category by the lexicon (1) or not (0.4)
  consistency  self-consistency: a second, higher-temperature sample found the same clause (1) or not (0)
  ocr          OCR confidence of the page the quote is on (scanned PDFs only)

The weights and the High/Medium/Low thresholds were tuned on hand-labelled findings
(scripts/calibrate.py, eval/confidence_labels.yaml); see docs/EVALUATION.md for the reliability table.
"""
from __future__ import annotations

import re

from lexlocal import config
from lexlocal.models import Fact, Finding, Kind

WEIGHTS = {"match": 0.30, "agreement": 0.20, "category": 0.20, "consistency": 0.30}
KIND_PRIOR = {Kind.explicit: 1.0, Kind.interpretation: 0.85, Kind.concern: 0.9}


def signals_for(f: Finding, quote_start: int, quote_end: int, facts: list[Fact], chunk_categories: list[str]) -> dict:
    s = {"match": round(f.match_score / 100, 3), "category": 1.0 if f.category in chunk_categories else 0.4}
    inside = [x for x in facts if quote_start <= x.start < quote_end and x.type in
              ("amount", "date", "duration", "notice_period", "percentage")]
    if inside:
        text = f.plain_explanation.lower().replace(",", "")
        s["agreement"] = 1.0 if any(_key(x.value) and re.search(rf"\b{re.escape(_key(x.value))}\b", text)
                                    for x in inside) else 0.5
    return s


def _key(v: str) -> str:
    """The comparable core of a fact value: its digits ("Rs. 25,000/-" -> "25000"), else its first word ("one month's" -> "one")."""
    digits = "".join(ch for ch in v if ch.isdigit())
    return digits or (re.findall(r"[a-z]+", v.lower()) or [""])[0]


def combine(signals: dict, kind: Kind, ambiguous: bool = False) -> float:
    """Weighted mean of the available signals, times a kind prior; OCR confidence multiplies."""
    used = {k: w for k, w in WEIGHTS.items() if k in signals}
    score = sum(signals[k] * w for k, w in used.items()) / sum(used.values())
    score *= KIND_PRIOR[kind]
    if ambiguous:
        score *= 0.92
    if "ocr" in signals:
        score *= 0.5 + 0.5 * signals["ocr"]
    return round(min(max(score, 0.0), 1.0), 3)


def label(score: float) -> str:
    return "High" if score >= config.CONF_HIGH else "Medium" if score >= config.CONF_MEDIUM else "Low"

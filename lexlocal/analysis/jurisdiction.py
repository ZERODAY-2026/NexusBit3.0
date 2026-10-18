"""Jurisdiction-aware notes: which Indian state the document points to, and which state-dependent topics it raises.

Every note is general information. Notes never state a statutory limit or number, and never conclude
whether a clause is legal, valid, enforceable or fair. They only say that rules differ and who can confirm.
"""
from __future__ import annotations

import re

from lexlocal import knowledge
from lexlocal.extract.rules import _sentence_around
from lexlocal.models import Document, Fact, JurisdictionInfo, JurisdictionNote

STATES = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
          "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
          "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
          "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry", "Chandigarh"]

CITY_STATE = {
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka", "mysore": "Karnataka",
    "mangaluru": "Karnataka", "mangalore": "Karnataka", "hubballi": "Karnataka", "hubli": "Karnataka",
    "dharwad": "Karnataka", "belagavi": "Karnataka", "mumbai": "Maharashtra", "pune": "Maharashtra",
    "nagpur": "Maharashtra", "thane": "Maharashtra", "nashik": "Maharashtra", "chennai": "Tamil Nadu",
    "coimbatore": "Tamil Nadu", "madurai": "Tamil Nadu", "hyderabad": "Telangana", "secunderabad": "Telangana",
    "warangal": "Telangana", "visakhapatnam": "Andhra Pradesh", "vijayawada": "Andhra Pradesh",
    "kochi": "Kerala", "cochin": "Kerala", "thiruvananthapuram": "Kerala", "kozhikode": "Kerala",
    "new delhi": "Delhi", "delhi": "Delhi", "gurugram": "Haryana", "gurgaon": "Haryana", "noida": "Uttar Pradesh",
    "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh", "kolkata": "West Bengal", "ahmedabad": "Gujarat",
    "surat": "Gujarat", "vadodara": "Gujarat", "jaipur": "Rajasthan", "bhopal": "Madhya Pradesh",
    "indore": "Madhya Pradesh", "chandigarh": "Chandigarh", "bhubaneswar": "Odisha", "patna": "Bihar",
    "guwahati": "Assam", "panaji": "Goa", "dehradun": "Uttarakhand", "ranchi": "Jharkhand", "raipur": "Chhattisgarh",
}

_PLACE_SIGNED = re.compile(r"\b(?:made|executed|entered\s+into|signed)(?:\s+and\s+executed)?\s+at\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)")
_CITY_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, CITY_STATE), key=len, reverse=True)) + r")\b", re.IGNORECASE)


def _state_of(text: str) -> str | None:
    for s in STATES:
        if re.search(rf"\b{re.escape(s)}\b", text, re.IGNORECASE):
            return s
    m = _CITY_RE.search(text)
    return CITY_STATE[m.group(1).lower()] if m else None


def detect(doc: Document, facts: list[Fact]) -> JurisdictionInfo:
    """Pick the state from, in order: governing law naming a state, courts' city, place of signing."""
    gl = [f for f in facts if f.type == "governing_law"]
    for kind, items in (("governing law", [f for f in gl if "court" not in f.value.lower()]),
                        ("courts", [f for f in gl if "court" in f.value.lower()])):
        for f in items:
            st = _state_of(f.value)
            if st:
                return JurisdictionInfo(state=st, basis=kind, value=f.value, quote=f.quote, page=f.page,
                                        country_law="India" if "india" in " ".join(g.value.lower() for g in gl) else "")
    m = _PLACE_SIGNED.search(doc.text)
    if m and _state_of(m.group(1)):
        s, e = _sentence_around(doc.text, m.start(), m.end())
        return JurisdictionInfo(state=_state_of(m.group(1)), basis="place of signing", value=m.group(1),
                                quote=doc.text[s:e].strip(), page=doc.page_for_offset(m.start()),
                                country_law="India" if any("india" in g.value.lower() for g in gl) else "")
    return JurisdictionInfo(country_law="India" if any("india" in g.value.lower() for g in gl) else "")


def notes(doc: Document, facts: list[Fact]) -> tuple[JurisdictionInfo, list[JurisdictionNote]]:
    info = detect(doc, facts)
    who = f"a lawyer who practises in {info.state}" if info.state else "a local lawyer"
    out: list[JurisdictionNote] = []
    low = doc.text.lower()
    for topic, spec in knowledge.load("jurisdiction_topics.json").items():
        if isinstance(spec, str):  # older format: {"topic": "note"}
            spec = {"match": [topic], "note": spec}
        if not isinstance(spec, dict):
            continue
        # Every mention of any match term, in document order; cite a real sentence rather than an ALL-CAPS heading.
        spans = sorted((m.start(),) + _sentence_around(doc.text, m.start(), m.end())
                       for term in spec.get("match", []) for m in re.finditer(re.escape(term.lower()), low))
        if not spans:
            continue
        i, s, e = next(((i, s, e) for i, s, e in spans if not doc.text[s:e].strip().isupper()), spans[0])
        out.append(JurisdictionNote(topic=topic, note=f"{spec['note']} {who[0].upper() + who[1:]} can confirm what applies.",
                                    quote=doc.text[s:e].strip(), page=doc.page_for_offset(i)))
    return info, out

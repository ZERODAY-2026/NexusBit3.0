"""Tolerant loaders for teammate-provided knowledge files.

Files may be missing, partial, or placeholders. List-shaped files may be either a plain
JSON list or {"_placeholder": true, "items": [...]}. Loaders never raise; on any problem
they fall back to built-in minimal defaults and record a warning.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from lexlocal import config

log = logging.getLogger("lexlocal.knowledge")

DEFAULTS: dict = {
    "checklists.json": {
        "rental": ["rent", "security deposit", "lock-in period", "notice period", "termination",
                   "maintenance and repairs", "rent escalation", "subletting", "use of premises",
                   "governing law", "dispute resolution", "utilities"],
        "employment": ["salary", "probation", "notice period", "termination", "working hours",
                       "leave", "confidentiality", "non-compete", "intellectual property",
                       "governing law", "dispute resolution", "benefits"],
    },
    "vague_terms.json": ["reasonable", "as soon as possible", "from time to time", "at its sole discretion",
                         "as deemed fit", "material breach", "promptly", "best efforts", "satisfactory",
                         "normal wear and tear", "appropriate", "substantial"],
    "glossary.json": {},
    "standard_clauses.json": {},
    "one_sided_patterns.json": ["sole discretion", "without any notice", "without assigning any reason",
                                "shall not be refunded", "forfeit"],
    "jurisdiction_topics.json": {},
    "disclaimers.json": {
        "en": {
            "disclaimer": "LexLocal explains what a document says. It is not legal advice and does not decide whether anything is legal, valid, enforceable or fair.",
            "escalation": "For a decision about your situation, consult a qualified lawyer.",
            "silent": "The document is silent on this.",
            "refusal": "I can't answer that from this document.",
        }
    },
}

_warnings: list[str] = []


def _unwrap(name: str, data):
    if isinstance(data, dict) and "items" in data and isinstance(DEFAULTS[name], list):
        data = data["items"]
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if not k.startswith("_")}
    if type(data) is not type(DEFAULTS[name]):
        raise ValueError(f"expected {type(DEFAULTS[name]).__name__}")
    return data


@lru_cache(maxsize=None)
def load(name: str):
    path = config.KNOWLEDGE_DIR / name
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = _unwrap(name, raw)
        if not data:
            raise ValueError("empty")
        return data
    except FileNotFoundError:
        _warnings.append(f"knowledge/{name} missing — using built-in defaults")
    except Exception as e:  # malformed / partial file
        _warnings.append(f"knowledge/{name} unusable ({e}) — using built-in defaults")
    log.warning("knowledge file %s unavailable, using defaults", name)
    return DEFAULTS[name]


def checklist(doc_type: str) -> list[str]:
    cl = load("checklists.json")
    for key in cl:
        if key.lower().startswith(doc_type.lower()[:4]):  # rental/rent/lease, employment/employ
            return list(cl[key])
    if doc_type == "rental":
        for key in cl:
            if "lease" in key.lower() or "rent" in key.lower():
                return list(cl[key])
    return list(cl.get(doc_type, []))


def disclaimer(lang: str = "en") -> dict:
    d = load("disclaimers.json")
    base = DEFAULTS["disclaimers.json"]["en"]
    return {**base, **d.get("en", {}), **d.get(lang, {})}


def warnings() -> list[str]:
    return list(_warnings)

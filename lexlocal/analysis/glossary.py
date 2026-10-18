"""Glossary of legal terms that appear in the document.

Definitions come from knowledge/glossary.json (written by the team). Recognised legal terms that the
glossary does not cover are explained by the local model, labelled as such, verdict-scrubbed, and
rejected if they contain numbers (a general meaning never needs one).
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from lexlocal import knowledge
from lexlocal.analysis import guardrails
from lexlocal.extract.rules import _sentence_around
from lexlocal.models import Document, GlossaryEntry

log = logging.getLogger("lexlocal.glossary")

# Legal terms worth explaining when present. Anything here without a glossary entry goes to the model.
CANDIDATES = ["lien", "covenant", "encumbrance", "novation", "severability", "subrogation", "estoppel",
              "power of attorney", "notarised", "affidavit", "caveat", "easement", "mesne profits", "holding over",
              "set-off", "pro rata", "bona fide", "mutatis mutandis", "inter alia", "in perpetuity", "joint and several",
              "time is of the essence", "survival", "entire agreement", "counterparts", "gratuity", "provident fund",
              "notice pay", "full and final settlement", "relieving letter", "moonlighting", "bond"]


class DefOut(BaseModel):
    definitions: list[str]


PROMPT = """Give the general, plain-English meaning of each legal term below in one short sentence each.
Describe what the term usually means. Do not mention numbers, do not say whether anything is legal, valid,
enforceable or fair, and do not refer to any particular document.
Return JSON {{"definitions": [...]}} with exactly {n} strings in the same order.

{items}"""


def _find(term: str, low: str) -> int:
    m = re.search(rf"\b{re.escape(term.lower())}\w{{0,3}}\b", low)
    return m.start() if m else -1


def build(doc: Document, llm=None, max_model_terms: int = 6) -> list[GlossaryEntry]:
    gloss = {k.lower(): v for k, v in knowledge.load("glossary.json").items() if isinstance(v, str)}
    low = doc.text.lower()
    out: list[GlossaryEntry] = []
    seen_spans: list[tuple[int, int]] = []
    # Longest terms first, so "material breach" wins over "breach" at the same place.
    for term in sorted(gloss, key=len, reverse=True):
        i = _find(term, low)
        if i < 0 or any(s <= i < e for s, e in seen_spans):
            continue
        seen_spans.append((i, i + len(term)))
        s, e = _sentence_around(doc.text, i, i + len(term))
        out.append(GlossaryEntry(term=term, definition=gloss[term], source="glossary",
                                 example=doc.text[s:e].strip(), page=doc.page_for_offset(i)))
    missing = [t for t in CANDIDATES if t not in gloss and _find(t, low) >= 0][:max_model_terms]
    if missing and llm is not None and llm.health().get("ok"):
        from lexlocal.llm import prompts
        from lexlocal.llm.client import LLMError

        try:
            r = llm.generate_json(prompts.BASE_SYSTEM,
                                  PROMPT.format(n=len(missing), items="\n".join(f"{k + 1}. {t}" for k, t in enumerate(missing))),
                                  DefOut, max_tokens=120 + 60 * len(missing))
            if len(r.definitions) == len(missing):
                for term, d in zip(missing, r.definitions):
                    d, _ = guardrails.scrub_verdicts(d)
                    if d.strip() and not re.search(r"\d", d):
                        i = _find(term, low)
                        s, e = _sentence_around(doc.text, i, i + len(term))
                        out.append(GlossaryEntry(term=term, definition=d.strip(), source="model",
                                                 example=doc.text[s:e].strip(), page=doc.page_for_offset(i)))
        except LLMError as e:
            log.warning("glossary model call failed: %s", type(e).__name__)
    return sorted(out, key=lambda g: g.term)

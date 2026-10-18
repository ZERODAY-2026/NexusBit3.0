"""Guardrails: question classification, legal-verdict scrubbing, prompt-injection scan."""
from __future__ import annotations

import logging
import re
from typing import Optional

from lexlocal.models import Chunk, Document, InjectionFlag

log = logging.getLogger("lexlocal.guardrails")

# ------------------------------------------------------------------ classification
_VERDICT_Q = re.compile(
    r"\b(enforceable|unenforceable|enforce(?:d)?\s+(?:in|by)\s+court|legal(?:ly)?|illegal|unlawful|lawful|valid(?:ity)?|invalid|void"
    r"|fair|unfair|reasonable\s+(?:clause|term|for me)|binding|standard\s+(?:clause|practice|term)|is\s+(?:this|it|that)\s+(?:normal|ok(?:ay)?|common|a\s+good|bad|safe)"
    r"|should\s+i|shall\s+i\s+sign|do\s+i\s+have\s+to\s+sign|can\s+i\s+sue|sue\b|take\s+(?:them|him|her|the\s+\w+)\s+to\s+court|win\s+(?:in\s+court|the\s+case)"
    r"|against\s+the\s+law|allowed\s+by\s+law|my\s+legal\s+rights|legal\s+advice|advise\s+me|what\s+would\s+you\s+do|recommend|good\s+deal|rip[- ]?off|scam"
    r"|can\s+(?:they|he|she|the\s+(?:landlord|employer|company|owner))\s+(?:legally|really)\s+)",
    re.I,
)
_OUT_OF_SCOPE_Q = re.compile(
    r"\b(weather|capital\s+of|recipe|cricket|movie|song|python\s+code|write\s+(?:me\s+)?(?:a\s+|an\s+)?(?:poem|story|code|essay|song|email)|joke|who\s+won"
    r"|stock\s+price|bitcoin|translate\s+this\s+sentence|what\s+is\s+your\s+name|tell\s+me\s+about\s+yourself|news|election|prime\s+minister|president)\b",
    re.I,
)
_DOC_HINT = re.compile(
    r"\b(rent|deposit|notice|terminate|termination|lease|tenant|landlord|salary|probation|leave|clause|agreement|contract|document"
    r"|pay|penalty|fee|pet|sublet|maintenance|employer|employee|bonus|non[- ]compete|confidential|lock[- ]in|vacate|renew|increase|escalat)\w*",
    re.I,
)


def classify_rules(question: str) -> Optional[str]:
    q = question.strip()
    if _VERDICT_Q.search(q):
        return "legal_verdict"
    if _OUT_OF_SCOPE_Q.search(q) and not _DOC_HINT.search(q):
        return "out_of_scope"
    return None


def classify(question: str, llm=None) -> tuple[str, str]:
    """Return (qtype, method). Rules first (high-precision), LLM next, safe default last."""
    r = classify_rules(question)
    if r:
        return r, "rules"
    if llm is not None:
        try:
            from lexlocal.llm.prompts import CLASSIFY_SYSTEM, ClassifyOut

            out = llm.generate_json(CLASSIFY_SYSTEM, f'Question: "{question}"', ClassifyOut, max_tokens=60)
            return out.qtype, "llm"
        except Exception as e:  # LLM down -> safe default
            log.warning("classifier llm failed: %s", type(e).__name__)
    # Default: treat as a document question; it will only be answered from verified quotes.
    return ("document_fact" if _DOC_HINT.search(question) or llm is None else "document_fact"), "default"


# ------------------------------------------------------------------ verdict scrubbing
_VERDICT_SENT = re.compile(
    r"\b(?:is|are|be|being|seems?|appears?|looks?|likely|probably|clearly|may\s+be|might\s+be|could\s+be|would\s+be|not)\s+(?:\w+\s+){0,2}"
    r"(?:legal|illegal|unlawful|lawful|legally\s+valid|invalid|void|voidable|enforceable|unenforceable|fair|unfair|legally\s+binding|legitimate)\b"
    r"|\b(?:illegal|unlawful|unenforceable|null\s+and\s+void|against\s+the\s+law|violates?\s+(?:the\s+)?(?:law|act))\b"
    r"|\byou\s+should\s+(?:not\s+)?(?:sign|accept|agree|refuse|reject)\b|\bi\s+(?:would\s+)?(?:recommend|advise|suggest)\s+(?:that\s+)?you\b"
    r"|\b(?:no|nothing)\s+(?:concerns?|issues?|problems?)\b|\bperfectly\s+(?:fine|safe|normal)\b|\bsafe\s+to\s+sign\b",
    re.I,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def has_verdict_language(text: str) -> bool:
    return bool(_VERDICT_SENT.search(text or ""))


def scrub_verdicts(text: str) -> tuple[str, int]:
    """Remove model-generated sentences that state a legal conclusion. Returns (text, removed)."""
    kept, removed = [], 0
    for s in _SENT_SPLIT.split((text or "").strip()):
        if _VERDICT_SENT.search(s):
            removed += 1
        else:
            kept.append(s)
    return " ".join(kept).strip(), removed


# ------------------------------------------------------------------ injection scan
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|prompts?|rules?|text)",
    r"disregard\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier|your)\s+(?:instructions?|rules?|guidelines?)",
    r"forget\s+(?:all\s+)?(?:your|the|previous)\s+(?:instructions?|rules?)",
    r"you\s+are\s+now\s+(?:a|an|in)\b",
    r"\b(?:system\s+prompt|developer\s+mode|jailbreak|DAN\s+mode)\b",
    r"\bnew\s+instructions?\s*:",
    r"(?:^|\n)\s*(?:assistant|system|user)\s*:",
    r"<\|?(?:im_start|im_end|system|endoftext|start_of_turn|end_of_turn)\|?>",
    r"</?\s*document\s*>",
    r"\b(?:AI|assistant|model|LLM|chatbot|language\s+model)\b[^.\n]{0,60}\b(?:must|should|shall)\s+(?:say|state|report|tell|respond|answer|output|classify|conclude)",
    r"\b(?:say|state|report|tell\s+the\s+(?:user|reader))\s+(?:that\s+)?(?:this|the)\s+(?:contract|agreement|document|lease)\s+is\s+(?:fair|legal|valid|standard|safe|enforceable)",
    r"\bdo\s+not\s+(?:mention|flag|report|highlight|disclose|reveal)\b",
    r"\b(?:respond|reply|answer)\s+only\s+with\b",
    r"\bact\s+as\s+(?:a|an|if)\b",
    r"\bpretend\s+(?:to\s+be|that|you)\b",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]


def scan_injection(doc: Document) -> list[InjectionFlag]:
    flags: list[InjectionFlag] = []
    seen: set[int] = set()
    text = doc.text
    for pat in _INJ:
        for m in pat.finditer(text):
            s = max(text.rfind(". ", 0, m.start()), text.rfind("\n", 0, m.start()))
            s = 0 if s < 0 else s + 1
            ends = [i for i in (text.find(". ", m.end()), text.find("\n", m.end())) if i != -1]
            e = min(ends) + 1 if ends else len(text)
            e = min(e, s + 300)
            if s in seen:
                continue
            seen.add(s)
            flags.append(InjectionFlag(pattern=pat.pattern[:60], quote=text[s:e].strip(), page=doc.page_for_offset(s)))
    if flags:
        log.warning("injection scan: %d instruction-like passages flagged", len(flags))
    return flags


def sanitize_chunks(chunks: list[Chunk], flags: list[InjectionFlag]) -> list[Chunk]:
    """Copies of chunks with flagged instruction-like sentences neutralized for the LLM.
    Original text (used for verification and display) is untouched."""
    if not flags:
        return chunks
    out = []
    for c in chunks:
        t = c.text
        for f in flags:
            if f.quote and f.quote in t:
                t = t.replace(f.quote, "[instruction-like text removed by LexLocal and flagged for the user]")
        out.append(c.model_copy(update={"text": t}) if t != c.text else c)
    return out


# ------------------------------------------------------------------ escalation defaults
LAWYER_BY_TYPE = {
    "rental": "a property / tenancy lawyer (rent-control and lease matters) in the state where the property is located",
    "employment": "an employment / labour lawyer familiar with the state where you work",
    "other": "a lawyer who handles contract matters",
}

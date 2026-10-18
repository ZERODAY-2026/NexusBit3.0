"""Grounded Q&A over the uploaded document.

document_fact  -> answer only from verified quotes; otherwise "The document is silent on this."
                  plus the closest related clauses.
legal_verdict  -> no verdict. Show what the document says + labelled general info + specific
                  escalation (type of lawyer, what to bring, questions to ask).
out_of_scope   -> decline; no general-knowledge answers.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

from lexlocal import knowledge
from lexlocal.analysis import guardrails
from lexlocal.analysis.verifier import Verifier, check_numbers
from lexlocal.llm import prompts
from lexlocal.llm.client import LLMError, OllamaClient
from lexlocal.models import Chunk, Document, Finding, Kind, QAAnswer, Severity
from lexlocal.retrieval.index import HybridIndex

log = logging.getLogger("lexlocal.qa")

# Fixed (not model-generated) refusal text for legal-verdict questions.
VERDICT_REFUSAL = ("I can't tell you whether this is legal, valid, enforceable or fair, or whether you should sign — "
                   "that is a judgement a qualified lawyer has to make for your situation.")

_GENERIC = set("""can could may might will would shall should do does did is are was were be been have has had i me my we our you your
the a an of to in on for by with and or not no any this that these those it its there here what which who whom when where why how
much many keep allowed allow permitted permit get document agreement contract say says said mention mentioned about tell regarding
under per as if than then also just only ever""".split())
_SYN = {
    "pet": ["pet", "animal", "dog", "cat", "bird"], "end": ["end", "terminat", "expir", "vacat"],
    "pay": ["pay", "rent", "salar", "amount", "rs", "inr", "fee", "₹", "remuner"],
    "leave": ["leave", "vacat", "terminat", "resign", "quit"], "quit": ["resign", "terminat", "quit", "leav"],
    "salary": ["salar", "remuner", "ctc", "compens", "pay"], "deposit": ["deposit", "advance"],
    "fire": ["terminat", "dismiss", "fire"], "rent": ["rent", "licen", "fee"], "notice": ["notice", "intimat"],
    "guest": ["guest", "visitor", "relative", "friend"], "smoke": ["smok", "tobacco"],
    "paint": ["paint", "alteration", "modif"], "late": ["late", "delay", "interest", "penalt"],
    "increase": ["increas", "escalat", "enhanc", "revis", "hike"], "repair": ["repair", "maint"],
}


def _salient(question: str) -> list[list[str]]:
    words = [w for w in re.findall(r"[a-z]+", question.lower()) if w not in _GENERIC and len(w) >= 3]
    groups = []
    for w in words:
        key = next((k for k in _SYN if w.startswith(k[:4])), None)
        groups.append(_SYN[key] if key else [w[:5]])
    return groups


def _topic_overlap(question: str, text: str) -> bool:
    groups = _salient(question)
    if not groups:
        return True
    low = text.lower()
    return any(any(s in low for s in g) for g in groups)


class QAEngine:
    def __init__(self, doc: Document, chunks: list[Chunk], doc_type: str, llm: Optional[OllamaClient] = None,
                 index: Optional[HybridIndex] = None, injection_flags=None, fact_values: Optional[list[str]] = None):
        self.doc = doc
        self.chunks = chunks
        self.doc_type = doc_type
        self.llm = llm or OllamaClient()
        self.index = index or HybridIndex(chunks)
        self.verifier = Verifier(doc, chunks)
        self.llm_chunks = {c.id: c for c in guardrails.sanitize_chunks(chunks, injection_flags or [])}
        self.fact_values = fact_values or []
        self.text = knowledge.disclaimer("en")

    def _verified(self, quote: str, hint: str) -> Optional[Finding]:
        v = self.verifier.verify(quote, hint)
        if not v.ok:
            log.info("qa quote rejected (%s)", v.reason)
            return None
        return Finding(category="qa", title="Document says", plain_explanation="", quote=v.quote, chunk_id=v.chunk_id,
                       page=v.page, kind=Kind.explicit, severity=Severity.info, confidence=v.score / 100,
                       verified=True, match_score=v.score)

    def _ground(self, question: str, hits: list[Chunk]) -> tuple[bool, str, list[Finding]]:
        try:
            out = self.llm.generate_json(prompts.BASE_SYSTEM,
                                         prompts.answer_prompt(question, [self.llm_chunks[c.id] for c in hits], 3500),
                                         prompts.AnswerOut, max_tokens=400)
        except LLMError as e:
            log.warning("qa llm failed: %s", type(e).__name__)
            return False, "", []
        cites = [f for f in (self._verified(q.quote, q.clause_id) for q in out.quotes) if f]
        answer, _ = guardrails.scrub_verdicts(out.answer)
        answer, _ = check_numbers(answer, " ".join(c.quote for c in cites), self.fact_values)
        found = out.found and bool(cites) and bool(answer) and _topic_overlap(question, " ".join(c.quote for c in cites))
        return found, answer, cites

    def ask(self, question: str) -> QAAnswer:
        t0 = time.perf_counter()
        question = (question or "").strip()[:500]
        qtype, method = guardrails.classify(question, self.llm)
        log.info("qa question classified as %s via %s", qtype, method)

        if qtype == "out_of_scope":
            return QAAnswer(question=question, qtype=qtype, seconds=time.perf_counter() - t0,
                            answer="I can only answer questions about the uploaded document. "
                                   "That question is outside its scope, so I won't answer it from general knowledge.")

        hits = [c for c, _ in self.index.search(question, k=4)]

        if qtype == "legal_verdict":
            found, _, cites = self._ground(question, hits)
            esc = self._escalation(question)
            ans = VERDICT_REFUSAL
            if cites:
                ans += " Here is what the document itself says on this topic:"
            else:
                ans += " I couldn't find a passage that directly addresses this; the closest related clauses are shown below."
            return QAAnswer(question=question, qtype=qtype, answer=ans, citations=cites,
                            related=[] if cites else hits[:3], escalation=esc["escalation"],
                            general_info=esc["general_info"], seconds=time.perf_counter() - t0)

        found, answer, cites = self._ground(question, hits)
        if not found:
            return QAAnswer(question=question, qtype=qtype, silent=True, related=hits[:3],
                            answer=self.text["silent"] + " Below are the closest related clauses, so you can check for yourself.",
                            seconds=time.perf_counter() - t0)
        return QAAnswer(question=question, qtype=qtype, answer=answer, citations=cites, seconds=time.perf_counter() - t0)

    def _escalation(self, question: str) -> dict:
        lawyer = guardrails.LAWYER_BY_TYPE.get(self.doc_type, guardrails.LAWYER_BY_TYPE["other"])
        bring = ["The full signed or draft agreement (all pages and annexures)", "Any messages/emails about the terms",
                 "Payment receipts or salary slips relevant to the question"]
        asks = [f"How does this clause apply to my situation: \"{question}\"?", "What are my options if the other party relies on this clause?",
                "Is there anything I should ask to change before signing?"]
        general = ""
        try:
            out = self.llm.generate_json(prompts.BASE_SYSTEM, prompts.escalation_prompt(question, self.doc_type),
                                         prompts.EscalationOut, max_tokens=350)
            if out.lawyer_type and not guardrails.has_verdict_language(out.lawyer_type):
                lawyer = out.lawyer_type
            bring = [b for b in out.what_to_bring if not guardrails.has_verdict_language(b)] or bring
            asks = [q for q in out.questions_to_ask if q.strip()] or asks
            general, _ = guardrails.scrub_verdicts(out.general_info)
        except LLMError:
            pass
        def clean(s: str) -> str:  # model items often end with "."; avoid "India.." and "agreement.; Any"
            return s.strip().rstrip(".;")

        esc = (f"**Consult:** {clean(lawyer)}.\n\n**Bring:** " + "; ".join(clean(b) for b in bring if clean(b)) +
               ".\n\n**Questions to ask:**\n" + "\n".join(f"- {q.strip()}" for q in asks))
        return {"escalation": esc, "general_info": general or None}

"""End-to-end analysis pipeline: chunks -> rules -> guardrail scans -> Gemma findings ->
verification -> Report. Every user-facing finding passes the Verifier; anything that does
not is moved to Report.rejected (shown only in eval/debug)."""
from __future__ import annotations

import logging
import re
import time
from typing import Callable, Optional

from lexlocal import config, knowledge
from lexlocal.analysis import confidence, consistency, glossary, guardrails, jurisdiction
from lexlocal.analysis.verifier import Verifier, check_numbers
from lexlocal.extract import categories as cats
from lexlocal.extract.rules import extract_facts
from lexlocal.extract.structured import build_key_terms
from lexlocal.ingest.chunker import chunk_document
from lexlocal.llm import prompts
from lexlocal.llm.client import LLMError, OllamaClient
from lexlocal.models import (SEVERITY_ORDER, Chunk, Document, Finding, Kind, Report, Severity,
                             StageTiming, VagueTerm)

log = logging.getLogger("lexlocal.analyzer")
Progress = Callable[[str, float], None]

ANALYSIS_CATEGORIES = ["payments", "penalties", "deadlines", "notice", "termination",
                       "obligations", "rights", "restrictions", "liability"]

# Synonyms used to decide whether a checklist clause is mentioned at all.
CLAUSE_SYNONYMS = {
    "rent": ["rent", "license fee", "licence fee", "monthly fee"],
    "security deposit": ["security deposit", "deposit", "advance amount"],
    "lock-in period": ["lock-in", "lock in", "lockin", "minimum period"],
    "notice period": ["notice period", "days notice", "days' notice", "month's notice", "months notice", "prior notice", "written notice"],
    "termination": ["terminat", "vacate", "end this agreement"],
    "maintenance and repairs": ["maintenance", "repair"],
    "rent escalation": ["escalat", "increase in rent", "rent increase", "enhance", "increment", "revise the rent",
                        "revise the license fee", "revise the licence fee", "revised rent", "revised fee"],
    "subletting": ["sublet", "sub-let", "sub let", "sub-licen", "part with possession", "assign this agreement", "assign the premises"],
    "use of premises": ["residential purpose", "use of the premises", "used for", "purpose of"],
    "governing law": ["governed by", "laws of india", "governing law", "applicable law"],
    "dispute resolution": ["arbitrat", "dispute", "jurisdiction", "court"],
    "utilities": ["electricity", "water", "utilities", "utility"],
    "stamp duty and registration": ["stamp duty", "registration", "registered"],
    "salary": ["salary", "remuneration", "ctc", "compensation", "wages", "stipend"],
    "probation": ["probation"],
    "working hours": ["working hours", "hours of work", "work hours", "working days", "shift"],
    "leave": ["leave", "holiday", "vacation"],
    "confidentiality": ["confidential"],
    "non-compete": ["non-compete", "non compete", "noncompete", "compete", "competitor"],
    "intellectual property": ["intellectual property", "inventions", "copyright", "work product"],
    "benefits": ["benefit", "insurance", "provident fund", "pf", "gratuity", "medical"],
}


def _mentioned(item: str, low_text: str) -> bool:
    syns = CLAUSE_SYNONYMS.get(item.lower())
    if syns:
        return any(re.search(r"(?<![a-z])" + re.escape(s), low_text) for s in syns)
    words = [w for w in re.findall(r"[a-z]+", item.lower()) if len(w) > 3]
    return bool(words) and all(w[:6] in low_text for w in words)


def find_missing(doc_type: str, text: str) -> list[str]:
    low = text.lower()
    return [item for item in knowledge.checklist(doc_type) if not _mentioned(item, low)]


def find_vague(doc: Document, chunks: list[Chunk]) -> list[VagueTerm]:
    out, seen = [], set()
    for term in knowledge.load("vague_terms.json"):
        if not isinstance(term, str) or not term.strip():
            continue
        pat = re.compile(r"(?<![a-z])" + re.escape(term.lower()) + r"(?![a-z])")
        for c in chunks:
            for m in pat.finditer(c.text.lower()):
                s = max(c.text.rfind(". ", 0, m.start()), c.text.rfind("\n", 0, m.start()))
                s = 0 if s < 0 else s + 1
                e_c = [i for i in (c.text.find(". ", m.end()), c.text.find("\n", m.end())) if i != -1]
                e = min(e_c) + 1 if e_c else len(c.text)
                if e - s > 300:
                    s, e = max(s, m.start() - 140), min(e, m.end() + 140)
                key = (term.lower(), c.id, s)
                if key in seen:
                    continue
                seen.add(key)
                out.append(VagueTerm(term=term, quote=c.text[s:e].strip(), page=doc.page_for_offset(c.start + s), chunk_id=c.id))
    return out


def _overlaps(a: Finding, b: Finding) -> bool:
    na, nb = a.quote.lower(), b.quote.lower()
    return na in nb or nb in na


class Analyzer:
    def __init__(self, llm: Optional[OllamaClient] = None, self_consistency: Optional[int] = None,
                 pairwise: Optional[int] = None):
        self.self_consistency = config.SELF_CONSISTENCY_CALLS if self_consistency is None else self_consistency
        self.pairwise = config.PAIRWISE_CHECKS if pairwise is None else pairwise
        self._facts: list = []
        self._chunk_cats: dict[str, list[str]] = {}
        self._page_signals: dict[int, dict] = {}  # e.g. {"ocr": 0.83} for scanned pages
        self.llm = llm or OllamaClient()

    # ----------------------------------------------------------------
    def _accept(self, report: Report, verifier: Verifier, fact_values: list[str], *, category: str, title: str,
                explanation: str, quote: str, chunk_hint: str, kind: str, severity: str, needs_lawyer: bool,
                ambiguity: str = "", source: str = "llm") -> Optional[Finding]:
        explanation, n_verdict = guardrails.scrub_verdicts(explanation)
        ambiguity, _ = guardrails.scrub_verdicts(ambiguity or "")
        if ambiguity.strip().strip(".").lower() in ("none", "null", "n/a", "na", "no", "-", "nil", "not applicable"):
            ambiguity = ""  # models sometimes fill the optional field with a placeholder
        title, n_title = guardrails.scrub_verdicts(title)
        if n_verdict or n_title:
            report.rejected.append({"reason": "verdict_language_removed", "category": category})
        v = verifier.verify(quote, chunk_hint)
        if not v.ok:
            report.rejected.append({"reason": v.reason, "category": category, "quote": quote[:300]})
            return None
        explanation, dropped = check_numbers(explanation, v.quote, fact_values)
        if dropped:
            report.rejected.append({"reason": "unsupported_number", "category": category, "dropped": dropped})
        if not explanation or not title:
            report.rejected.append({"reason": "empty_after_guardrails", "category": category})
            return None
        try:
            kind_e = Kind(kind)
        except ValueError:
            kind_e = Kind.interpretation
        try:
            sev = Severity(severity)
        except ValueError:
            sev = Severity.low
        # Deterministic concern flag: one-sided wording in the verified quote (knowledge/one_sided_patterns.json)
        one_sided = [p for p in knowledge.load("one_sided_patterns.json")
                     if isinstance(p, str) and p.lower() in v.quote.lower()]
        if one_sided and kind_e == Kind.explicit and source == "llm":
            kind_e = Kind.concern
            if sev == Severity.low:
                sev = Severity.medium
            note = f"Contains one-sided wording (\"{one_sided[0]}\") — worth asking a lawyer about."
            ambiguity = f"{ambiguity} {note}".strip() if ambiguity else note
        f = Finding(category=category, title=title[:120], plain_explanation=explanation, quote=v.quote,
                    chunk_id=v.chunk_id, page=v.page, kind=kind_e, severity=sev,
                    verified=True, needs_lawyer=needs_lawyer or kind_e == Kind.concern or sev == Severity.high,
                    ambiguity_note=ambiguity or None, match_score=v.score, source=source)
        f.signals = confidence.signals_for(f, v.start, v.end, self._facts, self._chunk_cats.get(v.chunk_id, []))
        if source == "rules":
            f.signals["agreement"] = 1.0  # the value is the rule fact itself
        f.signals.update(self._page_signals.get(v.page, {}))
        f.confidence = confidence.combine(f.signals, kind_e, bool(ambiguity))
        return f

    def _rule_findings(self, report: Report, verifier: Verifier, facts) -> list[Finding]:
        out = []
        fv = [f.value for f in facts]
        for f in facts:
            if f.type == "notice_period":
                out.append(self._accept(report, verifier, fv, category="notice", title=f"Notice period: {f.value}",
                                        explanation=f"The document mentions a notice requirement of {f.value}. Check who must give it and how.",
                                        quote=f.quote, chunk_hint="", kind="explicit", severity="medium",
                                        needs_lawyer=False, source="rules"))
            elif f.type == "amount" and re.search(r"rent|salary|deposit|fee|remuneration|ctc|penalt|interest|charge", f.quote, re.I):
                cat = "penalties" if re.search(r"penalt|late|interest|forfeit|deduct|fine", f.quote, re.I) else "payments"
                out.append(self._accept(report, verifier, fv, category=cat, title=f"Amount mentioned: {f.value}",
                                        explanation=f"The document states an amount of {f.value} in this clause.",
                                        quote=f.quote, chunk_hint="", kind="explicit", severity="medium",
                                        needs_lawyer=False, source="rules"))
        return [x for x in out if x]

    # ----------------------------------------------------------------
    def analyze(self, doc: Document, doc_type: str = "auto",
                progress: Optional[Progress] = None) -> tuple[Report, list[Chunk]]:
        progress = progress or (lambda stage, frac: None)
        timings: list[StageTiming] = []

        def stage(name: str, t0: float):
            timings.append(StageTiming(stage=name, seconds=round(time.perf_counter() - t0, 2)))

        t = time.perf_counter()
        progress("Segmenting clauses", 0.05)
        chunks = chunk_document(doc)
        cats.tag_chunks(chunks)
        if doc_type == "auto":
            doc_type = cats.detect_doc_type(doc.text)
        report = Report(doc_name=doc.name, doc_type=doc_type, model=self.llm.model, warnings=list(doc.warnings))
        report.warnings += knowledge.warnings()
        stage("segment", t)

        t = time.perf_counter()
        progress("Extracting facts (rules)", 0.1)
        facts = extract_facts(doc)
        report.facts = facts
        report.key_terms = build_key_terms(facts, chunks, doc, doc_type)
        self._facts, self._chunk_cats = facts, {c.id: c.categories for c in chunks}
        self._page_signals = {p: {"ocr": c} for p, c in (getattr(doc, "ocr_confidence", None) or {}).items()}
        fact_values = [f.value for f in facts]
        verifier = Verifier(doc, chunks)
        report.injection_flags = guardrails.scan_injection(doc)
        report.adversarial = list(doc.adversarial)
        llm_chunks = guardrails.sanitize_chunks(chunks, report.injection_flags)
        llm_by_id = {c.id: c for c in llm_chunks}
        report.vague_terms = find_vague(doc, chunks)
        report.missing_clauses = find_missing(doc_type, doc.text) if doc_type != "other" else []
        report.jurisdiction, report.jurisdiction_items = jurisdiction.notes(doc, facts)
        report.jurisdiction_notes = [f"{n.topic}: {n.note}" for n in report.jurisdiction_items]
        stage("rules", t)

        t = time.perf_counter()
        progress("Checking for conflicts and one-sided wording", 0.12)
        injected = {c.id for c in chunks if any(fl.quote[:60] in c.text for fl in report.injection_flags)}
        report.conflicts = consistency.rule_conflicts(doc, chunks, report.key_terms)
        report.unusual = consistency.unusual_clauses(doc, chunks, skip_chunks=injected)
        stage("consistency", t)

        llm_ok = self.llm.health().get("ok", False)
        if not llm_ok:
            report.warnings.append("Local model (Ollama) is not reachable — showing rule-based results only.")

        # ---- summary
        t = time.perf_counter()
        if llm_ok:
            progress("Writing plain-language summary (Gemma)", 0.15)
            pick: list[Chunk] = []
            for c in llm_chunks[:2] + [llm_by_id[c.id] for cat in ("payments", "deadlines", "termination")
                                       for c in cats.chunks_for(cat, chunks, 1)]:
                if c not in pick:
                    pick.append(c)
            try:
                out = self.llm.generate_json(prompts.BASE_SYSTEM,
                                             prompts.summary_prompt(doc_type, pick, config.CHUNK_CHAR_BUDGET),
                                             prompts.SummaryOut, max_tokens=800)
                summ, _ = guardrails.scrub_verdicts(out.summary)
                summ, _ = check_numbers(summ, " ".join(k.quote for k in out.key_points), fact_values)
                report.summary = summ
                for kp in out.key_points:
                    f = self._accept(report, verifier, fact_values, category="summary", title=kp.point[:120],
                                     explanation=kp.point, quote=kp.quote, chunk_hint=kp.clause_id,
                                     kind="explicit", severity="info", needs_lawyer=False)
                    if f:
                        report.summary_verified_quotes.append(f)
            except LLMError as e:
                report.warnings.append(f"Summary unavailable: {e}")
        stage("summary", t)

        # ---- category findings
        findings: list[Finding] = []
        cat_prompts: dict[str, str] = {}
        t = time.perf_counter()
        if llm_ok:
            for i, cat in enumerate(ANALYSIS_CATEGORIES):
                progress(f"Analysing {cats.label(cat).lower()} (Gemma)", 0.25 + 0.65 * i / len(ANALYSIS_CATEGORIES))
                sel = cats.chunks_for(cat, chunks, config.MAX_CHUNKS_PER_CATEGORY)
                if not sel:
                    continue
                sel_llm = [llm_by_id[c.id] for c in sel]
                cat_prompts[cat] = prompts.findings_prompt(cat, doc_type, sel_llm, config.CHUNK_CHAR_BUDGET)
                try:
                    out = self.llm.generate_json(prompts.BASE_SYSTEM, cat_prompts[cat], prompts.FindingsOut)
                except LLMError as e:
                    report.warnings.append(f"{cats.label(cat)}: model call failed ({e})")
                    continue
                for lf in out.findings:
                    f = self._accept(report, verifier, fact_values, category=cat, title=lf.title,
                                     explanation=lf.explanation, quote=lf.quote, chunk_hint=lf.clause_id,
                                     kind=lf.kind, severity=lf.severity, needs_lawyer=lf.needs_lawyer,
                                     ambiguity=lf.ambiguity)
                    if not f:
                        continue
                    dup = next((g for g in findings if _overlaps(f, g)), None)
                    if dup is None:
                        findings.append(f)
                    elif SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[dup.severity] or (
                            f.kind == Kind.concern and dup.kind != Kind.concern):
                        findings[findings.index(dup)] = f  # same clause: keep the stronger finding once
        stage("findings", t)

        # ---- self-consistency: resample categories with high-severity findings once at a higher temperature
        if llm_ok and self.self_consistency > 0:
            t = time.perf_counter()
            high_cats = list(dict.fromkeys(f.category for f in findings
                                           if f.severity == Severity.high and f.source == "llm" and f.category in cat_prompts))
            for cat in high_cats[:self.self_consistency]:
                progress(f"Double-checking {cats.label(cat).lower()} (Gemma, second sample)", 0.91)
                try:
                    out = self.llm.generate_json(prompts.BASE_SYSTEM, cat_prompts[cat], prompts.FindingsOut,
                                                 temperature=0.7, seed=11)
                except LLMError:
                    continue
                spans = [(v.start, v.end) for v in (verifier.verify(lf.quote, lf.clause_id) for lf in out.findings) if v.ok]
                for f in findings:
                    if f.category == cat and f.severity == Severity.high and f.source == "llm":
                        fv = verifier.verify(f.quote, f.chunk_id)
                        f.signals["consistency"] = 1.0 if any(s < fv.end and fv.start < e for s, e in spans) else 0.0
                        f.confidence = confidence.combine(f.signals, f.kind, bool(f.ambiguity_note))
            stage("self-consistency", t)

        # ---- rule-based findings fill gaps (and are the only findings if LLM is down)
        for rf in self._rule_findings(report, verifier, facts):
            if not any(_overlaps(rf, g) for g in findings):
                findings.append(rf)

        # ---- model check for contradictions between clause pairs (capped; rule conflicts are not re-checked)
        if llm_ok and self.pairwise > 0:
            t = time.perf_counter()
            progress("Checking clause pairs for contradictions (Gemma)", 0.93)
            covered = {c.chunk_a for c in report.conflicts} | {c.chunk_b for c in report.conflicts}
            extra, rej = consistency.model_conflicts(self.llm, llm_chunks, verifier, self.pairwise, covered)
            report.conflicts += extra
            report.rejected += rej
            stage("pairwise", t)

        findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], -f.confidence))
        t = time.perf_counter()
        report.glossary = glossary.build(doc, self.llm if llm_ok else None)
        stage("glossary", t)
        report.findings = findings
        report.timings = timings
        progress("Done", 1.0)
        log.info("analysis done findings=%d rejected=%d missing=%d vague=%d injection=%d",
                 len(findings), len(report.rejected), len(report.missing_clauses), len(report.vague_terms),
                 len(report.injection_flags))
        return report, chunks

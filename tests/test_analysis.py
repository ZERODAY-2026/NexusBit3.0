"""Pipeline tests with a fake LLM (deterministic, no Ollama needed)."""
import re

from lexlocal.analysis.analyzer import Analyzer
from lexlocal.analysis.qa import QAEngine
from lexlocal.ingest.parser import parse_file
from tests.conftest import SAMPLES

REAL = "the Tenant shall pay a late fee of Rs. 500/- for each week of delay"
FAKE = "the Tenant shall pay a penalty of Rs. 5,000 per day of delay and forfeit the deposit"


def _clause_of(user: str, needle: str) -> str:
    for m in re.finditer(r"\[clause (c\d+) \| page \d+\]\n(.*?)(?=\n\n\[clause|\n</document>)", user, re.S):
        if needle.lower() in m.group(2).lower():
            return m.group(1)
    return "c001"


def findings_fn(user):
    if "**penalties**" not in user:
        return {"findings": []}
    return {"findings": [
        {"title": "Late fee", "explanation": "If rent is late you pay Rs. 500 for every week of delay.",
         "quote": REAL, "clause_id": _clause_of(user, "late fee"), "kind": "explicit", "severity": "medium",
         "needs_lawyer": False, "ambiguity": ""},
        {"title": "Daily penalty", "explanation": "A Rs. 5,000 daily penalty applies.", "quote": FAKE,
         "clause_id": "c005", "kind": "concern", "severity": "high", "needs_lawyer": True, "ambiguity": ""},
        {"title": "Fair clause", "explanation": "This late fee clause is fair and enforceable. You pay weekly late fees.",
         "quote": "If the rent is not paid by the 10th day of the month", "clause_id": "c005",
         "kind": "interpretation", "severity": "low", "needs_lawyer": False, "ambiguity": ""},
        {"title": "Made-up number", "explanation": "The late fee is Rs. 750 per week.", "quote": REAL,
         "clause_id": "c005", "kind": "explicit", "severity": "low", "needs_lawyer": False, "ambiguity": ""},
    ]}


def summary_fn(user):
    return {"summary": "This is an 11 month rental agreement for a flat in Bengaluru. This agreement is legal and fair.",
            "key_points": [{"point": "Monthly rent is Rs. 25,000", "quote": "monthly rent of Rs. 25,000/- (Rupees Twenty Five Thousand only)", "clause_id": "c004"},
                           {"point": "Pets allowed", "quote": "The Tenant may keep pets with consent", "clause_id": "c004"}]}


def test_fabricated_quotes_rejected_real_kept(clean_doc, fake_llm_cls):
    llm = fake_llm_cls({"FindingsOut": findings_fn, "SummaryOut": summary_fn})
    report, chunks = Analyzer(llm).analyze(clean_doc, "auto")
    quotes = [f.quote for f in report.findings]
    assert all(f.verified and f.quote in clean_doc.text for f in report.findings)
    assert any("late fee of Rs. 500" in q for q in quotes)
    assert not any("5,000 per day" in q for q in quotes)
    assert any(r["reason"] == "not_found_in_document" for r in report.rejected)
    # verdict sentence removed, remaining sentence kept
    texts = " ".join(f.plain_explanation for f in report.findings) + report.summary
    assert "enforceable" not in texts and "legal and fair" not in texts
    # unsupported number removed
    assert "750" not in texts
    assert any(r["reason"] == "unsupported_number" for r in report.rejected)
    # summary key points: real kept, fabricated pets point dropped
    assert len(report.summary_verified_quotes) == 1


def test_missing_and_vague_and_facts(fake_llm_cls):
    doc = parse_file(SAMPLES / "rental_tricky.txt")
    report, _ = Analyzer(fake_llm_cls()).analyze(doc, "auto")
    assert report.doc_type == "rental"
    assert "governing law" in report.missing_clauses
    assert "subletting" in report.missing_clauses
    terms = {v.term for v in report.vague_terms}
    assert "sole discretion" in terms or "at its sole discretion" in terms
    assert "from time to time" in terms
    assert any(f.type == "amount" for f in report.facts)


def test_rule_only_mode_when_llm_down(clean_doc, fake_llm_cls):
    report, _ = Analyzer(fake_llm_cls(up=False)).analyze(clean_doc, "auto")
    assert any("not reachable" in w for w in report.warnings)
    assert report.findings and all(f.source == "rules" and f.verified for f in report.findings)


def test_injection_doc_flagged_and_not_sent_to_llm(fake_llm_cls):
    doc = parse_file(SAMPLES / "rental_injection.txt")
    llm = fake_llm_cls({"FindingsOut": lambda u: {"findings": []}})
    report, _ = Analyzer(llm).analyze(doc, "auto")
    assert report.injection_flags
    assert all("Ignore all previous instructions" not in user for _, user in llm.calls)


def _qa(doc, llm):
    report, chunks = Analyzer(llm).analyze(doc, "auto")
    return QAEngine(doc, chunks, report.doc_type, llm, injection_flags=report.injection_flags,
                    fact_values=[f.value for f in report.facts])


def test_qa_silent_on_pets(clean_doc, fake_llm_cls):
    # Model wrongly claims found with an inferred (non-verbatim) quote -> must become silent
    llm = fake_llm_cls({"ClassifyOut": lambda u: {"qtype": "document_fact"},
                        "AnswerOut": lambda u: {"found": True, "answer": "Pets are not allowed.",
                                                "quotes": [{"quote": "No pets are allowed in the premises", "clause_id": "c010"}]}})
    a = _qa(clean_doc, llm).ask("Can I keep a pet?")
    assert a.silent and "silent" in a.answer.lower() and a.related and not a.citations


def test_qa_silent_when_quote_off_topic(clean_doc, fake_llm_cls):
    llm = fake_llm_cls({"ClassifyOut": lambda u: {"qtype": "document_fact"},
                        "AnswerOut": lambda u: {"found": True, "answer": "Only residential use.",
                                                "quotes": [{"quote": "The Tenant shall use the Premises for residential purposes only", "clause_id": "c001"}]}})
    a = _qa(clean_doc, llm).ask("Can I keep a pet?")
    assert a.silent


def test_qa_fact_answer_with_citation(clean_doc, fake_llm_cls):
    llm = fake_llm_cls({"ClassifyOut": lambda u: {"qtype": "document_fact"},
                        "AnswerOut": lambda u: {"found": True, "answer": "The monthly rent is Rs. 25,000.",
                                                "quotes": [{"quote": "The Tenant shall pay a monthly rent of Rs. 25,000/-", "clause_id": "c004"}]}})
    a = _qa(clean_doc, llm).ask("What is the monthly rent?")
    assert not a.silent and a.citations and "25,000" in a.answer and a.citations[0].quote in clean_doc.text


def test_qa_verdict_escalates(clean_doc, fake_llm_cls):
    llm = fake_llm_cls({"AnswerOut": lambda u: {"found": True, "answer": "It is enforceable.", "quotes": []},
                        "EscalationOut": lambda u: {"lawyer_type": "property / tenancy lawyer in Karnataka",
                                                    "what_to_bring": ["The agreement"], "questions_to_ask": ["How does clause 7 apply?"],
                                                    "general_info": "Courts look at many factors. This clause is unenforceable."}})
    a = _qa(clean_doc, llm).ask("Is this enforceable?")
    assert a.qtype == "legal_verdict" and a.escalation and "lawyer" in a.escalation.lower()
    assert "can't tell you whether" in a.answer
    assert "unenforceable" not in (a.general_info or "")


def test_qa_out_of_scope(clean_doc, fake_llm_cls):
    a = _qa(clean_doc, fake_llm_cls()).ask("What is the capital of France?")
    assert a.qtype == "out_of_scope" and "Paris" not in a.answer


def test_placeholder_ambiguity_is_dropped(clean_doc, fake_llm_cls):
    def fn(user):
        if "**penalties**" not in user:
            return {"findings": []}
        return {"findings": [{"title": "Late fee", "explanation": "If rent is late you pay Rs. 500 for every week of delay.",
                              "quote": REAL, "clause_id": _clause_of(user, "late fee"), "kind": "explicit",
                              "severity": "medium", "needs_lawyer": False, "ambiguity": "None"}]}
    report, _ = Analyzer(fake_llm_cls({"FindingsOut": fn})).analyze(clean_doc, "auto")
    late = next(f for f in report.findings if f.title == "Late fee")
    assert late.ambiguity_note is None


def test_fast_mode_skips_second_samples_thorough_runs_them(clean_doc, fake_llm_cls):
    def fn(user):
        if "**penalties**" not in user:
            return {"findings": []}
        return {"findings": [{"title": "Late fee", "explanation": "If rent is late you pay Rs. 500 for every week of delay.",
                              "quote": REAL, "clause_id": _clause_of(user, "late fee"), "kind": "explicit",
                              "severity": "high", "needs_lawyer": False, "ambiguity": ""}]}
    counts = {}
    for name, sc in (("fast", 0), ("thorough", 2)):
        llm = fake_llm_cls({"FindingsOut": fn})
        report, _ = Analyzer(llm, self_consistency=sc, pairwise=0).analyze(clean_doc, "auto")
        counts[name] = sum(1 for c, _ in llm.calls if c == "FindingsOut")
        late = next(f for f in report.findings if f.title == "Late fee")
        assert ("consistency" in late.signals) == (sc > 0)
    assert counts["thorough"] == counts["fast"] + 1  # one resample of the penalties category

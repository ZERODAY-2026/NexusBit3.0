import pytest

from lexlocal.analysis import guardrails
from lexlocal.ingest.chunker import chunk_document
from lexlocal.ingest.parser import parse_file
from tests.conftest import SAMPLES


@pytest.mark.parametrize("q", [
    "Is this enforceable?", "Is this agreement legal?", "Should I sign this?", "Is the deposit clause fair?",
    "Can I sue my landlord?", "Is the non-compete valid in India?", "Is this a standard clause?",
    "Is it okay to accept this?", "What would you do?", "Is this binding on me?",
])
def test_verdict_questions(q):
    assert guardrails.classify_rules(q) == "legal_verdict"


@pytest.mark.parametrize("q", ["What is the capital of France?", "Write me a poem about rain", "Who won the cricket match?"])
def test_out_of_scope(q):
    assert guardrails.classify_rules(q) == "out_of_scope"


@pytest.mark.parametrize("q", ["Can I keep a pet?", "What is the notice period?", "How much is the deposit?",
                               "When is rent due?", "Who pays for electricity?"])
def test_fact_questions_not_misrouted(q):
    assert guardrails.classify_rules(q) is None
    assert guardrails.classify(q, None)[0] == "document_fact"


def test_scrub_verdicts():
    text = "You pay rent monthly. This clause is unenforceable in India. The deposit is refundable."
    out, n = guardrails.scrub_verdicts(text)
    assert n == 1 and "unenforceable" not in out and "deposit is refundable" in out
    assert guardrails.has_verdict_language("This contract is fair and safe to sign.")
    assert not guardrails.has_verdict_language("The tenant must give one month's notice.")
    assert not guardrails.has_verdict_language("The agreement is valid for 11 months.")


def test_injection_flagged_and_sanitized():
    doc = parse_file(SAMPLES / "rental_injection.txt")
    flags = guardrails.scan_injection(doc)
    assert flags and any("Ignore all previous instructions" in f.quote for f in flags)
    chunks = chunk_document(doc)
    clean = guardrails.sanitize_chunks(chunks, flags)
    joined = " ".join(c.text for c in clean)
    assert "Ignore all previous instructions" not in joined
    assert "Ignore all previous instructions" in doc.text  # original untouched


def test_no_injection_in_clean(clean_doc):
    assert guardrails.scan_injection(clean_doc) == []

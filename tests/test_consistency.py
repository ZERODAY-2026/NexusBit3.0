import re

import pytest

from lexlocal.analysis import consistency
from lexlocal.analysis.verifier import Verifier
from lexlocal.extract import categories as cats
from lexlocal.extract.rules import extract_facts
from lexlocal.extract.structured import build_key_terms
from lexlocal.ingest.chunker import chunk_document
from lexlocal.ingest.parser import parse_file
from tests.conftest import SAMPLES

VERDICT = re.compile(r"\b(illegal|unlawful|unenforceable|invalid|void|unfair|not allowed by law)\b", re.I)


def prep(name):
    d = parse_file(SAMPLES / name)
    ch = chunk_document(d)
    cats.tag_chunks(ch)
    kt = build_key_terms(extract_facts(d), ch, d, cats.detect_doc_type(d.text))
    return d, ch, kt


@pytest.mark.parametrize("words,n", [("Twenty Five Thousand", 25000), ("One Lakh Fifty Thousand", 150000),
                                     ("Three Lakhs", 300000), ("Twelve Lakhs", 1200000), ("eleven", 11),
                                     ("Two Hundred and Fifty", 250), ("banana", None)])
def test_words_to_number(words, n):
    assert consistency.words_to_number(words) == n


@pytest.mark.parametrize("text,days", [("one month's notice", 30), ("3 (three) months", 90), ("7 days' notice", 7),
                                       ("2 weeks", 14), ("1 year", 365)])
def test_to_days(text, days):
    assert consistency.to_days(text) == days


def test_planted_conflicts_are_all_found():
    d, ch, kt = prep("rental_conflicts.txt")
    found = consistency.rule_conflicts(d, ch, kt)
    titles = " | ".join(c.title for c in found)
    for expected in ["figures and in words", "Two different values for rent", "Term length does not match",
                     "Lock-in period is as long", "Different notice periods for the tenant"]:
        assert expected in titles, (expected, titles)
    for c in found:
        assert c.quote_a in d.text and (not c.quote_b or c.quote_b in d.text)
        assert not VERDICT.search(c.explanation)


@pytest.mark.parametrize("name", ["rental_clean.txt", "employment_offer.txt", "rental_injection.txt"])
def test_no_false_conflicts_on_consistent_documents(name):
    d, ch, kt = prep(name)
    assert consistency.rule_conflicts(d, ch, kt) == []


def test_one_sided_and_asymmetric_terms_flagged():
    d, ch, _ = prep("rental_tricky.txt")
    items = consistency.unusual_clauses(d, ch)
    bases = [u.basis for u in items]
    assert bases[0] == "asymmetric notice"  # most specific first
    asym = items[0]
    assert "7 days" in asym.quote and "3 months" in asym.quote_b
    quotes = " ".join(u.quote for u in items)
    assert "forfeited" in quotes and "sole discretion" in quotes
    for u in items:
        assert u.quote in d.text and not VERDICT.search(u.explanation)


def test_clean_document_has_no_unusual_flags():
    d, ch, _ = prep("rental_clean.txt")
    assert consistency.unusual_clauses(d, ch) == []


def test_injected_text_not_reported_as_atypical():
    d, ch, _ = prep("rental_injection.txt")
    skip = {c.id for c in ch if "ignore all previous instructions" in c.text.lower()}
    items = consistency.unusual_clauses(d, ch, skip_chunks=skip)
    assert not any("ignore all previous" in u.quote.lower() for u in items)


def _pair_llm(fake_llm_cls, reply):
    return fake_llm_cls({"PairOut": lambda user: reply})


def test_model_conflict_needs_both_quotes_verified(fake_llm_cls):
    d, ch, _ = prep("rental_conflicts.txt")
    v = Verifier(d, ch)
    good = {"conflict": True, "topic": "tenant notice", "quote_a": "the Tenant may terminate this agreement by giving one month's written notice",
            "quote_b": "The Tenant may terminate this agreement at any time by giving two months' written notice",
            "explanation": "One clause says one month and the other says two months. This clause is unenforceable."}
    # Force the pair under test: the two tenant-notice clauses.
    pair = [c for c in ch if "Tenant may terminate" in c.text]
    out, rej = consistency.model_conflicts(_pair_llm(fake_llm_cls, good), pair, v, limit=1)
    assert len(out) == 1 and out[0].source == "llm"
    assert out[0].quote_a in d.text and out[0].quote_b in d.text
    assert "unenforceable" not in out[0].explanation  # verdict sentence scrubbed

    fabricated = dict(good, quote_b="The Tenant may leave at any time without notice")
    out, rej = consistency.model_conflicts(_pair_llm(fake_llm_cls, fabricated), pair, v, limit=1)
    assert out == [] and rej


def test_candidate_pairs_share_a_category():
    _, ch, _ = prep("rental_conflicts.txt")
    for a, b in consistency.candidate_pairs(ch, 5):
        assert set(a.categories) & set(b.categories) & set(consistency.PAIR_CATEGORIES)

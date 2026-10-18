import pytest

from lexlocal.extract import categories as cats
from lexlocal.extract.rules import extract_facts
from lexlocal.extract.structured import build_key_terms
from lexlocal.ingest.chunker import chunk_document
from lexlocal.ingest.parser import parse_file

from .conftest import ROOT


def table(name):
    d = parse_file(ROOT / "samples" / name)
    ch = chunk_document(d)
    rows = build_key_terms(extract_facts(d), ch, d, cats.detect_doc_type(d.text))
    return d, ch, rows


def values(rows, field):
    return [r.value for r in rows if r.field == field]


def test_rental_table():
    _, _, rows = table("rental_clean.txt")
    assert values(rows, "Parties")[:2] == ["Ramesh Kumar", "Priya Sharma"]
    assert values(rows, "Term") == ["11 (eleven) months"]
    assert values(rows, "Lock-in") == ["3 (three) months"]
    assert "Rs. 25,000/-" in values(rows, "Rent")
    assert values(rows, "Deposit") == ["Rs. 1,00,000/-"]
    assert values(rows, "Penalties and charges") == ["Rs. 500/-"]
    dates = {r.label: r.value for r in rows if r.field == "Key dates"}
    assert dates["Start date"] == "1st March, 2026" and dates["End date"] == "31st January, 2027"
    assert any("India" in v for v in values(rows, "Governing law and courts"))


def test_employment_table():
    _, _, rows = table("employment_offer.txt")
    assert values(rows, "Salary")[0] == "Rs. 12,00,000/-"
    assert values(rows, "Probation") == ["6 months"]  # "15 days' notice during probation" is a notice period
    assert values(rows, "Penalties and charges") == ["Rs. 2,00,000/-"]  # training-cost repayment, not salary
    assert values(rows, "Restriction period") == ["2 years", "1 year"]
    assert values(rows, "Governing law and courts")[0] == "governed by the laws of India"


def test_advance_rent_is_not_a_deposit():
    _, _, rows = table("rental_tricky.txt")
    assert values(rows, "Rent") == ["Rs. 32,000/-"]
    assert "Rs. 32,000/-" not in values(rows, "Deposit")
    assert "Rs. 1,000/-" in values(rows, "Penalties and charges")


@pytest.mark.parametrize("name", ["rental_clean.txt", "employment_offer.txt", "rental_tricky.txt", "rental_injection.txt"])
def test_every_row_is_verbatim_and_linked(name):
    d, ch, rows = table(name)
    ids = {c.id for c in ch}
    assert rows
    for r in rows:
        assert r.quote in d.text and r.value in r.quote
        assert r.chunk_id in ids

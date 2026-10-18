from lexlocal.extract import categories as cats
from lexlocal.extract.rules import extract_facts
from lexlocal.ingest.chunker import chunk_document
from lexlocal.ingest.parser import parse_bytes


def test_chunks_follow_numbering(clean_doc, clean_chunks):
    assert len(clean_chunks) >= 10
    for c in clean_chunks:
        assert clean_doc.text[c.start:c.end] == c.text  # exact offsets
        assert c.page >= 1
    # section headings merge into their first sub-clause; later sub-clauses are their own chunks
    assert any(c.text.startswith("2. RENT") for c in clean_chunks)
    assert any(c.text.startswith("7.2") for c in clean_chunks)
    assert len({c.id for c in clean_chunks}) == len(clean_chunks)


def test_fallback_windows_for_unstructured():
    text = ("The tenant agrees to pay rent and the landlord agrees to provide the flat. " * 80)
    doc = parse_bytes("u.txt", text.encode())
    chunks = chunk_document(doc)
    assert len(chunks) >= 3
    assert all(doc.text[c.start:c.end] == c.text for c in chunks)


def test_rules_extract_amounts_dates_notice(clean_doc):
    facts = extract_facts(clean_doc)
    by = {}
    for f in facts:
        by.setdefault(f.type, []).append(f.value)
        assert f.value.lower().split()[0] in clean_doc.text[f.start:f.end].lower()
        assert f.quote in clean_doc.text
    assert any("25,000" in v for v in by["amount"])
    assert any("1,00,000" in v for v in by["amount"])
    assert any("March" in v for v in by["date"])
    assert any("month" in v.lower() for v in by["notice_period"])
    assert any("India" in v for v in by["governing_law"])
    assert any("Ramesh Kumar" in v for v in by.get("party", []))


def test_rules_rupee_symbol_and_inr():
    doc = parse_bytes("r.txt", "The salary is ₹ 50,000 per month. A fee of INR 2,000 applies. Interest at 18% per annum.".encode())
    vals = [f.value for f in extract_facts(doc)]
    assert any("50,000" in v for v in vals) and any("2,000" in v for v in vals) and any("18%" in v for v in vals)


def test_category_tagging_and_doctype(clean_doc, clean_chunks):
    cats.tag_chunks(clean_chunks)
    pay = cats.chunks_for("payments", clean_chunks, 3)
    assert pay and any("rent" in c.text.lower() for c in pay)
    assert cats.chunks_for("notice", clean_chunks, 3)
    assert cats.detect_doc_type(clean_doc.text) == "rental"

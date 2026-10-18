from lexlocal.analysis.verifier import Verifier, check_numbers


def test_real_quote_passes_exact(clean_doc, clean_chunks):
    v = Verifier(clean_doc, clean_chunks)
    r = v.verify("The Tenant shall pay a monthly rent of Rs. 25,000/- (Rupees Twenty Five Thousand only)")
    assert r.ok and r.score == 100
    assert r.quote in clean_doc.text  # snapped to verbatim span
    assert r.page >= 1 and r.chunk_id


def test_case_whitespace_punctuation_variants_snap(clean_doc, clean_chunks):
    v = Verifier(clean_doc, clean_chunks)
    r = v.verify("the  tenant shall pay a monthly rent of rs 25,000 - (rupees twenty five thousand only")
    assert r.ok
    assert r.quote in clean_doc.text and "Rs. 25,000" in r.quote


def test_minor_typo_passes_fuzzy(clean_doc, clean_chunks):
    v = Verifier(clean_doc, clean_chunks)
    r = v.verify("either party may terminate this agreement by giving one months prior writen notice to the other party")
    assert r.ok and 90 <= r.score <= 100
    assert r.quote in clean_doc.text


def test_paraphrase_fails(clean_doc, clean_chunks):
    v = Verifier(clean_doc, clean_chunks)
    r = v.verify("Either side can end the lease with thirty days of written warning to the other side")
    assert not r.ok


def test_fabrication_fails(clean_doc, clean_chunks):
    v = Verifier(clean_doc, clean_chunks)
    for fake in [
        "The Tenant may keep pets in the Premises with prior consent of the Landlord",
        "The Landlord shall refund the deposit with 12% annual interest",
        "Tenant waives all rights to any notice before eviction",
    ]:
        assert not v.verify(fake).ok, fake


def test_meaning_changing_edits_fail(clean_doc, clean_chunks):
    v = Verifier(clean_doc, clean_chunks)
    real = "The Tenant shall not sublet, assign or part with possession of the Premises or any part thereof without the prior written consent of the Landlord"
    assert v.verify(real).ok
    altered = {
        "negation removed": real.replace("shall not sublet", "shall sublet"),
        "negation added": "The Tenant shall never use the Premises for residential purposes only and shall not carry on any commercial activity",
        "number changed": "The Tenant shall pay a monthly rent of Rs. 35,000/- (Rupees Twenty Five Thousand only) to the Landlord on or before the 5th day",
        "condition appended": "The Tenant shall use the Premises for residential purposes only unless otherwise agreed by the Tenant in writing at any time",
    }
    for label, q in altered.items():
        r = v.verify(q)
        assert not r.ok, f"{label} accepted: {r.quote}"


def test_too_short_fails(clean_doc, clean_chunks):
    assert not Verifier(clean_doc, clean_chunks).verify("rent").ok


def test_check_numbers_drops_unsupported():
    clean, dropped = check_numbers("Rent is Rs. 25,000 a month. A late fee of Rs. 900 applies.",
                                   "monthly rent of Rs. 25,000/-", [])
    assert "25,000" in clean and "900" not in clean and dropped

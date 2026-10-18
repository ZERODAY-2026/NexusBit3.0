from lexlocal.analysis import glossary
from lexlocal.ingest.parser import parse_bytes, parse_file
from tests.conftest import SAMPLES


def test_terms_found_with_examples_from_glossary():
    d = parse_file(SAMPLES / "rental_tricky.txt")
    g = {e.term: e for e in glossary.build(d)}
    for t in ["licensor", "licensee", "forfeit", "indemnify", "arbitrator", "sole discretion"]:
        assert t in g and g[t].source == "glossary", t
        assert g[t].example in d.text


def test_longer_term_wins_at_same_place():
    d = parse_bytes("x.txt", b"Agreement between Landlord and Tenant. Any material breach by the Tenant allows termination. "
                             b"The parties agree. Notice shall be given. The Tenant shall pay rent and a deposit.")
    terms = {e.term for e in glossary.build(d)}
    assert "material breach" in terms and "breach" not in terms


def test_model_only_for_missing_terms_and_labelled(fake_llm_cls):
    d = parse_bytes("x.txt", b"Agreement between Landlord and Tenant. The Landlord shall have a lien on the Tenant's goods. "
                             b"This clause shall survive. Joint and several liability applies. The parties agree. Rent is payable.")
    llm = fake_llm_cls({"DefOut": lambda u: {"definitions": ["A right to keep property until a debt is paid.",
                                                             "Each person is liable for 100 percent of the debt."]}})
    g = {e.term: e for e in glossary.build(d, llm)}
    assert g["lien"].source == "model"
    assert "joint and several" not in g  # definition with a number was rejected

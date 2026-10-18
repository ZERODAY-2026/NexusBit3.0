import re

import pytest

from lexlocal.analysis import jurisdiction
from lexlocal.extract.rules import extract_facts
from lexlocal.ingest.parser import parse_bytes, parse_file
from tests.conftest import SAMPLES

VERDICT = re.compile(r"\b(illegal|unlawful|unenforceable|invalid|void|unfair|is legal|is enforceable)\b", re.I)


@pytest.mark.parametrize("name,state,basis", [
    ("rental_clean.txt", "Karnataka", "courts"),
    ("employment_offer.txt", "Karnataka", "courts"),
    ("rental_injection.txt", "Telangana", "courts"),
    ("rental_tricky.txt", "Maharashtra", "place of signing"),   # no governing-law clause: falls back to Pune
    ("rental_conflicts.txt", "Karnataka", "courts"),
])
def test_state_detection(name, state, basis):
    d = parse_file(SAMPLES / name)
    info = jurisdiction.detect(d, extract_facts(d))
    assert (info.state, info.basis) == (state, basis)
    assert info.quote in d.text


def test_explicit_state_law_wins():
    text = ("This Lease Agreement is made at Mumbai between the Lessor and the Lessee. The Lessee shall pay rent. "
            "This agreement shall be governed by the laws of the State of Goa. The parties agree to the terms.")
    d = parse_bytes("x.txt", text.encode())
    info = jurisdiction.detect(d, extract_facts(d))
    assert info.state == "Goa" and info.basis == "governing law"


def test_notes_are_general_have_no_numbers_or_verdicts():
    d = parse_file(SAMPLES / "rental_tricky.txt")
    info, notes = jurisdiction.notes(d, extract_facts(d))
    topics = {n.topic for n in notes}
    assert {"security deposit", "arbitration", "eviction and vacating", "late payment interest"} <= topics
    for n in notes:
        assert not re.search(r"\d", n.note), n.note       # never a statutory limit
        assert not VERDICT.search(n.note)
        assert "Maharashtra" in n.note
        assert n.quote in d.text


def test_unknown_place_gives_generic_lawyer():
    d = parse_bytes("x.txt", b"Agreement between the Landlord and the Tenant. The Tenant shall pay a security deposit. "
                             b"Either party may terminate with notice. The parties agree to these terms and shall comply.")
    info, notes = jurisdiction.notes(d, extract_facts(d))
    assert info.state == "" and notes and "a local lawyer" in notes[0].note.lower()

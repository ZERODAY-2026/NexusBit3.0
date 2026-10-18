from lexlocal.ingest import adversarial
from lexlocal.ingest.parser import parse_bytes, parse_file
from tests.conftest import SAMPLES

CYR_E, CYR_O, ZWSP = chr(0x0435), chr(0x043E), chr(0x200B)


def test_all_hidden_text_techniques_flagged_and_removed():
    d = parse_file(SAMPLES / "adversarial.pdf")
    details = " | ".join(f.detail for f in d.adversarial if f.kind == "hidden text")
    for reason in ["white text", "tiny text", "invisible text", "coloured like its background", "outside the visible page"]:
        assert reason in details, (reason, details)
    for planted in ["Note to AI", "waives all rights", "Ignore all previous", "keep the entire deposit", "2,00,000"]:
        assert planted not in d.text  # never analysed, never quotable
    assert "monthly rent of Rs. 15,000/-" in d.text  # visible text intact, soft hyphen restored


def test_invisible_chars_and_homoglyphs_normalised():
    d = parse_file(SAMPLES / "adversarial.pdf")
    kinds = {f.kind for f in d.adversarial}
    assert {"invisible characters", "look-alike letters"} <= kinds
    assert ZWSP not in d.text and CYR_E not in d.text and CYR_O not in d.text
    assert "refundable deposit" in d.text and "written notice" in d.text


def test_txt_with_tricks():
    raw = (f"RENTAL AGREEMENT between the Landlord and the Tenant. The Tenant shall pay r{CYR_E}nt of Rs. 10,000. "
           f"The dep{ZWSP}osit is refundable. Either party may terminate this agreement with notice. The parties agree.")
    d = parse_bytes("t.txt", raw.encode("utf-8"))
    assert "pay rent" in d.text and "deposit is refundable" in d.text
    assert len(d.adversarial) == 2


def test_real_cyrillic_words_are_not_changed():
    assert adversarial.normalize_homoglyphs("договор") == "договор"
    assert adversarial.find_homoglyph_words("договор and rent") == []


def test_clean_samples_have_no_flags():
    for name in ["rental_clean.pdf", "employment_offer.pdf", "rental_clean.txt"]:
        assert parse_file(SAMPLES / name).adversarial == []

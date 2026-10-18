import io

import fitz
import pytest

from lexlocal import config
from lexlocal.ingest.parser import IngestError, parse_bytes, parse_file
from tests.conftest import SAMPLES

TEXT = (SAMPLES / "rental_clean.txt").read_text(encoding="utf-8")


def _pdf(text: str, pages: int = 2) -> bytes:
    d = fitz.open()
    per = len(text) // pages + 1
    for i in range(pages):
        p = d.new_page()
        p.insert_textbox(fitz.Rect(40, 40, 560, 800), text[i * per:(i + 1) * per], fontsize=8)
    return d.tobytes()


def test_txt_ok():
    doc = parse_file(SAMPLES / "rental_clean.txt")
    assert doc.kind == "txt" and "Landlord" in doc.text and not any("does not look" in w for w in doc.warnings)


def test_text_pdf_pages_and_offsets():
    doc = parse_bytes("a.pdf", _pdf(TEXT, 2))
    assert doc.kind == "pdf" and len(doc.pages) == 2
    for p in doc.pages:
        assert doc.text[p.start:p.start + len(p.text)] == p.text


def test_docx_ok():
    import docx

    d = docx.Document()
    for para in TEXT.split("\n"):
        d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    doc = parse_bytes("a.docx", buf.getvalue())
    assert doc.kind == "docx" and "security deposit" in doc.text


@pytest.mark.parametrize("name,data,code", [
    ("e.txt", b"", "empty"),
    ("e.txt", b"   \n\n  ", "empty"),
    ("x.pdf", b"%PDF-1.7\n garbage \x00\x01", "corrupt"),
    ("x.pdf", b"not a pdf at all", "corrupt"),
    ("x.docx", b"PK\x03\x04 broken zip", "corrupt"),
    ("x.txt", b"\x00\x01\x02\x00binary", "corrupt"),
    ("x.exe", b"MZ hello", "unsupported"),
])
def test_bad_inputs(name, data, code):
    with pytest.raises(IngestError) as e:
        parse_bytes(name, data)
    assert e.value.code == code
    assert e.value.message  # user-facing message present


def test_encrypted_pdf():
    d = fitz.open(stream=_pdf(TEXT), filetype="pdf")
    data = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="own")
    with pytest.raises(IngestError) as e:
        parse_bytes("enc.pdf", data)
    assert e.value.code == "encrypted"


def test_scanned_pdf_without_ocr(monkeypatch):
    from lexlocal import config

    monkeypatch.setattr(config, "OCR_ENABLED", False)
    src = fitz.open(stream=_pdf(TEXT, 1), filetype="pdf")
    pix = src[0].get_pixmap(dpi=60)
    out = fitz.open()
    pg = out.new_page()
    pg.insert_image(pg.rect, pixmap=pix)
    with pytest.raises(IngestError) as e:
        parse_bytes("scan.pdf", out.tobytes())
    assert e.value.code == "scanned" and "OCR" in e.value.message


def test_oversized(monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_MB", 0.001)
    with pytest.raises(IngestError) as e:
        parse_bytes("big.txt", b"a" * 5000)
    assert e.value.code == "too_large"


def test_non_contract_warning():
    doc = parse_file(SAMPLES / "not_a_contract.txt")
    assert any("does not look like a contract" in w for w in doc.warnings)


def test_zero_width_removed():
    doc = parse_bytes("z.txt", "The Tenant​ shall pay rent.\n".encode())
    assert "​" not in doc.text

import pytest

from lexlocal import config
from lexlocal.analysis.analyzer import Analyzer
from lexlocal.ingest import ocr
from lexlocal.ingest.parser import IngestError, parse_file
from tests.conftest import SAMPLES

SCANNED = SAMPLES / "edge" / "scanned.pdf"
needs_tesseract = pytest.mark.skipif(not ocr.available()[0], reason="Tesseract not installed")


@needs_tesseract
def test_scanned_pdf_is_read_with_ocr():
    d = parse_file(SCANNED)
    assert "RENTAL AGREEMENT" in d.text and "Ramesh Kumar" in d.text
    assert d.ocr_confidence and 0.5 < d.ocr_confidence[1] <= 1.0
    assert any("local OCR" in w for w in d.warnings)


def test_missing_tesseract_gives_install_hint(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_path", lambda: None)
    with pytest.raises(IngestError) as e:
        parse_file(SCANNED)
    assert e.value.code == "scanned" and "Tesseract" in e.value.message and "winget" in e.value.message


def _fake_ocr(conf):
    text = (SAMPLES / "rental_clean.txt").read_text(encoding="utf-8")[:2400]
    return lambda page, vault=None, dpi=300: ocr.OcrPage(text=text, confidence=conf, words=300)


def test_low_confidence_pages_warn_and_downgrade_findings(monkeypatch, fake_llm_cls):
    monkeypatch.setattr(ocr, "available", lambda: (True, "fake"))
    monkeypatch.setattr(ocr, "ocr_page", _fake_ocr(0.45))
    d = parse_file(SCANNED)
    assert set(d.ocr_confidence.values()) == {0.45}
    assert any("low on page(s) 1" in w for w in d.warnings)
    report, _ = Analyzer(fake_llm_cls(up=False)).analyze(d)
    assert report.findings and all(f.signals.get("ocr") == 0.45 for f in report.findings)

    monkeypatch.setattr(ocr, "ocr_page", _fake_ocr(0.97))
    hi, _ = Analyzer(fake_llm_cls(up=False)).analyze(parse_file(SCANNED))
    assert max(f.confidence for f in report.findings) < min(f.confidence for f in hi.findings)


def test_ocr_off_switch(monkeypatch):
    monkeypatch.setattr(config, "OCR_ENABLED", False)
    with pytest.raises(IngestError) as e:
        parse_file(SCANNED)
    assert "LEXLOCAL_OCR=off" in e.value.message

import pymupdf

from lexlocal import knowledge
from lexlocal.analysis.analyzer import Analyzer
from lexlocal.ingest.parser import parse_file
from lexlocal.report import export
from tests.conftest import SAMPLES


def _report(fake_llm_cls):
    report, _ = Analyzer(fake_llm_cls(up=False)).analyze(parse_file(SAMPLES / "rental_conflicts.txt"))
    return report


def test_markdown_has_disclaimer_citations_and_sections(fake_llm_cls):
    r = _report(fake_llm_cls)
    md = export.to_markdown(r)
    assert md.count(knowledge.disclaimer("en")["disclaimer"]) >= 2  # top and bottom
    assert "## Key terms" in md and "## Places that seem to disagree" in md
    for f in r.findings:
        assert f.quote in md and f"page {f.page}" in md


def test_pdf_is_valid_and_contains_text(fake_llm_cls):
    r = _report(fake_llm_cls)
    pdf = export.to_pdf(r)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    assert doc.page_count >= 1
    assert "not legal advice" in text and "Places that seem to disagree" in text

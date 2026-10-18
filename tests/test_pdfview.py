import pymupdf

from lexlocal.report.pdfview import find_quote_rects, render_page

from .conftest import ROOT

PDF = (ROOT / "samples" / "rental_clean.pdf").read_bytes()


def _page(n=1):
    return pymupdf.open(stream=PDF, filetype="pdf")[n - 1]


def test_quote_spanning_line_break_is_located():
    q = "aged about 58 years, residing at No. 14, 3rd Cross, Jayanagar"
    rects = find_quote_rects(_page(), q)
    assert len(rects) == 2  # crosses one line break -> one band per line
    assert all(r.width > 0 and r.height > 0 for r in rects)


def test_quote_ignores_punctuation_and_case_differences():
    assert find_quote_rects(_page(), 'hereinafter referred to as the "landlord"')


def test_absent_or_altered_quote_is_not_highlighted():
    assert find_quote_rects(_page(), "The tenant may keep two pets in the premises") == []
    assert find_quote_rects(_page(), "aged about 59 years, residing at No. 14") == []


def test_render_returns_png_and_count():
    png, found = render_page(PDF, 1, ["This Rental Agreement is made and executed at Bengaluru", "not in this doc at all"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert found == 1


def test_render_clamps_page_number():
    png, found = render_page(PDF, 99, [])
    assert png[:4] == b"\x89PNG" and found == 0

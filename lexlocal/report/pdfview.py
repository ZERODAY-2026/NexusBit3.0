"""Render a PDF page in memory with the cited quote highlighted (PyMuPDF). Nothing touches disk."""
from __future__ import annotations

import re
import unicodedata

import pymupdf

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(unicodedata.normalize("NFKC", text))]


def find_quote_rects(page: "pymupdf.Page", quote: str) -> list["pymupdf.Rect"]:
    """Rectangles of the words on `page` that spell out `quote` (word-sequence match, punctuation ignored).

    Matching on words rather than raw characters survives line breaks, hyphenation and PDF spacing quirks.
    Falls back to PyMuPDF's text search for very short quotes.
    """
    want = _tokens(quote)
    if not want:
        return []
    words = page.get_text("words", sort=True)  # (x0, y0, x1, y1, word, block, line, wno)
    # A PDF "word" may hold several tokens ("Rs.25,000/-"), so expand to (token, word_index) pairs.
    seq: list[tuple[str, int]] = [(t, i) for i, w in enumerate(words) for t in _tokens(w[4])]
    toks = [t for t, _ in seq]
    n = len(want)
    for s in range(len(toks) - n + 1):
        if toks[s] == want[0] and toks[s:s + n] == want:
            idx = sorted({seq[k][1] for k in range(s, s + n)})
            return _merge_lines([pymupdf.Rect(words[i][:4]) for i in idx])
    return list(page.search_for(quote[:120])) if len(want) <= 3 else []


def _merge_lines(rects: list["pymupdf.Rect"]) -> list["pymupdf.Rect"]:
    """Join word boxes on the same line into one box so the highlight reads as a band."""
    out: list[pymupdf.Rect] = []
    for r in rects:
        if out and abs(out[-1].y0 - r.y0) < 2 and abs(out[-1].y1 - r.y1) < 2 and r.x0 >= out[-1].x0:
            out[-1] = out[-1] | r
        else:
            out.append(pymupdf.Rect(r))
    return out


def render_page(pdf_bytes: bytes, page_number: int, quotes: list[str], zoom: float = 1.6) -> tuple[bytes, int]:
    """PNG bytes of a 1-based page with every quote highlighted, plus the number of quotes located."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.needs_pass:
            doc.authenticate("")
        page = doc[max(0, min(page_number - 1, doc.page_count - 1))]
        found = 0
        for q in quotes:
            rects = find_quote_rects(page, q)
            if rects:
                found += 1
                annot = page.add_highlight_annot(rects)
                annot.set_colors(stroke=(0.96, 0.85, 0.55))
                annot.update(opacity=0.55)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True)
        return pix.tobytes("png"), found
    finally:
        doc.close()

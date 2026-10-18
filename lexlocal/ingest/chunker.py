"""Clause segmentation.

Splits on clause numbering ("1.", "1.1", "12.3.4", "(a)", "Clause 5", "ARTICLE IV") and
ALL-CAPS / Title headings. Falls back to overlapping windows when no structure is found.
Every chunk keeps exact offsets into Document.text so quotes can be traced to a page.
"""
from __future__ import annotations

import re

from lexlocal.models import Chunk, Document

# A clause boundary: start of a line followed by a number/heading pattern.
_BOUNDARY = re.compile(
    r"(?m)^(?=[ \t]*(?:"
    r"(?i:clause|article|section|schedule|annexure)\s+[\dIVXLC]+[.:)]?\s"  # Clause 5 / ARTICLE IV
    r"|\d{1,2}(?:\.\d{1,2}){1,3}[.)]?\s+\S"                                # 1.1 / 2.3.1)
    r"|\d{1,2}[.)]\s+\S"                                                   # 1. / 2)
    r"|[A-Z][A-Z &/,'-]{3,60}:?[ \t]*$"                                     # ALL CAPS HEADING
    r"))"
)
_HEADING_LINE = re.compile(r"^[ \t]*([^\n]{0,90})")
MAX_CHUNK = 1800
MIN_CHUNK = 60
WINDOW = 1200
OVERLAP = 200


def _split_long(text: str, start: int) -> list[tuple[int, int]]:
    """Split a long span on sentence/paragraph boundaries into <= MAX_CHUNK pieces."""
    spans, s = [], 0
    while s < len(text):
        e = min(s + MAX_CHUNK, len(text))
        if e < len(text):
            cut = max(text.rfind("\n", s + MIN_CHUNK, e), text.rfind(". ", s + MIN_CHUNK, e))
            if cut > s:
                e = cut + 1
        spans.append((start + s, start + e))
        s = e
    return spans


def _windows(doc: Document) -> list[tuple[int, int]]:
    spans, s, n = [], 0, len(doc.text)
    while s < n:
        e = min(s + WINDOW, n)
        if e < n:
            cut = doc.text.rfind(". ", s + WINDOW // 2, e)
            if cut > s:
                e = cut + 1
        spans.append((s, e))
        if e >= n:
            break
        s = max(e - OVERLAP, s + 1)
    return spans


def chunk_document(doc: Document) -> list[Chunk]:
    text = doc.text
    starts = sorted({m.start() for m in _BOUNDARY.finditer(text)})
    spans: list[tuple[int, int]] = []
    if len(starts) >= 3:
        if starts[0] > 0:
            starts = [0] + starts
        bounds = starts + [len(text)]
        raw = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        # merge tiny pieces (e.g. a heading line alone) into the following piece
        merged: list[list[int]] = []
        for s, e in raw:
            if merged and (merged[-1][1] - merged[-1][0]) < MIN_CHUNK:
                merged[-1][1] = e
            else:
                merged.append([s, e])
        for s, e in merged:
            if e - s > MAX_CHUNK:
                spans.extend(_split_long(text[s:e], s))
            else:
                spans.append((s, e))
    else:
        spans = _windows(doc)

    chunks: list[Chunk] = []
    for s, e in spans:
        # trim whitespace but keep offsets exact
        seg = text[s:e]
        lstrip = len(seg) - len(seg.lstrip())
        rstrip = len(seg) - len(seg.rstrip())
        s2, e2 = s + lstrip, e - rstrip
        if e2 - s2 < 5:
            continue
        body = text[s2:e2]
        heading = _HEADING_LINE.match(body).group(1).strip()
        chunks.append(
            Chunk(
                id=f"c{len(chunks) + 1:03d}",
                heading=heading[:90],
                text=body,
                start=s2,
                end=e2,
                page=doc.page_for_offset(s2),
            )
        )
    return chunks

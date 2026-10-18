"""Quote verification — the anti-fabrication gate.

A quote is accepted only if it matches the document:
  1. normalized exact match (case/whitespace/punctuation-insensitive), or
  2. rapidfuzz partial_ratio >= FUZZY_THRESHOLD against a clause, and
the accepted quote is *snapped* to the real document span, so what the user sees is
always verbatim document text, never model text.

Numbers in explanations must be supported by the quote or by rule-extracted facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz

from lexlocal import config
from lexlocal.extract.rules import numbers_with_words
from lexlocal.models import Chunk, Document


def _norm_map(text: str) -> tuple[str, list[int]]:
    """Lowercase alnum-only normalization with a map normalized_index -> original_index."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        if ch.isalnum():
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
        elif not prev_space:
            out.append(" ")
            idx.append(i)
            prev_space = True
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def normalize(text: str) -> str:
    return _norm_map(text)[0]


@dataclass
class Verification:
    ok: bool
    quote: str = ""          # snapped verbatim document text
    start: int = -1
    end: int = -1
    score: float = 0.0
    chunk_id: str = ""
    page: int = 0
    reason: str = ""


class Verifier:
    def __init__(self, doc: Document, chunks: list[Chunk]):
        self.doc = doc
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}
        self.norm, self.idx = _norm_map(doc.text)

    def _snap(self, ns: int, ne: int) -> tuple[int, int]:
        s = self.idx[ns]
        e = self.idx[ne - 1] + 1
        text = self.doc.text
        # extend to whole words
        while s > 0 and text[s - 1].isalnum():
            s -= 1
        while e < len(text) and text[e].isalnum():
            e += 1
        return s, e

    def _chunk_for(self, start: int, hint: Optional[str]) -> Chunk:
        if hint and hint in self.by_id:
            c = self.by_id[hint]
            if c.start <= start < c.end:
                return c
        for c in self.chunks:
            if c.start <= start < c.end:
                return c
        return self.chunks[0]

    def _result(self, s: int, e: int, score: float, hint: Optional[str]) -> Verification:
        c = self._chunk_for(s, hint)
        return Verification(True, self.doc.text[s:e], s, e, score, c.id, self.doc.page_for_offset(s))

    def verify(self, quote: str, chunk_hint: Optional[str] = None) -> Verification:
        q = normalize(quote or "")
        if len(q) < config.MIN_QUOTE_CHARS or len(q.split()) < 3:
            return Verification(False, reason="quote_too_short")
        # 1. exact normalized match (prefer inside the hinted chunk)
        positions = [m.start() for m in re.finditer(re.escape(q), self.norm)]
        if positions:
            pick = positions[0]
            if chunk_hint in self.by_id:
                c = self.by_id[chunk_hint]
                inside = [p for p in positions if c.start <= self.idx[p] < c.end]
                pick = inside[0] if inside else pick
            s, e = self._snap(pick, pick + len(q))
            return self._result(s, e, 100.0, chunk_hint)
        # 2. fuzzy: hinted chunk first, then all chunks
        order = ([self.by_id[chunk_hint]] if chunk_hint in self.by_id else []) + self.chunks
        best: Optional[tuple[float, int, int]] = None
        for c in order:
            cn, cidx = _norm_map(c.text)
            if not cn:
                continue
            al = fuzz.partial_ratio_alignment(q, cn, score_cutoff=config.FUZZY_THRESHOLD)
            if al is None:
                continue
            # alignment must cover most of the quote (no tiny partial hits)
            covered = (al.dest_end - al.dest_start) / max(len(q), 1)
            if covered < 0.85 or al.dest_end <= al.dest_start:
                continue
            if best is None or al.score > best[0]:
                s = c.start + cidx[al.dest_start]
                e = c.start + cidx[al.dest_end - 1] + 1
                best = (al.score, s, e)
                if al.score >= 99:
                    break
        if best:
            score, s, e = best
            text = self.doc.text
            while s > 0 and text[s - 1].isalnum():
                s -= 1
            while e < len(text) and text[e].isalnum():
                e += 1
            reason = meaning_changed(q, normalize(text[s:e]))
            if reason:
                return Verification(False, reason=reason, score=score)
            return self._result(s, e, score, chunk_hint)
        return Verification(False, reason="not_found_in_document")


NEGATIONS = {"not", "no", "never", "without", "nor", "neither", "none", "cannot", "unless", "except", "shall't", "nothing"}


def meaning_changed(q_norm: str, span_norm: str) -> str:
    """Fuzzy matches tolerate typos, but not edits that change meaning: the whole quote must be
    >= threshold similar to the snapped span, numbers must be identical, and negations must agree."""
    if fuzz.ratio(q_norm, span_norm) < config.FUZZY_THRESHOLD:
        return "fuzzy_whole_quote_mismatch"
    qt, st = q_norm.split(), span_norm.split()
    if [t for t in qt if t.isdigit()] != [t for t in st if t.isdigit()]:
        return "fuzzy_numbers_differ"
    if sorted(t for t in qt if t in NEGATIONS) != sorted(t for t in st if t in NEGATIONS):
        return "fuzzy_negation_differs"
    return ""


_SENT = re.compile(r"(?<=[.!?])\s+")


def check_numbers(explanation: str, quote: str, fact_values: list[str]) -> tuple[str, list[str]]:
    """Drop sentences whose numbers are not in the quote or rule facts. Returns (clean, dropped)."""
    allowed = numbers_with_words(quote)
    for v in fact_values:
        allowed |= numbers_with_words(v)
    kept, dropped = [], []
    for sent in _SENT.split(explanation.strip()):
        nums = numbers_with_words(sent) if re.search(r"\d", sent) else set()
        # only digit-numbers are checked strictly; spelled small numbers are too common
        digit_nums = {n for n in nums if n in {x.replace(",", "").lstrip("0") or "0" for x in re.findall(r"\d[\d,]*(?:\.\d+)?", sent)}}
        if digit_nums - allowed:
            dropped.append(sent)
        else:
            kept.append(sent)
    return " ".join(kept).strip(), dropped

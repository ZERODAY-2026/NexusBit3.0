"""Adversarial-content detection: text a reader cannot see but a parser (or a model) would read.

* PDF hidden text: white or background-coloured, tiny (< 3 pt), invisible render mode, near-zero opacity,
  or placed outside the visible page.
* Zero-width and bidirectional control characters (all formats).
* Homoglyphs: Cyrillic or Greek letters inside otherwise Latin words ("Rеnt" with a Cyrillic "е").

Hidden PDF text is removed from the analysed text and reported. Zero-width characters are stripped and
homoglyphs normalised to Latin before analysis, so the model and the verifier see what a reader sees.
"""
from __future__ import annotations

import re
import unicodedata

from lexlocal.models import AdversarialFlag

MIN_VISIBLE_PT = 3.0
_INVISIBLE_CHARS = {0x200B: "zero-width space", 0x200C: "zero-width non-joiner", 0x200D: "zero-width joiner",
                    0x2060: "word joiner", 0xFEFF: "zero-width no-break space",
                    0x202A: "bidi control", 0x202B: "bidi control", 0x202C: "bidi control", 0x202D: "bidi control",
                    0x202E: "bidi override", 0x2066: "bidi control", 0x2067: "bidi control", 0x2068: "bidi control",
                    0x2069: "bidi control"}
INVISIBLE_RE = re.compile("[" + "".join(chr(c) for c in _INVISIBLE_CHARS) + "]")

# Cyrillic/Greek letters that look like Latin ones.
CONFUSABLES = {
    0x0430: "a", 0x0435: "e", 0x043E: "o", 0x0440: "p", 0x0441: "c", 0x0443: "y", 0x0445: "x", 0x0456: "i",
    0x0458: "j", 0x04BB: "h", 0x0501: "d", 0x0410: "A", 0x0412: "B", 0x0415: "E", 0x041A: "K", 0x041C: "M",
    0x041D: "H", 0x041E: "O", 0x0420: "P", 0x0421: "C", 0x0422: "T", 0x0425: "X", 0x0406: "I", 0x0408: "J",
    0x03BF: "o", 0x03B1: "a", 0x03BD: "v", 0x03C1: "p", 0x0391: "A", 0x0392: "B", 0x0395: "E", 0x0397: "H",
    0x0399: "I", 0x039A: "K", 0x039C: "M", 0x039D: "N", 0x039F: "O", 0x03A1: "P", 0x03A4: "T", 0x03A7: "X",
    0x03A5: "Y", 0x0396: "Z",
}
_WORD = re.compile(r"\w+", re.UNICODE)


def _script(ch: str) -> str:
    if ch.isascii():
        return "latin" if ch.isalpha() else ""
    name = unicodedata.name(ch, "")
    return "cyrillic" if name.startswith("CYRILLIC") else "greek" if name.startswith("GREEK") else \
        "latin" if name.startswith("LATIN") else ""


def find_homoglyph_words(text: str) -> list[str]:
    """Words that mix Latin letters with look-alike Cyrillic/Greek letters."""
    out = []
    for m in _WORD.finditer(text):
        w = m.group(0)
        scripts = {_script(c) for c in w} - {""}
        if "latin" in scripts and scripts & {"cyrillic", "greek"} and any(ord(c) in CONFUSABLES for c in w):
            out.append(w)
    return out


def normalize_homoglyphs(text: str) -> str:
    """Replace look-alike letters with Latin ones, but only inside mixed-script words (real Cyrillic is untouched)."""
    def fix(m):
        w = m.group(0)
        scripts = {_script(c) for c in w} - {""}
        if "latin" in scripts and scripts & {"cyrillic", "greek"}:
            return "".join(CONFUSABLES.get(ord(c), c) for c in w)
        return w
    return _WORD.sub(fix, text)


def scan_text(raw: str, page: int = 1) -> list[AdversarialFlag]:
    """Zero-width/bidi characters and homoglyph words in raw extracted text (any format)."""
    flags = []
    counts: dict[str, int] = {}
    for ch in INVISIBLE_RE.findall(raw):
        counts[_INVISIBLE_CHARS[ord(ch)]] = counts.get(_INVISIBLE_CHARS[ord(ch)], 0) + 1
    for kind, n in counts.items():
        flags.append(AdversarialFlag(kind="invisible characters", page=page, text="",
                                     detail=f"{n} {kind} character(s) were found and removed before analysis."))
    words = find_homoglyph_words(raw)
    if words:
        shown = ", ".join(sorted({normalize_homoglyphs(w) for w in words})[:6])
        flags.append(AdversarialFlag(kind="look-alike letters", page=page, text=shown,
                                     detail=f"{len(words)} word(s) mix Latin letters with look-alike Cyrillic or Greek "
                                            f"letters (shown here normalised: {shown}). They were normalised before analysis."))
    return flags


def _near(a, b, tol=0.08) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def scan_pdf_page(page) -> tuple[list[AdversarialFlag], list[str]]:
    """Hidden-text flags for one PyMuPDF page, plus the hidden strings to remove from its extracted text."""
    flags, hidden = [], []
    rect = page.rect
    fills = [(d["rect"], d["fill"]) for d in page.get_drawings() if d.get("fill") and d.get("rect")]
    for s in page.get_texttrace():
        text = "".join(chr(c[0]) for c in s["chars"]).replace(chr(0xA0), " ").strip()  # trace uses NBSP for spaces
        if len(text) < 2:
            continue
        bbox = s["bbox"]
        color = tuple(s["color"])[:3] if s.get("color") is not None and len(s["color"]) >= 3 else (0, 0, 0)
        reason = None
        if s.get("type") == 3:
            reason = "invisible text (render mode 3)"
        elif (s.get("opacity") or 1) < 0.1:
            reason = "fully transparent text"
        elif s["size"] < MIN_VISIBLE_PT:
            reason = f"tiny text ({s['size']:.1f} pt)"
        elif not rect.intersects(bbox):
            reason = "text placed outside the visible page"
        else:
            under = [f for r, f in fills if r.contains(bbox[:2]) and len(f) >= 3]
            bg = tuple(under[-1][:3]) if under else (1.0, 1.0, 1.0)
            if _near(color, bg):
                reason = "text coloured like its background" if under else "white text on a white page"
        if reason:
            flags.append(AdversarialFlag(kind="hidden text", page=page.number + 1, text=text[:300], detail=reason))
            hidden.append(text)
    return flags, hidden


def remove_hidden(page_text: str, hidden: list[str]) -> str:
    for h in sorted(hidden, key=len, reverse=True):
        page_text = page_text.replace(h, "")
    return page_text

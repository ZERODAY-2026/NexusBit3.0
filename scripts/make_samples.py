"""Generate PDF samples and edge-case fixtures from the synthetic .txt samples.

    python scripts/make_samples.py

Writes samples/rental_clean.pdf, samples/employment_offer.pdf and samples/edge/*.
Never overwrites an existing file (teammate-provided samples are preserved).
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
EDGE = SAMPLES / "edge"


def text_pdf(text: str, lines_per_page: int = 45) -> bytes:
    doc = fitz.open()
    lines = []
    for para in text.split("\n"):
        while len(para) > 95:
            cut = para.rfind(" ", 0, 95)
            cut = cut if cut > 0 else 95
            lines.append(para[:cut])
            para = para[cut + 1:]
        lines.append(para)
    for i in range(0, len(lines), lines_per_page):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 60), "\n".join(lines[i:i + lines_per_page]), fontsize=10, fontname="helv")
    return doc.tobytes()


def scanned_pdf(text: str) -> bytes:
    """Rasterise a text PDF page into an image-only PDF (simulates a scan)."""
    src = fitz.open(stream=text_pdf(text), filetype="pdf")
    out = fitz.open()
    for p in src:
        pix = p.get_pixmap(dpi=100, colorspace=fitz.csGRAY)
        page = out.new_page(width=p.rect.width, height=p.rect.height)
        page.insert_image(page.rect, stream=pix.tobytes("jpeg", jpg_quality=60))
    return out.tobytes()


def encrypted_pdf(text: str) -> bytes:
    doc = fitz.open(stream=text_pdf(text), filetype="pdf")
    return doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")


def write(path: Path, data: bytes) -> None:
    if path.exists():
        print(f"skip (exists): {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"wrote {path.relative_to(ROOT)} ({len(data):,} bytes)")


def main() -> int:
    clean = (SAMPLES / "rental_clean.txt").read_text(encoding="utf-8")
    emp = (SAMPLES / "employment_offer.txt").read_text(encoding="utf-8")
    write(SAMPLES / "rental_clean.pdf", text_pdf(clean))
    write(SAMPLES / "employment_offer.pdf", text_pdf(emp))
    write(EDGE / "scanned.pdf", scanned_pdf(clean[:2500]))
    write(EDGE / "encrypted.pdf", encrypted_pdf(clean))
    write(EDGE / "corrupt.pdf", b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n%% truncated garbage \x00\x01\x02")
    write(EDGE / "empty.txt", b"")
    return 0


if __name__ == "__main__":
    sys.exit(main())

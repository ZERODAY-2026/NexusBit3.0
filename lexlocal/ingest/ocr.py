"""Local OCR for scanned PDFs: Tesseract (via pytesseract), English + Hindi, per-page confidence.

Everything runs on this machine. Tesseract reads page images from a file, so images go to the session
vault's private scratch directory and are wiped with it. OCR results are cached encrypted in the vault.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from lexlocal import config

log = logging.getLogger("lexlocal.ocr")
_tmp_lock = threading.Lock()
DEFAULT_WIN_PATH = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
INSTALL_HINT = ("Local OCR needs the free Tesseract program. Install it once (Windows: "
                "winget install UB-Mannheim.TesseractOCR; Linux: apt install tesseract-ocr tesseract-ocr-hin; "
                "macOS: brew install tesseract tesseract-lang), then reload LexLocal.")


@dataclass
class OcrPage:
    text: str
    confidence: float  # 0..1, mean word confidence
    words: int


def tesseract_path() -> str | None:
    env = os.environ.get("LEXLOCAL_TESSERACT")
    if env and Path(env).exists():
        return env
    found = shutil.which("tesseract")
    if found:
        return found
    return str(DEFAULT_WIN_PATH) if DEFAULT_WIN_PATH.exists() else None


def tessdata_dir() -> str | None:
    local = config.TESSDATA_DIR
    return str(local) if (local / "eng.traineddata").exists() else None


def languages() -> str:
    d = tessdata_dir()
    if d:
        return "+".join(lang for lang in ("eng", "hin") if (Path(d) / f"{lang}.traineddata").exists())
    return "eng"


def available() -> tuple[bool, str]:
    exe = tesseract_path()
    if not exe:
        return False, INSTALL_HINT
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = exe
        version = str(pytesseract.get_tesseract_version())
        return True, f"Tesseract {version.split()[0]} ({languages()})"
    except Exception as e:  # binary present but broken
        return False, f"Tesseract could not be started ({type(e).__name__}). {INSTALL_HINT}"


def ocr_page(page, vault=None, dpi: int = 300) -> OcrPage:
    """OCR one PyMuPDF page. Uses the vault for the temporary image and an encrypted result cache."""
    import pytesseract
    from PIL import Image
    import io

    pix = page.get_pixmap(dpi=dpi, colorspace="gray")
    png = pix.tobytes("png")
    key = "ocr-" + hashlib.sha256(png).hexdigest()[:32]
    if vault is not None:
        cached = vault.get(key)
        if cached is not None:
            conf, words, text = cached.decode("utf-8").split("\n", 2)
            return OcrPage(text=text, confidence=float(conf), words=int(words))
    pytesseract.pytesseract.tesseract_cmd = tesseract_path()
    if tessdata_dir():  # quoting --tessdata-dir is unreliable on Windows; the env var is inherited by tesseract
        os.environ["TESSDATA_PREFIX"] = tessdata_dir()
    cfg = "--psm 3"
    img = Image.open(io.BytesIO(png))
    scratch = vault.scratch_dir() if vault is not None else None
    with _tmp_lock:  # pytesseract writes its temp files to tempfile.gettempdir()
        old = tempfile.tempdir
        tempfile.tempdir = scratch or old
        try:
            data = pytesseract.image_to_data(img, lang=languages(), config=cfg, output_type=pytesseract.Output.DICT)
        finally:
            tempfile.tempdir = old
    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        c = float(data["conf"][i])
        if c >= 0:
            confs.append(c)
        lines.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(word)
    text, prev_par = [], None
    for (b, p, _), ws in lines.items():
        if prev_par is not None and (b, p) != prev_par:
            text.append("")
        text.append(" ".join(ws))
        prev_par = (b, p)
    result = OcrPage(text="\n".join(text), confidence=round(sum(confs) / len(confs) / 100, 3) if confs else 0.0,
                     words=len(confs))
    if vault is not None:
        vault.put(key, f"{result.confidence}\n{result.words}\n{result.text}".encode("utf-8"))
    log.info("ocr page words=%d conf=%.2f", result.words, result.confidence)  # metadata only
    return result

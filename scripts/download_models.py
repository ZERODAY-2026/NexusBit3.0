"""SETUP-TIME ONLY: download the embedding model into models/ (the only network use of
LexLocal besides `ollama pull`). At runtime the model is loaded from this local path with
HF_HUB_OFFLINE=1."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "models" / "bge-small-en-v1.5"
REPO = "BAAI/bge-small-en-v1.5"


TESSDATA = ROOT / "models" / "tessdata"
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{lang}.traineddata"  # Apache-2.0


def download_tessdata() -> None:
    """OCR language data (English + Hindi) for local Tesseract. Optional: OCR is skipped if this fails."""
    import urllib.request

    TESSDATA.mkdir(parents=True, exist_ok=True)
    for lang in ("eng", "hin", "osd"):
        dest = TESSDATA / f"{lang}.traineddata"
        if dest.exists():
            continue
        try:
            urllib.request.urlretrieve(TESSDATA_URL.format(lang=lang), dest)
            print(f"Downloaded tessdata {lang} -> {dest}")
        except Exception as e:  # network or GitHub hiccup: OCR falls back to the system tessdata
            print(f"Could not download tessdata {lang} ({type(e).__name__}); OCR will use the system language data")


def main() -> int:
    download_tessdata()
    if (TARGET / "config.json").exists() and any(TARGET.glob("*.safetensors")):
        print(f"Embedding model already present at {TARGET}")
        return 0
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from huggingface_hub import snapshot_download

    TARGET.mkdir(parents=True, exist_ok=True)
    snapshot_download(REPO, local_dir=str(TARGET),
                      allow_patterns=["*.json", "*.txt", "model.safetensors", "1_Pooling/*", "*.model"])
    print(f"Downloaded {REPO} -> {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

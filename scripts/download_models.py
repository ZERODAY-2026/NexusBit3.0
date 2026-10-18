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


def main() -> int:
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

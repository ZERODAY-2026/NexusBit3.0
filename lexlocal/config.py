"""Central configuration. Every value can be overridden with an env var (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Runtime must never reach Hugging Face / the internet. Set before any HF import.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# --- LLM ---------------------------------------------------------------
# Default chosen from scripts/bench_model.py results (see docs/MODEL.md).
MODEL = os.environ.get("LEXLOCAL_MODEL", "gemma4:e4b")
FAST_MODEL = os.environ.get("LEXLOCAL_FAST_MODEL", "gemma4:e2b")
OLLAMA_URL = os.environ.get("LEXLOCAL_OLLAMA_URL", "http://127.0.0.1:11434")
LLM_TIMEOUT = float(os.environ.get("LEXLOCAL_LLM_TIMEOUT", "180"))
LLM_TEMPERATURE = 0.1
LLM_NUM_CTX = int(os.environ.get("LEXLOCAL_NUM_CTX", "4096"))
LLM_MAX_TOKENS = int(os.environ.get("LEXLOCAL_MAX_TOKENS", "700"))

# --- Embeddings ----------------------------------------------------------
EMBED_MODEL_DIR = Path(os.environ.get("LEXLOCAL_EMBED_DIR", ROOT / "models" / "bge-small-en-v1.5"))
TESSDATA_DIR = Path(os.environ.get("LEXLOCAL_TESSDATA", ROOT / "models" / "tessdata"))  # eng + hin for local OCR
OCR_LOW_CONFIDENCE = 0.70  # pages below this get a warning and lower finding confidence
OCR_ENABLED = os.environ.get("LEXLOCAL_OCR", "on") != "off"
MAX_OCR_PAGES = 30

# --- Ingestion -----------------------------------------------------------
MAX_FILE_MB = 25
MAX_PAGES = 200
MIN_TEXT_CHARS_PER_PAGE = 40  # below this on most pages -> treat as scanned

# --- Verification --------------------------------------------------------
FUZZY_THRESHOLD = 90  # rapidfuzz partial_ratio for quote acceptance
MIN_QUOTE_CHARS = 12

# --- Analysis ------------------------------------------------------------
MAX_CHUNKS_PER_CATEGORY = 3
CHUNK_CHAR_BUDGET = 3500  # ~1k tokens of document text per LLM call
PAIRWISE_CHECKS = int(os.environ.get("LEXLOCAL_PAIRWISE", "2"))  # Gemma clause-pair contradiction checks (0 = off)

# --- Privacy -------------------------------------------------------------
NETGUARD_MODE = os.environ.get("LEXLOCAL_NETGUARD", "strict")  # strict | off
LOG_LEVEL = os.environ.get("LEXLOCAL_LOG_LEVEL", "INFO")
LOG_DIR = ROOT / "logs"

KNOWLEDGE_DIR = ROOT / "knowledge"
SAMPLES_DIR = ROOT / "samples"
EVAL_DIR = ROOT / "eval"
DOCS_DIR = ROOT / "docs"

# --- Confidence (tuned by scripts/calibrate.py on eval/confidence_labels.yaml) ---------------
CONF_HIGH = float(os.environ.get("LEXLOCAL_CONF_HIGH", "0.85"))
CONF_MEDIUM = float(os.environ.get("LEXLOCAL_CONF_MEDIUM", "0.65"))
SELF_CONSISTENCY_CALLS = int(os.environ.get("LEXLOCAL_SELF_CONSISTENCY", "2"))  # extra samples for high-severity categories

# --- Analysis modes (sidebar) ----------------------------------------------------------------
MODES = {
    "Fast": {"model": FAST_MODEL, "self_consistency": 0, "pairwise": 1,
             "help": "gemma4:e2b, one pass. About 3x faster; good for a first read."},
    "Thorough": {"model": MODEL, "self_consistency": SELF_CONSISTENCY_CALLS, "pairwise": PAIRWISE_CHECKS,
                 "help": "gemma4:e4b with a second sample for high-severity findings and clause-pair checks."},
}

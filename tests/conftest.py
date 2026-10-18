import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lexlocal import config  # noqa: E402,F401  (offline env vars)
from lexlocal.ingest.chunker import chunk_document  # noqa: E402
from lexlocal.ingest.parser import parse_file  # noqa: E402

SAMPLES = ROOT / "samples"


def _ollama_up() -> bool:
    try:
        import requests

        s = requests.Session()
        s.trust_env = False
        return s.get(config.OLLAMA_URL + "/api/tags", timeout=2).ok
    except Exception:
        return False


def pytest_configure(config):  # noqa: F811  (pytest hook arg name is fixed)
    config.addinivalue_line("markers", "needs_ollama: requires a running local Ollama with the configured model")


def pytest_collection_modifyitems(config, items):  # noqa: F811
    if _ollama_up():
        return
    skip = pytest.mark.skip(reason="Ollama not reachable on 127.0.0.1")
    for item in items:
        if "needs_ollama" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def clean_doc():
    return parse_file(SAMPLES / "rental_clean.txt")


@pytest.fixture
def clean_chunks(clean_doc):
    return chunk_document(clean_doc)


class FakeLLM:
    """Deterministic stand-in for OllamaClient. `responses` maps schema class name -> callable(user)->obj."""

    model = "fake-llm"

    def __init__(self, responses=None, up=True):
        self.responses = responses or {}
        self.up = up
        self.calls = []

    def health(self):
        return {"ok": self.up, "models": [self.model], "model_available": self.up}

    def generate_json(self, system, user, model_cls, max_tokens=None, temperature=None, seed=7):
        from lexlocal.llm.client import LLMError

        self.calls.append((model_cls.__name__, user))
        if not self.up:
            raise LLMError("down")
        fn = self.responses.get(model_cls.__name__)
        try:
            return model_cls.model_validate(fn(user) if fn else {})
        except Exception:
            raise LLMError("fake: no valid canned response")


@pytest.fixture
def fake_llm_cls():
    return FakeLLM

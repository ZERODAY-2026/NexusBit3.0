"""Hybrid retrieval: BM25 (rank_bm25) + dense bge-small-en-v1.5 embeddings, in memory.

The embedding model is loaded only from the local models/ directory (HF offline). If it is
missing, retrieval degrades gracefully to BM25 only.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from lexlocal import config
from lexlocal.models import Chunk

log = logging.getLogger("lexlocal.retrieval")

_model = None
_model_lock = threading.Lock()
_model_error: Optional[str] = None
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
_STOP = set("the a an of to and or in on for by with is are be shall will this that any all as at from it its such".split())


def _tok(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP]


def get_embedder():
    """Lazy-load the local embedding model. Returns None if unavailable."""
    global _model, _model_error
    with _model_lock:
        if _model is not None or _model_error is not None:
            return _model
        path = config.EMBED_MODEL_DIR
        if not (path / "config.json").exists():
            _model_error = f"embedding model not found at {path} (run scripts/setup)"
            log.warning(_model_error)
            return None
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(str(path), device="cpu", local_files_only=True)
            log.info("embedding model loaded from local path")
        except Exception as e:
            _model_error = f"embedding model failed to load ({type(e).__name__})"
            log.warning(_model_error)
        return _model


def embedder_status() -> str:
    return "ok" if _model is not None else (_model_error or "not loaded")


class HybridIndex:
    def __init__(self, chunks: list[Chunk], alpha: float = 0.5):
        self.chunks = chunks
        self.alpha = alpha
        self.bm25 = BM25Okapi([_tok(c.heading + " " + c.text) or ["_"] for c in chunks])
        self.emb = None
        model = get_embedder()
        if model is not None and chunks:
            self.emb = model.encode([c.text[:2000] for c in chunks], normalize_embeddings=True,
                                    batch_size=16, show_progress_bar=False)

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        bm = np.asarray(self.bm25.get_scores(_tok(query)), dtype=float)
        bm_n = bm / bm.max() if bm.max() > 0 else bm
        if self.emb is not None:
            qv = get_embedder().encode([BGE_QUERY_PREFIX + query], normalize_embeddings=True, show_progress_bar=False)[0]
            dense = self.emb @ qv
            dense_n = np.clip((dense - 0.3) / 0.5, 0, 1)  # bge cosine ~0.3 (unrelated) .. 0.8 (match)
            scores = self.alpha * bm_n + (1 - self.alpha) * dense_n
            raw_dense = dense
        else:
            scores, raw_dense = bm_n, np.zeros_like(bm_n)
        order = np.argsort(-scores)[:k]
        self.last_dense = {self.chunks[i].id: float(raw_dense[i]) for i in order}
        return [(self.chunks[i], float(scores[i])) for i in order]

"""Logging that can never contain document text.

Two layers:
1. Code only logs metadata (stage names, timings, token counts, lengths).
2. DocTextFilter redacts any log record that contains a substring of the currently loaded
   document (registered via register_document) or is suspiciously long.
"""
from __future__ import annotations

import logging
import re
import threading

_lock = threading.Lock()
_fingerprints: set[str] = set()
MAX_MSG = 400
_WINDOW = 40


def register_document(text: str) -> None:
    """Register fingerprints (40-char windows of normalized text) of the loaded document."""
    norm = re.sub(r"\s+", " ", text).strip().lower()
    fps = {norm[i : i + _WINDOW] for i in range(0, max(len(norm) - _WINDOW, 1), _WINDOW // 2)}
    with _lock:
        _fingerprints.clear()
        _fingerprints.update(fp for fp in fps if len(fp.strip()) >= 20)


def clear_document() -> None:
    with _lock:
        _fingerprints.clear()


def _contains_doc_text(msg: str) -> bool:
    norm = re.sub(r"\s+", " ", msg).lower()
    if len(norm) < _WINDOW // 2:
        return False
    with _lock:
        fps = list(_fingerprints)
    # A doc substring of length >= 40 must contain one full 20-step window start -> check
    # all 20-char prefixes of fingerprints for robustness.
    return any(fp[:20] in norm for fp in fps)


class DocTextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if _contains_doc_text(msg):
            record.msg = "[REDACTED: log message contained document text]"
            record.args = ()
        elif len(msg) > MAX_MSG:
            record.msg = msg[:MAX_MSG] + " …[truncated]"
            record.args = ()
        return True


_configured = False


def setup_logging(level: str = "INFO", log_file=None) -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger("lexlocal")
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(DocTextFilter())
        root.addHandler(h)
    _configured = True

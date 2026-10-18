"""Per-session encrypted scratch space.

LexLocal keeps documents in memory. When something has to touch disk (OCR page images that Tesseract
reads from a file, cached OCR results), it goes through a Vault:

* a private temp directory (created with mkdtemp, owner-only permissions where the OS supports it);
* every cached item encrypted with Fernet (AES-128-CBC + HMAC-SHA256) under a key that exists only in memory;
* wipe(): overwrite each file with zeros, delete it, remove the directory, drop the key.

A vault is wiped on "Delete document", on "Panic wipe", when its session object is garbage-collected
(Streamlit discards a session's state after the browser tab closes), and at process exit.
"""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import tempfile
import threading
import weakref
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("lexlocal.vault")
_LIVE: "weakref.WeakSet[Vault]" = weakref.WeakSet()
_lock = threading.Lock()


def _wipe_dir(path: str) -> int:
    n = 0
    if not os.path.isdir(path):
        return 0
    for root, _, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            try:
                size = os.path.getsize(fp)
                with open(fp, "r+b") as fh:
                    fh.write(b"\0" * size)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.remove(fp)
                n += 1
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)
    return n


class Vault:
    def __init__(self):
        self._key = Fernet.generate_key()
        self._fernet = Fernet(self._key)
        self.dir = tempfile.mkdtemp(prefix="lexlocal-")
        try:
            os.chmod(self.dir, 0o700)
        except OSError:
            pass
        # Runs when this object is garbage-collected, or at interpreter exit, whichever comes first.
        self._finalizer = weakref.finalize(self, _wipe_dir, self.dir)
        with _lock:
            _LIVE.add(self)
        log.info("vault created")

    @property
    def active(self) -> bool:
        return self._fernet is not None and os.path.isdir(self.dir)

    def _path(self, name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)[:80]
        return Path(self.dir) / f"{safe}.bin"

    def put(self, name: str, data: bytes) -> None:
        if not self.active:
            raise RuntimeError("vault is wiped")
        self._path(name).write_bytes(self._fernet.encrypt(data))

    def get(self, name: str) -> bytes | None:
        p = self._path(name)
        if not self.active or not p.exists():
            return None
        try:
            return self._fernet.decrypt(p.read_bytes())
        except InvalidToken:
            return None

    def scratch_dir(self) -> str:
        """A plain subdirectory for tools that need a real file (e.g. Tesseract). Wiped with the vault."""
        d = os.path.join(self.dir, "scratch")
        os.makedirs(d, exist_ok=True)
        return d

    def files(self) -> list[str]:
        return [str(p) for p in Path(self.dir).rglob("*") if p.is_file()] if os.path.isdir(self.dir) else []

    def wipe(self) -> int:
        n = _wipe_dir(self.dir)
        self._finalizer.detach()
        self._fernet = None
        self._key = b""
        log.info("vault wiped files=%d", n)
        return n


def wipe_all() -> int:
    """Wipe every live vault in this process (panic wipe and process exit)."""
    with _lock:
        vaults = list(_LIVE)
    return sum(v.wipe() for v in vaults if v.active)


atexit.register(wipe_all)

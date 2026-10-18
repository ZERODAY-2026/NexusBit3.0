"""UI hygiene: no emojis in the repo, no external assets in the UI code."""
import re
from pathlib import Path

from lexlocal import config
from lexlocal.ui import theme

_RANGES = [(0x2190, 0x21FF), (0x2300, 0x23FF), (0x2460, 0x27BF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F),
           (0x200D, 0x200D), (0x1F000, 0x1FAFF)]
PICTOGRAPHS = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in _RANGES) + "]")
SKIP = {".venv", ".git", "models", "__pycache__", ".pytest_cache", "logs"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".yaml", ".yml", ".txt", ".ps1", ".sh", ".css", ".html"}


def _repo_text_files():
    for p in config.ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and not SKIP & set(p.relative_to(config.ROOT).parts):
            yield p


def test_no_emojis_or_pictographs_in_repo():
    hits = []
    for p in _repo_text_files():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if PICTOGRAPHS.search(line):
                hits.append(f"{p.relative_to(config.ROOT)}:{i}")
    assert not hits, hits


def test_ui_has_no_external_urls():
    ui_files = [config.ROOT / "lexlocal" / "app.py", *(config.ROOT / "lexlocal" / "ui").glob("*.py")]
    for p in ui_files:
        src = p.read_text(encoding="utf-8")
        assert not re.search(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}/", src, re.I), p
        assert "@import" not in src and "url(" not in src, p
    for css in (theme.CSS, theme.SPLASH):
        assert "http" not in css and "url(" not in css


def test_splash_respects_reduced_motion_and_is_hidden_from_screen_readers():
    assert "prefers-reduced-motion: reduce" in theme.SPLASH
    assert 'aria-hidden="true"' in theme.SPLASH
    assert theme.SPLASH.count("class='ll-l'") == len("LexLocal")


def test_favicon_is_local():
    assert (Path(config.ROOT) / "lexlocal" / "ui" / "assets" / "favicon.png").is_file()

"""Visual theme for the Streamlit UI: inline CSS only, no external fonts, scripts or images.

Severity and status are always shown as text; the coloured dot is decoration (aria-hidden).
"""
from __future__ import annotations

import html

from lexlocal.models import Severity

# Warm off-white palette. Text/background pairs below pass WCAG AA (>= 4.5:1).
BG = "#FBF8F1"
BG2 = "#F3EEE2"
CARD = "#FFFDF8"
BORDER = "#E7DFCC"
TEXT = "#1F1D1A"
MUTED = "#5E574C"      # 6.6:1 on BG
PRIMARY = "#7A2E2E"    # 8.4:1 on BG

SERIF = '"Iowan Old Style", "Palatino Linotype", Georgia, "Times New Roman", serif'
SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

SEVERITY_COLOR = {Severity.high: "#9B2C2C", Severity.medium: "#A86412", Severity.low: "#3F6E4A",
                  Severity.info: "#8A8476"}

CSS = f"""
<style>
html, body, .stApp, .stMarkdown, button, input, textarea, select {{ font-family: {SANS}; }}
h1, h2, h3, h4, h5, .ll-serif {{ font-family: {SERIF} !important; font-weight: 600; letter-spacing: -0.005em; color: {TEXT}; }}
.stApp {{ background: {BG}; }}
section[data-testid="stSidebar"] {{ background: {BG2}; border-right: 1px solid {BORDER}; }}
div[data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stExpander"] details {{
  background: {CARD}; border: 1px solid {BORDER} !important; border-radius: 8px; box-shadow: none; }}
mark {{ background: #F4E3B5; color: {TEXT}; padding: 0 2px; border-radius: 2px; }}
blockquote {{ border-left: 3px solid {PRIMARY}; color: {TEXT}; }}
.ll-masthead {{ display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  border-bottom: 1px solid {BORDER}; padding: 2px 0 10px; margin-bottom: 14px; }}
.ll-masthead .ll-title {{ font-family: {SERIF}; font-size: 2.1rem; font-weight: 600; color: {TEXT}; line-height: 1.1; }}
.ll-masthead .ll-tag {{ font-size: 0.85rem; color: {MUTED}; }}
.ll-notice {{ background: {CARD}; border: 1px solid {BORDER}; border-left: 3px solid {PRIMARY}; border-radius: 8px;
  padding: 10px 14px; margin-bottom: 12px; font-size: 0.92rem; color: {TEXT}; }}
.ll-badge {{ display: inline-flex; align-items: center; gap: 6px; font-size: 0.74rem; font-weight: 600;
  letter-spacing: 0.04em; text-transform: uppercase; padding: 2px 8px; border-radius: 999px;
  border: 1px solid {BORDER}; background: {BG2}; color: {TEXT}; white-space: nowrap; }}
.ll-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex: none; }}
.ll-chip {{ display: flex; align-items: center; gap: 8px; font-size: 0.86rem; padding: 6px 10px; margin: 4px 0;
  background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; color: {TEXT}; }}
.ll-meta {{ font-size: 0.8rem; color: {MUTED}; }}
section[data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"] {{
  justify-content: flex-start; text-align: left; min-height: 0; padding: 3px 6px; margin: 0; border-radius: 6px; }}
section[data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"] > div {{ justify-content: flex-start; width: 100%; }}
section[data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"]:hover {{ background: {CARD}; }}
section[data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"] p {{ text-align: left; font-size: 0.82rem; line-height: 1.3; }}
section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-tertiary"]) {{ margin-bottom: -10px; }}
.ll-loading {{ display: inline-flex; align-items: center; gap: 10px; font-size: 0.88rem; color: {TEXT};
  background: {CARD}; border: 1px solid {BORDER}; border-radius: 999px; padding: 6px 14px; margin: 0 0 12px; }}
.ll-loading .ll-pulse {{ width: 9px; height: 9px; border-radius: 50%; background: {PRIMARY};
  animation: llPulse 1.1s ease-in-out infinite; }}
@keyframes llPulse {{ 0%, 100% {{ opacity: 0.25; transform: scale(0.8); }} 50% {{ opacity: 1; transform: scale(1); }} }}
@media (prefers-reduced-motion: reduce) {{ .ll-loading .ll-pulse {{ animation: none; opacity: 0.8; }} }}
.ll-ftitle {{ font-family: {SERIF}; font-size: 1.08rem; font-weight: 600; color: {TEXT}; }}
</style>
"""

_WORD = "LexLocal"
_SUB = "Private legal document understanding. On your device."


def _letters() -> str:
    out = []
    for i, ch in enumerate(_WORD):
        enter, exit_ = i * 0.1, i * 0.1 + 0.2
        out.append(
            "<span class='ll-l'>"
            f"<span class='ll-a' style='animation-delay:{enter:.1f}s'>{ch}</span>"
            f"<span class='ll-b' style='animation-delay:{exit_:.1f}s'>{ch}</span>"
            f"<span class='ll-h'>{ch}</span></span>")
    return "".join(out)


SPLASH = f"""
<style>
.ll-splash {{ position: fixed; inset: 0; z-index: 2147483000; background: {BG}; display: flex; flex-direction: column;
  align-items: center; justify-content: center; animation: llFadeOut 0.5s ease 2.0s forwards; }}
.ll-word {{ font-family: {SERIF}; font-size: clamp(3rem, 11vw, 6.5rem); font-weight: 600; color: {TEXT};
  letter-spacing: -0.01em; line-height: 1.15; }}
.ll-l {{ display: inline-block; position: relative; perspective: 600px; transform-style: preserve-3d; }}
.ll-a, .ll-b {{ position: absolute; left: 0; top: 0; backface-visibility: hidden; -webkit-backface-visibility: hidden;
  animation-duration: 0.5s; animation-timing-function: ease-in; animation-fill-mode: both; }}
.ll-a {{ transform-origin: 50% 25%; animation-name: llRollOut; }}
.ll-b {{ transform-origin: 50% 100%; transform: rotateX(90deg); animation-name: llRollIn; }}
.ll-h {{ visibility: hidden; }}
.ll-sub {{ margin-top: 14px; font-family: {SANS}; font-size: 0.98rem; color: {MUTED}; opacity: 0;
  animation: llFadeIn 0.6s ease 0.9s forwards; }}
@keyframes llRollOut {{ from {{ transform: rotateX(0deg); }} to {{ transform: rotateX(90deg); }} }}
@keyframes llRollIn {{ from {{ transform: rotateX(90deg); }} to {{ transform: rotateX(0deg); }} }}
@keyframes llFadeIn {{ to {{ opacity: 1; }} }}
@keyframes llFadeOut {{ to {{ opacity: 0; visibility: hidden; pointer-events: none; }} }}
@media (prefers-reduced-motion: reduce) {{ .ll-splash {{ display: none !important; }} }}
</style>
<div class="ll-splash" aria-hidden="true">
  <div class="ll-word">{_letters()}</div>
  <div class="ll-sub">{_SUB}</div>
</div>
"""


def dot(color: str) -> str:
    return f"<span class='ll-dot' aria-hidden='true' style='background:{color}'></span>"


def severity_badge(sev: Severity, label: str) -> str:
    return f"<span class='ll-badge'>{dot(SEVERITY_COLOR[sev])}{html.escape(label)}</span>"


def badge(text: str, color: str | None = None) -> str:
    return f"<span class='ll-badge'>{dot(color) if color else ''}{html.escape(text)}</span>"


def chip(text: str, ok: bool | None) -> str:
    """Status line for the sidebar. ok=True green, False red, None amber; the text carries the meaning."""
    color = {True: "#3F6E4A", False: "#9B2C2C", None: "#A86412"}[ok]
    return f"<div class='ll-chip'>{dot(color)}<span>{text}</span></div>"


def loading_tag(text: str) -> str:
    """Small 'please wait' pill; role=status so screen readers announce it."""
    return (f"<div class='ll-loading' role='status' aria-live='polite'>"
            f"<span class='ll-pulse' aria-hidden='true'></span><span>{html.escape(text)}</span></div>")

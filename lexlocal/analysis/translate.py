"""Local machine translation of LexLocal's own explanations (never of document quotes).

Only text that already passed verification, number grounding and the verdict scrubber is translated.
A translation is rejected (the English is shown instead) if it is empty, wildly different in length,
adds a number that is not in the English source, or contains English verdict words.
Fixed disclaimers come from knowledge/disclaimers.json and are never machine translated.
"""
from __future__ import annotations

import logging
import re
import unicodedata

from pydantic import BaseModel

from lexlocal.analysis import guardrails

log = logging.getLogger("lexlocal.translate")

LANGUAGES = {"hi": "Hindi", "kn": "Kannada", "ta": "Tamil", "ml": "Malayalam", "te": "Telugu"}
BATCH = 8


class TranslationsOut(BaseModel):
    translations: list[str]


PROMPT = """Translate each numbered English text below into {language}.
Rules: translate faithfully and simply; keep every number, amount and date exactly as written (use the same digits);
keep names and the words "LexLocal" unchanged; do not add advice, opinions or anything not in the English.
Return JSON {{"translations": [...]}} with exactly {n} strings, in the same order.

{items}"""


def numbers(text: str) -> set[str]:
    """Digit sequences, with native-script digits (Devanagari, Kannada, Tamil, ...) mapped to ASCII."""
    ascii_text = "".join(str(unicodedata.digit(ch)) if ch.isdigit() and not ch.isascii() else ch for ch in text)
    return {n.replace(",", "").lstrip("0") or "0" for n in re.findall(r"\d[\d,]*", ascii_text)}


def acceptable(source: str, translated: str) -> bool:
    if not translated or not translated.strip():
        return False
    ratio = len(translated) / max(len(source), 1)
    if not 0.3 <= ratio <= 4.0:
        return False
    if not numbers(translated) <= numbers(source):
        return False
    return not guardrails.has_verdict_language(translated)


def translate_texts(llm, texts: list[str], lang: str) -> list[str | None]:
    """Translations in order; None where translation failed or was rejected (caller shows English)."""
    from lexlocal.llm import prompts
    from lexlocal.llm.client import LLMError

    if lang not in LANGUAGES:
        raise ValueError(lang)
    out: list[str | None] = [None] * len(texts)
    for start in range(0, len(texts), BATCH):
        batch = texts[start:start + BATCH]
        items = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(batch))
        try:
            r = llm.generate_json(prompts.BASE_SYSTEM, PROMPT.format(language=LANGUAGES[lang], n=len(batch), items=items),
                                  TranslationsOut, max_tokens=min(400 + 220 * len(batch), 2400))
        except LLMError as e:
            log.warning("translation batch failed: %s", type(e).__name__)
            continue
        if len(r.translations) != len(batch):
            log.warning("translation batch returned %d of %d", len(r.translations), len(batch))
            continue
        for i, (src, tr) in enumerate(zip(batch, r.translations)):
            out[start + i] = tr.strip() if acceptable(src, tr) else None
    log.info("translated lang=%s ok=%d/%d", lang, sum(t is not None for t in out), len(texts))
    return out

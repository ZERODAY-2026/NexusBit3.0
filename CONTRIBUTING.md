# Contributing to LexLocal

Thanks for helping. LexLocal handles people's private legal documents, so a few rules are stricter than usual.

## Ground rules (non-negotiable)

1. **Local only.** Document processing must never leave the machine. No remote APIs, telemetry, CDNs, web fonts
   or remote images. Runtime network use is loopback only (Ollama on 127.0.0.1). `tests/test_privacy.py` and
   `tests/test_ui_assets.py` enforce parts of this.
2. **No document text in logs.** Log counts and timings only. `DocTextFilter` is a safety net, not a licence.
3. **Never legal advice.** No code path may tell the user that something is legal, valid, enforceable or fair.
   Model text goes through `guardrails.scrub_verdicts`. Fixed texts belong in `knowledge/`.
4. **Every claim has a verified quote.** Anything shown to the user as coming from the document must pass
   `analysis/verifier.py`. If verification fails, drop the claim. Do not show the model's text instead.
5. **No emojis** in code, UI or docs. Use text labels or the CSS badges in `lexlocal/ui/theme.py`.

## Setup

```bash
git clone https://github.com/ZERODAY-2026/NexusBit3.0.git && cd NexusBit3.0
bash scripts/setup.sh          # Windows: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

## Before you open a pull request

```bash
.venv/bin/python -m pytest -m "not needs_ollama"   # must pass; no model needed
.venv/bin/python -m pytest -m needs_ollama          # if you touched the pipeline (needs Ollama)
```

- Add a test with every behaviour change. Fake LLM fixtures are in `tests/conftest.py`.
- Record non-obvious choices in `docs/DECISIONS.md` (one row: decision, why, alternatives).
- If you change prompts, bump `PROMPT_VERSION` in `lexlocal/llm/prompts.py` and re-run `scripts/eval.py`.
- Keep knowledge files (`knowledge/*.json`) as reviewable data. Notes must not state statutory limits.

## Good first contributions

- More reference clauses in `knowledge/standard_clauses.json` and glossary entries.
- Native-speaker review of the translations in `knowledge/disclaimers.json`.
- Real (anonymised, consented) agreements for the gold set in `eval/gold.yaml`.

By contributing you agree that your work is licensed under the Apache-2.0 licence of this repository.

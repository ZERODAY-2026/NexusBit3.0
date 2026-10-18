# ⚖️ LexLocal: private, on-device legal document triage

**Runs 100% on your device · Not legal advice**

LexLocal reads an Indian rental/lease or employment agreement and explains it in plain English: what you pay,
what you must do, deadlines, penalties, how it ends, and what's missing or vague. **Every claim comes with a verified
verbatim quote and page number.** It never tells you whether something is legal, enforceable or fair. Instead it tells you
what kind of lawyer to ask and what to ask them.

Everything runs locally: Gemma 4 via [Ollama](https://ollama.com) on `127.0.0.1`, local embeddings, and a runtime
network guard. No document ever leaves the machine.

> ZeroDay OSS Hacktoberfest 2026 (IIIT Dharwad), Problem Statement 2.

## Who it's for

Tenants, students, first-job employees and small landlords who are handed an agreement and need to understand it
before they sign, and who can't, or shouldn't, upload it to a cloud AI.

## Scope (Phase 1)

- **Documents:** Indian rental, lease and leave-and-license agreements, and employment agreements or offer letters.
- **Language:** English.
- **Formats:** text-based PDF, DOCX, TXT (≤ 25 MB, ≤ 200 pages). Scanned PDFs are detected and declined ("OCR coming in advanced mode").
- **Out of scope:** legal advice, legality or enforceability verdicts, other contract types (they are analysed with a warning).

## Features

| Requirement | What LexLocal does |
|---|---|
| L1/L2 Local ingestion | PDF (PyMuPDF), DOCX, TXT parsed in memory. Encrypted, empty, corrupt, oversized, scanned and non-contract files get clear messages |
| L3 Plain-language summary | Gemma summary plus key points, each backed by a verified quote |
| L4 Key terms | Obligations, rights, deadlines, payments, penalties, termination, notice periods, restrictions and liability, from rules (₹ amounts, dates, notice periods, governing law) and Gemma |
| L5 Citations | Every finding has a **verbatim quote + page**. Expanding it shows the full source clause with the quote highlighted |
| L6 Labels | Each finding is **EXPLICIT** (the document states it), **INTERPRETATION** or **CONCERN** (worth asking a lawyer). Severity and confidence are shown as text |
| L7 Gaps | Vague terms ("sole discretion", "reasonable", …), missing expected clauses ("The document does not appear to mention …") and jurisdiction-dependent notes |
| L8 Q&A | Questions are classified as **document fact** (answered only from verified passages, otherwise *"The document is silent on this"* plus the closest clauses), **legal verdict** (no verdict; what the doc says, labelled general info, and a specific lawyer escalation) or **out of scope** (declined) |
| Injection defence | Instruction-like text in a document is detected, flagged in the UI and removed from what the model sees. `<document>` delimiters, an untrusted-data system prompt and schema-validated JSON with one retry |
| L9 Privacy | Network guard on by default (loopback only), status chips and a blocked-attempt counter, no document text in logs, memory-only session, **Clear document** |
| L10 Gemma | Summary, category findings, question classification, grounded Q&A, escalation guidance |

**Anti-fabrication:** a model quote is shown only if it matches the document (normalized exact match, or fuzzy ≥ 90).
It is then replaced by the real document span. Numbers in explanations must appear in the quote or in rule-extracted
facts. Sentences that state a legal verdict are removed. Rejected claims are logged for evaluation and never shown.

## Hardware tested

Intel i5-13420H, 16 GB RAM, RTX 2050 4 GB, Windows 11, Python 3.13, Ollama 0.40.6.
`gemma4:e4b` runs at 14.4 tok/s and `gemma4:e2b` at 65 tok/s (see [docs/MODEL.md](docs/MODEL.md)). A full analysis takes about 1.5–3.5 minutes
with E4B. Minimum: 8 GB RAM (E2B) or 16 GB recommended (E4B).

## Setup (needs internet once)

Prerequisites: Python ≥ 3.11 and [Ollama](https://ollama.com/download), running (`ollama serve`).

**Windows (PowerShell)**

```powershell
git clone <this repo>; cd <repo>
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

**Linux / macOS**

```bash
git clone <this repo> && cd <repo>
bash scripts/setup.sh
```

The setup script creates `.venv`, installs pinned dependencies (CPU torch) and downloads `BAAI/bge-small-en-v1.5`
into `models/`. It generates PDF samples and pulls `gemma4:e4b` and `gemma4:e2b` if they are missing.

Manual equivalent:

```bash
python -m venv .venv && .venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/download_models.py && .venv/bin/python scripts/make_samples.py
ollama pull gemma4:e4b
```

## Run (works offline)

```bash
.venv/Scripts/streamlit run app.py      # Windows
.venv/bin/streamlit run app.py          # Linux/macOS
```

Open <http://127.0.0.1:8501>, upload something from `samples/` and click **Analyse document**.
For the Wi-Fi-off demo with the connection monitor, see [scripts/offline_demo.md](scripts/offline_demo.md).

## Test and evaluate

```bash
.venv/Scripts/python -m pytest -m "not needs_ollama"   # fast unit tests, no model needed
.venv/Scripts/python -m pytest -m needs_ollama          # full offline pipeline with real Gemma + netguard strict
.venv/Scripts/python scripts/eval.py                    # writes docs/EVALUATION.md
.venv/Scripts/python scripts/bench_model.py             # tokens/s for E4B vs E2B
```

## Configuration

Copy `.env.example` to `.env`, or set environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `LEXLOCAL_MODEL` | `gemma4:e4b` | Ollama model tag (`gemma4:e2b` is about 3× faster) |
| `LEXLOCAL_OLLAMA_URL` | `http://127.0.0.1:11434` | Must be loopback; other hosts are refused |
| `LEXLOCAL_LLM_TIMEOUT` | `180` | Seconds per model call |
| `LEXLOCAL_NETGUARD` | `strict` | `strict` = loopback only; `off` disables the guard (not recommended) |
| `LEXLOCAL_NUM_CTX` / `LEXLOCAL_MAX_TOKENS` | `4096` / `700` | Context and output limits per call |

Other tunables (fuzzy threshold, chunk budget, file limits) are in [lexlocal/config.py](lexlocal/config.py).
Knowledge files (checklists, vague terms, disclaimers, …) are in [knowledge/](knowledge/).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Ollama not reachable" | Start `ollama serve`, then check `curl http://127.0.0.1:11434/api/tags` |
| "model not pulled" | Run `ollama pull gemma4:e4b`, or pick an available model in the sidebar |
| Very slow analysis | Switch to `gemma4:e2b` and close GPU-heavy apps. The first call includes ~20 s of model load |
| "Embeddings: BM25 only" | Run `python scripts/download_models.py` once while online |
| Scanned PDF rejected | Phase 1 has no OCR. Export the document as a text PDF or DOCX |
| `ollama` command not found on Windows | The API works without it; the setup script pulls models over HTTP |

## Limitations

- English Indian rental and employment agreements only. Other documents get a warning, and results may be weak.
- No OCR yet, so scanned PDFs are declined.
- Checklist-based "missing clause" detection can miss clauses that use unusual wording, and it says "does not *appear* to mention".
- Recall is not perfect: the model may miss a clause. Absence of a finding is not a guarantee.
- Confidence is a simple heuristic in Phase 1 (quote match × label type), not calibrated.
- netguard covers Python sockets in the LexLocal process; see [docs/PRIVACY.md](docs/PRIVACY.md) for the threat model.

## ⚠️ Not legal advice

LexLocal explains what a document says. It does not provide legal advice and does not decide whether anything is legal,
valid, enforceable or fair. For decisions about your situation, consult a qualified lawyer.

## Main technical contribution

A **verify-then-display pipeline for small local LLMs**. Gemma 4 E4B, running on a laptop, proposes findings in
schema-constrained JSON over small clause windows. A deterministic verifier then lets through only claims whose quotes
match the document, and snaps them to the real text. It also checks every number against rule-extracted facts and scrubs
legal-verdict language. A rules-first question router and a topic-overlap check turn "the model guessed" into "the document
is silent". Combined with prompt-injection sanitization and an in-process network guard, LexLocal never displays a
quote that isn't in the document and never sends a byte off the machine. Both properties are covered by tests and
measured in [docs/EVALUATION.md](docs/EVALUATION.md).

## Docs

[Architecture](docs/ARCHITECTURE.md) · [Privacy](docs/PRIVACY.md) · [Model](docs/MODEL.md) ·
[Evaluation](docs/EVALUATION.md) · [Decisions](docs/DECISIONS.md) · [Data](DATA.md) · [Licence: Apache-2.0](LICENSE)

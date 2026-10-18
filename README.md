# LexLocal: private, on-device legal document triage

**Runs entirely on your device. Not legal advice.**

LexLocal reads an Indian rental, lease or employment agreement and explains it in plain language: what you pay,
what you must do, deadlines, penalties, how it ends, what is missing, what is vague, what contradicts itself and
what looks one-sided. **Every claim comes with a verbatim quote and page number that has been checked against the
document.** LexLocal never says whether something is legal, enforceable or fair. Instead it tells you which kind
of lawyer to ask, and what to ask them.

Everything runs locally: Gemma 4 through [Ollama](https://ollama.com) on `127.0.0.1`, local embeddings, local OCR,
and a runtime network guard. **No document content leaves the machine during processing. This was verified offline
and with connection monitoring** (see [Network calls](#network-calls) and [docs/evidence/](docs/evidence/)).

> ZeroDay OSS Hacktoberfest 2026 (IIIT Dharwad), Problem Statement 2.
> Repository: <https://github.com/ZERODAY-2026/NexusBit3.0>

## Demo

- Video: **[link to be added]**
- Try it: run the app (below) and upload files from `samples/`. `rental_tricky.txt` (one-sided terms),
  `rental_conflicts.txt` (planted contradictions), `adversarial.pdf` (hidden text), `edge/scanned.pdf` (OCR),
  and `rental_clean.txt` with `rental_clean_v2.txt` in *Compare two versions*.

| Cited passage beside the source | "The document is silent" |
|---|---|
| ![Document view with the cited quote highlighted on the PDF page](docs/screenshots/cited-passage.png) | ![Silent answer with closest clauses](docs/screenshots/silent.png) |
| **Refusal and lawyer escalation** | **Hidden text and injection flagged** |
| ![Legal-verdict question escalated](docs/screenshots/refusal.png) | ![Hidden content flagged](docs/screenshots/injection.png) |
| **Two-version comparison** | **Places that seem to disagree** |
| ![Word-level comparison](docs/screenshots/comparison.png) | ![Conflicting clauses side by side](docs/screenshots/conflicts.png) |

## Who it's for

Tenants, students, first-job employees and small landlords who are handed an agreement and need to understand it
before they sign, and who can't, or shouldn't, upload it to a cloud AI.

## Scope

- **Documents:** Indian rental, lease and leave-and-license agreements; employment agreements and offer letters.
- **Language:** English documents.
- **Input:** upload a PDF (text or scanned), DOCX or TXT file (up to 25 MB and 200 pages), or type or paste the agreement text. Scanned pages are read with local
  Tesseract OCR (English and Hindi), with a confidence score for each page.
- **Out of scope:** legal advice, verdicts on legality or enforceability, and other contract types (they are
  analysed with a warning).

## Features

| Area | What LexLocal does |
|---|---|
| Ingestion | PDF (PyMuPDF), DOCX and TXT parsed in memory. Encrypted, empty, corrupt, oversized and non-contract files get clear messages. Scanned pages go through local OCR |
| Summary and key terms | Gemma summary with quote-backed key points. A **key-terms table** (parties, term, lock-in, rent or salary, deposit, notice, penalties, dates, governing law) built from rules, with each value next to its exact sentence |
| Findings | Obligations, rights, deadlines, payments, penalties, termination, notice, restrictions and liability. Each finding is labelled **EXPLICIT**, **INTERPRETATION** or **CONCERN**, with text severity and calibrated confidence |
| Citations and navigation | Verbatim quote and page on every finding. A sidebar clause outline with severity labels, "View in document", and the original PDF page rendered with the quote highlighted |
| Missing and vague | Expected clauses that don't appear ("does not appear to mention ...") and vague wording ("sole discretion", "reasonable", ...) |
| Conflicts | Places that disagree: figures vs words, the same term with two values, term vs dates, lock-in vs term, two notice periods for one party, plus Gemma clause-pair checks. Both quotes are shown side by side |
| Worth asking about | One-sided wording, notice periods that differ between the parties, and wording far from typical clauses (embedding distance). Never framed as "illegal" |
| Jurisdiction | Detects the state from governing law, courts or place of signing. General notes for state-dependent topics. No statutory limits are stated |
| Follow-up questions | After the analysis, a chat box at the bottom of every view takes follow-up questions (with starter suggestions). Questions are routed as **document fact** (answered only from verified passages, otherwise *"The document is silent on this"*), **legal verdict** (no verdict, specific lawyer escalation) or **out of scope** (declined) |
| Safety | Prompt-injection scan and removal; hidden PDF text, zero-width characters and look-alike letters detected and kept out of the analysis |
| Compare versions | Clause alignment that survives renumbering, word-level diff, material-change tags (money, dates, periods, termination, penalties, deposit) and Gemma explanations quoting both versions |
| Glossary | Legal terms found in the document with plain meanings, each shown with the sentence where it appears |
| Modes | **Fast** (gemma4:e2b) or **Thorough** (gemma4:e4b plus self-consistency checks) |
| Privacy controls | Network guard (loopback only) with a blocked-attempt counter, no document text in logs, an encrypted temporary store, **Delete document** and **Panic wipe** |
| Export | Markdown or PDF report with citations and disclaimers, built on the device |

**Anti-fabrication:** a model quote is shown only if it matches the document (normalised exact match, or fuzzy
match of at least 90). It is then replaced by the real document span. Numbers in explanations must appear in the
quote or in rule-extracted facts. Sentences that state a legal verdict are removed. Rejected claims are logged for
evaluation and never shown.

## Results

From [docs/EVALUATION.md](docs/EVALUATION.md) (gemma4:e4b, synthetic gold set, network guard strict) and the test suite:

| Metric | Result |
|---|---|
| Displayed findings with a verified verbatim quote | 100% (40/40) |
| Fabricated quotes rejected by the verifier | 100% (127/127); fabricated text shown: 0 |
| Silent-answer / refusal / out-of-scope accuracy | 100% (7/7) / 100% (7/7) / 100% (3/3) |
| Fact-question accuracy | 100% (8/8) |
| Finding recall (quote match) | 100% (18/18) |
| Planted contradictions found (`rental_conflicts.txt`) | 5/5, with 0 false conflicts on the other samples |
| Hidden-content techniques detected (`adversarial.pdf`) | 7/7, all kept out of the analysis |
| Hand-labelled finding accuracy (calibration set) | 92% (47/51) |
| Blocked outbound connections during evaluation | 0 |
| Automated tests | **144 passed** (`pytest -m "not needs_ollama"`), plus 4 end-to-end tests with real Gemma |

The gold set is small and synthetic. See the caveats in EVALUATION.md.

## Model

| | Thorough (default) | Fast |
|---|---|---|
| Ollama tag | `gemma4:e4b` | `gemma4:e2b` |
| Parameters / quantisation | 7.5 B, Q4_K_M (GGUF) | 4.6 B, Q4_K_M (GGUF) |
| Download size (`ollama list`) | 6.58 GB | 4.59 GB |
| Licence | Apache-2.0 (per `ollama show`) | Apache-2.0 |

- Model card: <https://ollama.com/library/gemma4> and <https://ai.google.dev/gemma>. Ollama version tested: **0.40.6**.
- Embeddings: [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) (33 M parameters, about 130 MB, MIT), on CPU.
- OCR: Tesseract 5.4 (Apache-2.0) with `tessdata_fast` English and Hindi data.
- Details and how Gemma is used: [docs/MODEL.md](docs/MODEL.md).

## Hardware and performance

Tested on an Intel Core i5-13420H, 16 GB RAM, NVIDIA RTX 2050 (4 GB), Windows 11, **Python 3.13.2**, Ollama 0.40.6.

Measured with `scripts/benchmark.py` (network guard strict, 0 blocked connections in every run). Full table: [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

| | gemma4:e2b (Fast) | gemma4:e4b (Thorough) |
|---|---|---|
| Generation speed | about 58-60 tokens/s | about 13-15 tokens/s |
| Full analysis, 1-page agreement (7 clauses) | 52 s | 150 s |
| Full analysis, 2-page agreement (21 clauses) | 76 s | 265 s |
| Full analysis, long agreement (61 clauses) | 73 s | 274 s |
| Answer to a question | 2-4 s | 8-14 s |
| Peak RAM, LexLocal process | about 0.7 GB | about 0.3 GB |
| Peak RAM, Ollama (model) | about 1 GB (model mostly in VRAM) | 3-5.6 GB (6.6 GB model split between 4 GB VRAM and RAM) |
| Peak VRAM (whole GPU) | about 2.8 GB | about 2.8 GB |

Analysis time grows slowly with length because at most 3 clauses per category go to the model. OCR adds about
5 s per scanned page. Model loading (about 25 s for E4B) happens once and is not included.

Minimum: 8 GB RAM for Fast mode (E2B). 16 GB is recommended for Thorough mode (E4B).

## Setup (needs internet once)

Prerequisites: Python 3.11 or newer, [Ollama](https://ollama.com/download) running (`ollama serve`), and optionally
[Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) for scanned PDFs.

**Windows (PowerShell)**

```powershell
git clone https://github.com/ZERODAY-2026/NexusBit3.0.git; cd NexusBit3.0
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
winget install UB-Mannheim.TesseractOCR   # optional, for scanned PDFs
```

**Linux / macOS**

```bash
git clone https://github.com/ZERODAY-2026/NexusBit3.0.git && cd NexusBit3.0
bash scripts/setup.sh
sudo apt install tesseract-ocr tesseract-ocr-hin   # or: brew install tesseract tesseract-lang (optional)
```

The setup script creates `.venv`, installs pinned dependencies (CPU torch), and downloads `BAAI/bge-small-en-v1.5`
and the OCR language data into `models/`. It also generates the PDF samples and pulls `gemma4:e4b` and `gemma4:e2b`
if they are missing.

## Run (works offline)

```bash
.venv/Scripts/python -m streamlit run app.py      # Windows
.venv/bin/python -m streamlit run app.py          # Linux/macOS
```

Open <http://127.0.0.1:8501>, upload a file from `samples/` and click **Analyse document**. For the Wi-Fi-off demo
with the connection monitor, see [scripts/offline_demo.md](scripts/offline_demo.md). A Dockerfile for a no-network container is in [docs/DOCKER.md](docs/DOCKER.md) (written but not yet verified; see that page).

**Use a browser profile without extensions for sensitive documents.** An AI-sidebar extension can read anything shown
on a web page. That is outside LexLocal's control.

## Network calls

| When | What | Destination | Document content? |
|---|---|---|---|
| Setup only | `pip install` | PyPI, download.pytorch.org | No |
| Setup only | Embedding model and OCR language data | huggingface.co, github.com | No |
| Setup only | `ollama pull gemma4:e4b`, `gemma4:e2b` | registry.ollama.ai | No |
| Runtime | Gemma inference | 127.0.0.1:11434 (loopback) | Stays on the machine |
| Runtime | Browser to UI | 127.0.0.1:8501 (loopback) | Stays on the machine |
| Runtime, outside LexLocal | Ollama's Windows app may check for updates | ollama.com | **No.** The check is made by the Ollama app and carries no document data |

- Streamlit usage statistics are off (`gatherUsageStats = false`). Hugging Face is offline (`HF_HUB_OFFLINE=1`).
  The UI loads no fonts, scripts or images from the internet (checked by `tests/test_ui_assets.py` and a headless
  browser request log).
- The in-process network guard blocks every non-loopback connection and DNS lookup from LexLocal, and the sidebar counts attempts.
- Evidence: [docs/evidence/](docs/evidence/) has a connection-monitor log, the network-guard test log, and an offline
  end-to-end run with real Gemma. Full threat model: [docs/PRIVACY.md](docs/PRIVACY.md).

## Test and evaluate

```bash
.venv/Scripts/python -m pytest -m "not needs_ollama"   # unit tests, no model needed
.venv/Scripts/python -m pytest -m needs_ollama          # full offline pipeline with real Gemma and the network guard strict
.venv/Scripts/python scripts/eval.py                    # writes docs/EVALUATION.md
.venv/Scripts/python scripts/calibrate.py tune          # confidence reliability table
.venv/Scripts/python scripts/benchmark.py               # writes docs/BENCHMARKS.md
```

## Configuration

Copy `.env.example` to `.env`, or set environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `LEXLOCAL_MODEL` / `LEXLOCAL_FAST_MODEL` | `gemma4:e4b` / `gemma4:e2b` | Models for Thorough and Fast modes |
| `LEXLOCAL_OLLAMA_URL` | `http://127.0.0.1:11434` | Must be loopback; other hosts are refused |
| `LEXLOCAL_NETGUARD` | `strict` | `strict` = loopback only; `off` disables the guard (not recommended) |
| `LEXLOCAL_SELF_CONSISTENCY` / `LEXLOCAL_PAIRWISE` | `2` / `2` | Extra Gemma checks in Thorough mode |
| `LEXLOCAL_OCR` | `on` | `off` declines scanned PDFs instead of running OCR |
| `LEXLOCAL_LLM_TIMEOUT`, `LEXLOCAL_NUM_CTX`, `LEXLOCAL_MAX_TOKENS` | `180`, `4096`, `700` | Model call limits |

Other tunables are in [lexlocal/config.py](lexlocal/config.py). Knowledge files (checklists, reference clauses,
glossary, disclaimers, jurisdiction topics) are in [knowledge/](knowledge/).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Ollama not reachable" | Start `ollama serve`, then check `curl http://127.0.0.1:11434/api/tags` |
| "model not pulled" | `ollama pull gemma4:e4b` (or switch to Fast mode, or pick a pulled model in the sidebar) |
| Very slow analysis | Use Fast mode and close GPU-heavy apps. The first call includes about 20 s of model loading |
| "Embeddings: BM25 only" | Run `python scripts/download_models.py` once while online |
| Scanned PDF rejected | Install Tesseract (see Setup) and run `python scripts/download_models.py` |
| `streamlit` launcher fails after moving the folder | Use `python -m streamlit run app.py`. Venv console launchers hard-code the original path |

## Limitations

- English Indian rental and employment agreements only. Other documents get a warning, and results may be weak.
- Recall is not perfect. The model may miss a clause, so the absence of a finding is not a guarantee.
- Confidence measures how well a claim is anchored in the document, not whether the paraphrase is perfect. In the
  labelled set, the 4 wrong findings looked identical to correct ones on every signal. Read the quote.
- Missing-clause, conflict and one-sided checks are rule- and reference-based. They say "does not appear to" and
  "worth asking about", and they can miss unusual wording.
- OCR quality depends on the scan. Low-confidence pages are flagged and their findings get lower confidence.
- The evaluation set is small and synthetic.
- The network guard covers Python sockets in the LexLocal process. For the strongest guarantee, run with the network off
  (or try the unverified Docker `--network none` setup). See [docs/PRIVACY.md](docs/PRIVACY.md).

## Not legal advice

LexLocal explains what a document says. It does not provide legal advice and does not decide whether anything is
legal, valid, enforceable or fair. For decisions about your situation, consult a qualified lawyer.

## Main technical contribution

A **verify-then-display pipeline for small local LLMs**. Gemma 4, running on a laptop, proposes findings in
schema-constrained JSON over small clause windows. A deterministic verifier lets through only claims whose quotes
match the document, and snaps them to the real text. It also checks every number against rule-extracted facts and
removes legal-verdict language. The same rule applies everywhere Gemma speaks: clause-pair conflicts, version
changes and glossary gaps all have to pass verification, the number check and the verdict check before
they are shown. Rules come first wherever they can (key terms, conflicts, jurisdiction, adversarial content), and the
model fills the gaps.

## Docs

[Architecture](docs/ARCHITECTURE.md) · [Privacy](docs/PRIVACY.md) · [Model](docs/MODEL.md) ·
[Evaluation](docs/EVALUATION.md) · [Benchmarks](docs/BENCHMARKS.md) · [Decisions](docs/DECISIONS.md) ·
[Docker](docs/DOCKER.md) · [Data](DATA.md) · [Contributing](CONTRIBUTING.md) · [Licence: Apache-2.0](LICENSE)

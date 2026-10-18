# Model

| | Default | Fast alternative |
|---|---|---|
| Ollama tag | `gemma4:e4b` | `gemma4:e2b` |
| Parameters (Ollama) | 7.5 B (E4B, "effective 4B") | 4.6 B (E2B, "effective 2B") |
| Quantization | Q4_K_M (GGUF, llama.cpp runner) | Q4_K_M |
| Download size | 6.58 GB | 4.59 GB |
| Context length (model max) | 131,072 (LexLocal uses `num_ctx` 4096) | 131,072 |
| Licence | Apache-2.0 (per `ollama show`) | Apache-2.0 |
| Model card | <https://ollama.com/library/gemma4> · <https://ai.google.dev/gemma> | same |

Ollama version tested: **0.40.6**.

## Install

```bash
ollama pull gemma4:e4b
ollama pull gemma4:e2b   # optional, faster
```

`scripts/setup.ps1` and `scripts/setup.sh` do this through the local Ollama API if a model is missing.

## Measured on the development machine

Hardware: Intel Core i5-13420H (8C/12T), 16 GB RAM, NVIDIA RTX 2050 (4 GB VRAM), Windows 11.
Measured with `python scripts/bench_model.py`: one category-analysis prompt (574 prompt tokens, JSON-schema output), median of 2 warm runs.

| Model | Output tok/s | Prompt tok/s | Latency per call | Cold load | Valid JSON |
|---|---|---|---|---|---|
| gemma4:e4b | **14.4** | 4,309 | 22.2 s | 21.4 s | 100% |
| gemma4:e2b | **65.1** | 5,109 | 8.3 s | 21.4 s | 100% |

E4B does not fit fully in 4 GB of VRAM, so Ollama splits it between the GPU and the CPU. E2B mostly fits, which explains the 4.5× speed gap.

**Default choice:** E4B reaches ≥ 8 tok/s (the threshold in the build plan), so it is the default for quality.
Set `LEXLOCAL_MODEL=gemma4:e2b` in `.env`, or choose it in the sidebar, for about 3× faster analysis on weaker machines.
Full-document latency and RAM for each model are in `docs/EVALUATION.md`.

## How Gemma is used (L10)

| Task | Calls per document | Output |
|---|---|---|
| Plain-language summary + key points with quotes | 1 | `SummaryOut` JSON |
| Category findings (payments, penalties, deadlines, notice, termination, obligations, rights, restrictions, liability) | ≤ 9 (categories with no matching clauses are skipped) | `FindingsOut` JSON |
| Question classification (when the high-precision rules don't decide) | ≤ 1 per question | `ClassifyOut` |
| Grounded answer | 1 per question | `AnswerOut` |
| Lawyer escalation (lawyer type, what to bring, questions) | 1 per verdict question | `EscalationOut` |

All calls use temperature 0.1, a fixed seed, `think: false` and a JSON schema passed to Ollama's `format`.
Output is validated with Pydantic, with one repair retry.

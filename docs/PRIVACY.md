# Privacy

**Claim:** after setup, no document content leaves the machine during processing. This was verified offline and with connection
monitoring. LexLocal sends no telemetry.

## Threat model

| Threat | Mitigation |
|---|---|
| The app or a dependency sends document data to a remote API | No remote APIs are used. `privacy/netguard.py` blocks every non-loopback `connect` and DNS lookup at runtime, counts attempts and shows them in the UI. The LLM client refuses any non-local Ollama URL and ignores system proxies (`trust_env=False`) |
| Library telemetry (Streamlit, Hugging Face) | `browser.gatherUsageStats=false`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`. The embedding model is loaded from a local path with `local_files_only=True` |
| External assets in the UI (fonts, CDNs) | None are used. The Streamlit server binds to `127.0.0.1` only |
| Document text leaking into logs | Code logs only metadata (counts, timings, token counts). `DocTextFilter` redacts any log record containing a fragment of the loaded document. Covered by tests |
| Document persisted on disk | Uploads stay in memory (`st.file_uploader` bytes). Nothing is written to disk except OCR temporary files, which are encrypted (see Storage). **Delete document** and **Panic wipe** clear the session |
| A malicious document steering the model | Prompt-injection scan, sanitization, delimiters, schema-constrained output and output verification (see ARCHITECTURE.md) |
| Ollama itself phoning home | Ollama runs locally. Its only network use is `ollama pull` at setup time. Run with Wi-Fi off to prove it, and `scripts/monitor_connections.*` shows its connections too |

## Data flow

1. The browser (127.0.0.1:8501) uploads the file to the local Streamlit process. The bytes are held in memory.
2. Parsing, chunking, rules, the embeddings index and verification all run in-process, in RAM.
3. Small prompts containing ≤3 clauses go to Ollama at `http://127.0.0.1:11434/api/chat`, which is loopback.
4. Results are shown in the browser. When you clear the session or close the tab, the data is gone.

## Every network call

| When | What | Destination | Document content? |
|---|---|---|---|
| Setup only | `pip install` | PyPI, download.pytorch.org | No |
| Setup only | `scripts/download_models.py` (bge-small-en-v1.5, Tesseract eng/hin data) | huggingface.co, github.com | No |
| Setup only | `ollama pull gemma4:e4b`, `gemma4:e2b` | registry.ollama.ai | No |
| Runtime | LLM inference | 127.0.0.1:11434 (loopback) | Stays on the machine |
| Runtime | Browser <-> UI | 127.0.0.1:8501 (loopback) | Stays on the machine |
| Runtime, outside LexLocal | The Ollama Windows app may check for updates | ollama.com | No: the Ollama app makes the check itself, and no document data passes to it |

There are no other runtime calls from LexLocal. Any attempt is blocked and counted, and the counter is shown in the
sidebar. Streamlit usage statistics are off, Hugging Face runs offline, and the UI loads no external fonts, scripts
or images (`tests/test_ui_assets.py`; a headless-browser request log showed only loopback requests from the page).

**Claim wording:** no document content leaves the machine during processing. This was verified offline and with
connection monitoring (evidence in `docs/evidence/`).

## Proof

- `pytest tests/test_privacy.py`: external IP, DNS and `requests` are blocked; loopback is allowed; logs contain no document text.
- `pytest -m needs_ollama`: the full pipeline runs with netguard strict and asserts zero blocked attempts.
- `scripts/monitor_connections.ps1` / `.sh`: samples the Python and Ollama TCP connections every second during an analysis and reports non-loopback connections. The expected result is `only loopback`.
- Offline demo with Wi-Fi off: `scripts/offline_demo.md`.

**Recorded run (2026-10-18, dev machine, during `scripts/eval.py` with live Gemma calls):**

```
> scripts\monitor_connections.ps1 -Seconds 40
RESULT: only loopback connections observed (240 samples). Log: logs\connections.csv
  python        -> 127.0.0.1:11434   (LexLocal -> Ollama API)
  ollama        -> 127.0.0.1:<port>  (Ollama -> its llama-server runner)
  llama-server  -> 127.0.0.1:<port>
  non-loopback: 0
```

## Storage and deletion

- Document content is held in memory only, in the Streamlit session state. Use **Delete document** or **Panic wipe** in the sidebar, or close the session.
- Log files (`logs/lexlocal.log`, git-ignored) contain metadata only.
- **Encrypted temporary store** (`lexlocal/privacy/vault.py`): the only time LexLocal writes document-derived
  data to disk is OCR, because Tesseract reads page images from files. Each browser session gets a private temp
  directory (`mkdtemp`, owner-only permissions where supported). Cached OCR results are encrypted with Fernet
  (AES-128-CBC with HMAC-SHA256) under a key held only in memory. Tesseract's own temporary image files are created
  in the same directory and deleted by Tesseract right away.
- **Wiping:** files are overwritten with zeros, then deleted, and the key is dropped on **Delete document**, on
  **Panic wipe**, when Streamlit discards the session after the tab closes (garbage-collection finalizer), and at
  process exit. Tested in `tests/test_vault.py`.
- `models/` holds the public embedding model and nothing about your documents.

## Limitations

- netguard is an in-process Python guard. Native code that opens raw sockets without going through Python's
  `socket` module would bypass it. For the strongest guarantee, run with the network off, or in Docker with `--network none` ([DOCKER.md](DOCKER.md), not yet verified).
- Ollama is a separate process outside netguard. It is local, but run `monitor_connections` to verify.
- Memory is not securely zeroed. Python strings may stay in RAM until garbage-collected.
- Streamlit holds uploaded bytes in memory for the session lifetime.
- **Browser extensions are outside LexLocal's control.** An extension that reads page content (AI sidebars, for example) can see what the UI shows. Use a browser profile without extensions for sensitive documents. During development, a headless Edge with extensions enabled showed requests from an installed AI-sidebar extension. With `--disable-extensions`, the page made only loopback requests.

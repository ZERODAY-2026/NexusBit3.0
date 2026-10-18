# Docker offline demo

> **Status: not yet verified.** The image build was started on the development machine but stopped because the disk was nearly full (the Ollama base image alone is 3.6 GB compressed). The files are provided as a starting point; the offline claim is verified instead by the Wi-Fi-off run, the connection monitor and the test suite (docs/evidence/).

The strongest version of the privacy claim: run the whole pipeline in a container that has **no network
interface except loopback** (`--network none`). Ollama runs inside the same container on 127.0.0.1, so the
model is reachable and nothing else is.

## 1. Build (online, once)

```bash
docker build -t lexlocal .
```

The image contains Python dependencies, Tesseract (eng + hin) and the bge-small embedding model. Gemma weights
are not copied into the image; you mount the Ollama model store you already pulled on the host.

## 2. Run the full pipeline with no network

```bash
# Windows (PowerShell)
docker run --rm --network none -v "$env:USERPROFILE\.ollama:/root/.ollama:ro" lexlocal offline-check
# Linux / macOS
docker run --rm --network none -v "$HOME/.ollama:/root/.ollama:ro" lexlocal offline-check
```

`offline-check` first proves that an outbound connection fails, then runs `pytest -m needs_ollama`: parsing,
Gemma analysis, verification and Q&A on the samples, with netguard in strict mode. Other commands:
`test`, `unit`, `eval`.

## 3. Use the UI in a container

A container with `--network none` cannot publish a port, so the browser cannot reach it. For the UI, run with
a published loopback-only port; netguard still blocks every non-loopback connection from LexLocal:

```bash
docker run --rm -p 127.0.0.1:8501:8501 -v "$HOME/.ollama:/root/.ollama:ro" lexlocal app
```

Then open http://127.0.0.1:8501.

#!/usr/bin/env bash
# Setup-time only: fetch the local models (embedding model + Gemma via Ollama).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-.venv/bin/python}
"$PY" scripts/download_models.py
for m in gemma4:e4b gemma4:e2b; do
  curl -s http://127.0.0.1:11434/api/pull -d "{\"model\":\"$m\",\"stream\":false}" >/dev/null && echo "pulled $m"
done

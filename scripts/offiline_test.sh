#!/usr/bin/env bash
# Offline test: run the full pipeline against local Ollama with the network guard in strict mode,
# while monitoring connections. See scripts/offline_demo.md for the manual Wi-Fi-off demo.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-.venv/bin/python}
bash scripts/monitor_connections.sh 180 logs/connections.csv &
MON=$!
"$PY" -m pytest -q -m needs_ollama
"$PY" scripts/eval.py --docs rental_clean.txt
kill $MON 2>/dev/null || true

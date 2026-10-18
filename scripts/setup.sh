#!/usr/bin/env bash
# LexLocal setup for Linux/macOS. Network is used ONLY here (pip, model downloads).
#   bash scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
[ -d .venv ] || "$PY" -m venv .venv
VPY=.venv/bin/python
"$VPY" -m pip install --upgrade pip

if [ "$(uname)" = "Linux" ] && ! command -v nvidia-smi >/dev/null 2>&1; then
  "$VPY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
fi
"$VPY" -m pip install -r requirements.txt

echo "Downloading embedding model (setup-time only)..."
"$VPY" scripts/download_models.py
echo "Generating PDF samples / edge cases..."
"$VPY" scripts/make_samples.py

echo "Checking Ollama on 127.0.0.1:11434..."
if curl -sf http://127.0.0.1:11434/api/tags >/tmp/lexlocal_tags.json; then
  for m in gemma4:e4b gemma4:e2b; do
    if grep -q "\"$m\"" /tmp/lexlocal_tags.json; then echo "  $m present"
    else echo "Pulling $m..."; curl -s http://127.0.0.1:11434/api/pull -d "{\"model\":\"$m\",\"stream\":false}" >/dev/null; fi
  done
else
  echo "WARNING: Ollama not reachable. Install from https://ollama.com, run 'ollama serve', then 'ollama pull gemma4:e4b'"
fi

[ -f .env ] || cp .env.example .env
echo "Setup complete. Run:  .venv/bin/python -m streamlit run app.py"

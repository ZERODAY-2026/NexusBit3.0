#!/bin/sh
# Start Ollama on loopback inside the container, wait for it, then run the requested command.
set -e
ollama serve >/tmp/ollama.log 2>&1 &
for i in $(seq 1 60); do
  if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=1)" 2>/dev/null; then break; fi
  sleep 1
done
case "$1" in
  app)     exec python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 ;;
  test)    exec python -m pytest -m needs_ollama -q ;;
  unit)    exec python -m pytest -m "not needs_ollama" -q ;;
  eval)    exec python scripts/eval.py ;;
  offline-check)
    python - <<'PY'
import socket
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3)
    print("NETWORK REACHABLE: this container is not offline")
except OSError as e:
    print(f"offline confirmed: outbound connection failed ({type(e).__name__})")
PY
    exec python -m pytest -m needs_ollama -q ;;
  *)       exec "$@" ;;
esac

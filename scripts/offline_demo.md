# Offline demo (Wi-Fi OFF)

1. **Once, with internet:** run `scripts/setup.ps1` (Windows) or `scripts/setup.sh` (Linux/macOS). This installs
   dependencies, downloads `bge-small-en-v1.5` into `models/`, and pulls `gemma4:e4b` / `gemma4:e2b` into Ollama.
2. **Disconnect:** turn Wi-Fi off / unplug Ethernet (or Windows: `Airplane mode`; Linux: `nmcli networking off`).
3. **Start Ollama** if it is not running: `ollama serve` (it listens on 127.0.0.1:11434).
4. **Start the connection monitor** in a second terminal:
   - Windows: `powershell -ExecutionPolicy Bypass -File scripts\monitor_connections.ps1 -Seconds 300`
   - Linux: `bash scripts/monitor_connections.sh 300`
5. **Start LexLocal:** `.venv\Scripts\python -m streamlit run app.py` (Linux: `.venv/bin/python -m streamlit run app.py`) and open
   http://127.0.0.1:8501.
6. Upload `samples/rental_tricky.txt`, click **Analyse document**, then ask in the *Ask* tab:
   - "What is the deposit amount?" -> answer with a verified quote
   - "Can I keep a pet?" -> "The document is silent on this." + closest clauses
   - "Is this enforceable?" -> no verdict, lawyer escalation
7. Upload `samples/rental_injection.txt` -> injection banner; analysis unaffected.
8. Check the sidebar: *Ollama local OK*, *Network guard active*, *Blocked outbound attempts: 0*.
9. Stop the monitor -> `RESULT: only loopback connections observed`.
10. Automated equivalent: `pytest -m needs_ollama` (full pipeline with netguard strict) and `python scripts/eval.py`.

# Privacy evidence

Recorded on the development machine (Windows 11, Python 3.13.2, Ollama 0.40.6) on 2026-10-18.

| File | What it shows |
|---|---|
| [connection_monitor.txt](connection_monitor.txt), [connections.csv](connections.csv) | Every TCP connection of the Python, Ollama and llama-server processes, sampled each second for 90 s during a live `gemma4:e4b` analysis: 642 samples, **0 non-loopback** |
| [netguard_tests.txt](netguard_tests.txt) | The network guard blocks external IPs, DNS and `requests`; loopback is allowed; the LLM client refuses remote hosts; logs contain no document text; UI has no external assets; vault encryption and wiping |
| [offline_run.txt](offline_run.txt) | The full pipeline (`pytest -m needs_ollama`) with real Gemma and the network guard strict: zero blocked attempts |
| [ui_requests.txt](ui_requests.txt) | Every request made in a headless browser during an analysis: the page's own requests are loopback only (2 requests came from an installed browser extension) |

How to reproduce: `scripts/monitor_connections.ps1` (or `.sh`), `pytest tests/test_privacy.py`,
`pytest -m needs_ollama`, [docs/DOCKER.md](../DOCKER.md), and [scripts/offline_demo.md](../../scripts/offline_demo.md)
for a manual Wi-Fi-off run.

Note: a manual Wi-Fi-off run should be repeated before the live demo. The headless-browser log excludes requests made by
browser extensions installed on the machine (one AI-sidebar extension contacted its own server during testing;
that traffic comes from the extension, not from the page).

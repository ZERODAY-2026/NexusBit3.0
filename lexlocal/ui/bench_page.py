"""Benchmarks page: shows docs/benchmarks.json written by scripts/benchmark.py (nothing is measured here)."""
from __future__ import annotations

import json

import streamlit as st

from lexlocal import config


def render() -> None:
    st.markdown("#### Benchmarks")
    path = config.DOCS_DIR / "benchmarks.json"
    if not path.exists():
        st.info("No benchmark results yet. Run `python scripts/benchmark.py` (takes about 20 minutes).")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    st.caption(f"Measured {data['date']} on {data['cpu']}, {data['ram_gb']} GB RAM, GPU: {data['gpu'] or 'none'}; "
               f"{data['os']}, Python {data['python']}. Network guard strict; blocked attempts are listed per run. "
               "Re-run with `python scripts/benchmark.py`; details in docs/BENCHMARKS.md.")
    rows = data["results"]
    st.dataframe([{
        "Model": r["model"], "Document": f"{r['size']} ({r['chars']:,} chars, {r['clauses']} clauses)",
        "Analysis (s)": r["analysis_s"], "Q&A (s)": r["qa_s"], "LLM calls": r["llm_calls"],
        "Tokens/s": r["tok_per_s"], "Peak RAM LexLocal (MB)": r["peak_app_mb"],
        "Peak RAM Ollama (MB)": r["peak_ollama_mb"], "Peak VRAM (MB)": r["peak_vram_mb"], "Blocked": r["blocked"],
    } for r in rows], hide_index=True, width="stretch")
    st.markdown("**Per-stage latency (seconds)**")
    stages = sorted({k for r in rows for k in r["stages"]}, key=lambda k: -max(r["stages"].get(k, 0) for r in rows))
    st.dataframe([{"Model": r["model"], "Document": r["size"], **{s: r["stages"].get(s) for s in stages}} for r in rows],
                 hide_index=True, width="stretch")
    if data.get("idle_vram_mb") is not None:
        st.caption(f"VRAM in use before the run (display and other apps): {data['idle_vram_mb']} MB. "
                   "Peak VRAM is total GPU memory in use.")

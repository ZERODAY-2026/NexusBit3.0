"""Benchmarks: per-stage latency, tokens/s, peak RAM and VRAM, E2B vs E4B, by document length.

    python scripts/benchmark.py            # both models, three document lengths
    python scripts/benchmark.py --models gemma4:e2b

Writes docs/benchmarks.json (read by the Benchmarks view) and docs/BENCHMARKS.md.
Runs with the network guard in strict mode, like the app.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psutil  # noqa: E402

from lexlocal import config  # noqa: E402
from lexlocal.privacy import netguard  # noqa: E402

OUT_JSON = ROOT / "docs" / "benchmarks.json"
OUT_MD = ROOT / "docs" / "BENCHMARKS.md"


def vram_used_mb() -> int | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


class Sampler:
    """Samples RSS of this process and of Ollama's processes, and GPU memory, every 0.5 s."""

    def __init__(self):
        self.me = psutil.Process()
        self.peak_app = self.peak_ollama = 0
        self.peak_vram = None
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.peak_app = max(self.peak_app, self.me.memory_info().rss)
            total = 0
            for p in psutil.process_iter(["name"]):
                try:
                    n = (p.info["name"] or "").lower()
                    if "ollama" in n or "llama-server" in n or "llama_server" in n:
                        total += p.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            self.peak_ollama = max(self.peak_ollama, total)
            v = vram_used_mb()
            if v is not None:
                self.peak_vram = max(self.peak_vram or 0, v)
            self._stop.wait(0.5)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self._t.join()


def long_doc():
    """A ~3x longer agreement: the clean rental agreement followed by renumbered copies of its clauses."""
    from lexlocal.ingest.parser import parse_bytes

    base = (ROOT / "samples" / "rental_clean.txt").read_text(encoding="utf-8")
    body = base.split("1. TERM", 1)[1]
    extra = "".join(f"\n\nSCHEDULE {i}\n1. TERM" + body for i in ("B", "C"))
    return parse_bytes("rental_long.txt", (base + extra).encode("utf-8"))


def docs():
    from lexlocal.ingest.parser import parse_file

    return [("short", parse_file(ROOT / "samples" / "rental_injection.txt")),
            ("medium", parse_file(ROOT / "samples" / "rental_clean.txt")),
            ("long", long_doc())]


def run(models: list[str]) -> dict:
    from lexlocal.analysis.analyzer import Analyzer
    from lexlocal.analysis.qa import QAEngine
    from lexlocal.llm import client as llm_client
    from lexlocal.llm.client import OllamaClient
    from lexlocal.retrieval.index import HybridIndex

    netguard.install()
    results = []
    idle_vram = vram_used_mb()
    for model in models:
        llm = OllamaClient(model=model)
        if not llm.health().get("model_available"):
            print(f"skip {model}: not pulled")
            continue
        t = time.perf_counter()
        llm.generate_text("Reply with OK.", "OK?", max_tokens=5)  # load the model; timed separately
        load_s = time.perf_counter() - t
        for size, doc in docs():
            for k in llm_client.STATS:
                llm_client.STATS[k] = 0
            with Sampler() as s:
                t0 = time.perf_counter()
                report, chunks = Analyzer(llm).analyze(doc)
                analysis_s = time.perf_counter() - t0
                qa = QAEngine(doc, chunks, report.doc_type, llm, HybridIndex(chunks), report.injection_flags,
                              [f.value for f in report.facts])
                t1 = time.perf_counter()
                qa.ask("What is the notice period?")
                qa_s = time.perf_counter() - t1
            st = dict(llm_client.STATS)
            row = {"model": model, "size": size, "chars": len(doc.text), "clauses": len(chunks),
                   "analysis_s": round(analysis_s, 1), "qa_s": round(qa_s, 1), "model_load_s": round(load_s, 1),
                   "llm_calls": st["calls"], "output_tokens": st["output_tokens"], "prompt_tokens": st["prompt_tokens"],
                   "tok_per_s": round(st["output_tokens"] / st["seconds"], 1) if st["seconds"] else None,
                   "stages": {x.stage: x.seconds for x in report.timings},
                   "peak_app_mb": round(s.peak_app / 2**20), "peak_ollama_mb": round(s.peak_ollama / 2**20),
                   "peak_vram_mb": s.peak_vram, "findings": len(report.findings),
                   "blocked": len(netguard.blocked_attempts())}
            results.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "stages"}), flush=True)
    vm = psutil.virtual_memory()
    gpu = None
    if shutil.which("nvidia-smi"):
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True).stdout.strip()
    return {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "python": platform.python_version(),
            "os": platform.platform(), "cpu": platform.processor(), "ram_gb": round(vm.total / 2**30, 1),
            "gpu": gpu, "idle_vram_mb": idle_vram, "pairwise_checks": config.PAIRWISE_CHECKS,
            "self_consistency_calls": config.SELF_CONSISTENCY_CALLS, "results": results}


def write_md(data: dict) -> None:
    rows = data["results"]
    stages = sorted({k for r in rows for k in r["stages"]}, key=lambda k: -max(r["stages"].get(k, 0) for r in rows))
    L = ["# Benchmarks", "", "Generated by `python scripts/benchmark.py`. Do not edit by hand.", "",
         f"- Date: {data['date']}", f"- Machine: {data['cpu']}, {data['ram_gb']} GB RAM, GPU: {data['gpu'] or 'none'}",
         f"- OS / Python: {data['os']} / {data['python']}",
         f"- VRAM in use before the run (other apps, display): {data['idle_vram_mb']} MB",
         f"- Settings: {data['pairwise_checks']} pairwise checks, {data['self_consistency_calls']} self-consistency calls, "
         "network guard strict", "",
         "## Summary", "",
         "| Model | Document | Characters | Clauses | Analysis | Q&A | LLM calls | Output tokens | Tokens/s | Peak RAM (LexLocal) | Peak RAM (Ollama) | Peak VRAM | Blocked |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['model']} | {r['size']} | {r['chars']:,} | {r['clauses']} | {r['analysis_s']} s | {r['qa_s']} s | "
                 f"{r['llm_calls']} | {r['output_tokens']:,} | {r['tok_per_s']} | {r['peak_app_mb']:,} MB | "
                 f"{r['peak_ollama_mb']:,} MB | {r['peak_vram_mb'] if r['peak_vram_mb'] is not None else 'n/a'} MB | {r['blocked']} |")
    L += ["", "## Per-stage latency (seconds)", "", "| Model | Document | " + " | ".join(stages) + " |",
          "|---|---|" + "---|" * len(stages)]
    for r in rows:
        L.append(f"| {r['model']} | {r['size']} | " + " | ".join(str(r["stages"].get(s, "")) for s in stages) + " |")
    L += ["", "## Notes", "",
          "- Peak RAM (Ollama) is the summed working set of the Ollama server and its llama-server runner, which holds the model.",
          "- Peak VRAM is total GPU memory in use (nvidia-smi), including other applications; subtract the idle figure above.",
          "- Model load time is measured once per model before the runs and is not included in analysis time.",
          "- The long document is the clean rental agreement with two renumbered copies of its clauses appended.",
          "- Both models ran with the same extra checks (self-consistency and pairwise, the Thorough settings), so the "
          "E2B rows overstate Fast-mode time slightly; Fast mode skips self-consistency.",
          "- Analysis time is roughly flat from medium to long documents because LexLocal sends at most 3 clauses per "
          "category to the model; longer documents mainly cost retrieval and rule time, which stays under a second.",
          "- The first run's 'consistency' stage includes loading the embedding model (about 15 s, once per process).",
          "- If 'VRAM in use before the run' is already high, a model was still resident from earlier use, so peak VRAM "
          "mostly reflects that resident model. E4B (6.6 GB) does not fit in 4 GB of VRAM and is split with system RAM, "
          "which is why its Ollama RAM is several GB.", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[config.FAST_MODEL, config.MODEL])
    a = ap.parse_args()
    data = run(a.models)
    OUT_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")
    write_md(data)
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")

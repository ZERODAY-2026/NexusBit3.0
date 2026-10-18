"""Benchmark local Gemma variants on a sample clause: latency and tokens/s.

    python scripts/bench_model.py [--models gemma4:e4b gemma4:e2b] [--runs 3]

Recommends E4B if it reaches >= 8 tok/s, else E2B. Writes docs/bench_results.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from lexlocal import config  # noqa: E402
from lexlocal.llm import prompts  # noqa: E402
from lexlocal.models import Chunk  # noqa: E402

CLAUSE = ("3.2 The Licensor may deduct from the deposit such amounts as it deems fit towards painting, cleaning, "
          "repairs and any other charges, and the decision of the Licensor in this regard shall be final. "
          "3.3 If the Licensee vacates the premises before the expiry of 11 months for any reason whatsoever, "
          "the entire deposit shall be forfeited and shall not be refunded.")


def run(model: str) -> dict:
    s = requests.Session()
    s.trust_env = False
    chunk = Chunk(id="c001", text=CLAUSE, start=0, end=len(CLAUSE), page=1)
    body = {
        "model": model, "stream": False, "keep_alive": "30m", "think": False,
        "messages": [{"role": "system", "content": prompts.BASE_SYSTEM},
                     {"role": "user", "content": prompts.findings_prompt("penalties", "rental", [chunk], 3000)}],
        "format": prompts.FindingsOut.model_json_schema(),
        "options": {"temperature": 0.1, "num_ctx": config.LLM_NUM_CTX, "num_predict": 500, "seed": 7},
    }
    t0 = time.perf_counter()
    r = s.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=600)
    if r.status_code == 400 and "think" in r.text.lower():
        body.pop("think")
        r = s.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=600)
    r.raise_for_status()
    d = r.json()
    wall = time.perf_counter() - t0
    ev = d.get("eval_count", 0)
    evd = d.get("eval_duration", 1) / 1e9
    try:
        json.loads(d["message"]["content"])
        valid = True
    except Exception:
        valid = False
    return {"wall_s": wall, "out_tokens": ev, "tok_s": ev / evd if evd else 0,
            "prompt_tokens": d.get("prompt_eval_count", 0),
            "prompt_tok_s": d.get("prompt_eval_count", 0) / (d.get("prompt_eval_duration", 1) / 1e9),
            "load_s": d.get("load_duration", 0) / 1e9, "valid_json": valid}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemma4:e4b", "gemma4:e2b"])
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5).json()
    available = {m["name"] for m in tags.get("models", [])}
    version = requests.get(f"{config.OLLAMA_URL}/api/version", timeout=5).json().get("version")
    results = {"ollama_version": version, "models": {}}
    for m in a.models:
        if m not in available:
            print(f"{m}: not pulled, skipping")
            continue
        print(f"{m}: warm-up...", flush=True)
        warm = run(m)
        runs = [run(m) for _ in range(a.runs)]
        res = {
            "cold_load_s": round(warm["load_s"], 2),
            "median_latency_s": round(statistics.median(r["wall_s"] for r in runs), 2),
            "median_tok_s": round(statistics.median(r["tok_s"] for r in runs), 1),
            "median_prompt_tok_s": round(statistics.median(r["prompt_tok_s"] for r in runs), 1),
            "median_out_tokens": int(statistics.median(r["out_tokens"] for r in runs)),
            "prompt_tokens": runs[0]["prompt_tokens"],
            "valid_json_rate": sum(r["valid_json"] for r in runs) / len(runs),
            "size_bytes": next((t.get("size") for t in tags["models"] if t["name"] == m), None),
            "details": next((t.get("details") for t in tags["models"] if t["name"] == m), None),
        }
        results["models"][m] = res
        print(f"{m}: {res['median_tok_s']} tok/s, {res['median_latency_s']} s/call, json ok {res['valid_json_rate']:.0%}")
    e4 = results["models"].get("gemma4:e4b", {}).get("median_tok_s", 0)
    rec = "gemma4:e4b" if e4 >= 8 else ("gemma4:e2b" if "gemma4:e2b" in results["models"] else "gemma4:e4b")
    results["recommended_default"] = rec
    print(f"Recommended default model: {rec}")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "bench_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

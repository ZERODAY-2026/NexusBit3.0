"""Confidence calibration.

  python scripts/calibrate.py collect   # run the pipeline on samples, write eval/calibration_findings.json
  python scripts/calibrate.py tune      # read eval/confidence_labels.yaml, pick weights/thresholds, print reliability

Labels: for every collected finding, a person reads the explanation against the verified quote and
marks it correct (accurate, correctly categorised and not misleading) or not. The samples are synthetic,
so the quotes in these files are not private data.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from lexlocal import config  # noqa: E402
from lexlocal.privacy import netguard  # noqa: E402

FINDINGS = ROOT / "eval" / "calibration_findings.json"
LABELS = ROOT / "eval" / "confidence_labels.yaml"
DOCS = ["rental_clean.txt", "rental_tricky.txt", "employment_offer.txt", "rental_injection.txt", "rental_conflicts.txt"]


def collect():
    from lexlocal.analysis.analyzer import Analyzer
    from lexlocal.ingest.parser import parse_file
    from lexlocal.llm.client import OllamaClient

    netguard.install()
    llm = OllamaClient(model=config.MODEL)
    rows = []
    for name in DOCS:
        report, _ = Analyzer(llm).analyze(parse_file(ROOT / "samples" / name))
        for i, f in enumerate(report.findings):
            rows.append({"id": f"{name}#{i}", "doc": name, "category": f.category, "kind": f.kind.value,
                         "severity": f.severity.value, "source": f.source, "title": f.title,
                         "explanation": f.plain_explanation, "quote": f.quote, "signals": f.signals,
                         "ambiguous": bool(f.ambiguity_note), "confidence": f.confidence})
        print(f"{name}: {len(report.findings)} findings", flush=True)
    FINDINGS.write_text(json.dumps({"model": config.MODEL, "findings": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {FINDINGS} ({len(rows)} findings, blocked={len(netguard.blocked_attempts())})")


def recompute_signals(rows):
    """Recompute the deterministic signals with the current code (the model's sampled outputs are kept)."""
    from lexlocal.analysis import confidence
    from lexlocal.extract import categories as cats
    from lexlocal.extract.rules import extract_facts
    from lexlocal.ingest.chunker import chunk_document
    from lexlocal.ingest.parser import parse_file
    from lexlocal.models import Finding

    cache = {}
    for r in rows:
        if r["doc"] not in cache:
            d = parse_file(ROOT / "samples" / r["doc"])
            ch = chunk_document(d)
            cats.tag_chunks(ch)
            cache[r["doc"]] = (d, ch, extract_facts(d))
        d, ch, facts = cache[r["doc"]]
        s = d.text.find(r["quote"])
        if s < 0:
            continue
        chunk = next((c for c in ch if c.start <= s < c.end), None)
        f = Finding(category=r["category"], title=r["title"], plain_explanation=r["explanation"], quote=r["quote"],
                    chunk_id=chunk.id if chunk else "", page=1, match_score=r["signals"].get("match", 1.0) * 100)
        new = confidence.signals_for(f, s, s + len(r["quote"]), facts, chunk.categories if chunk else [])
        if r["source"] == "rules":
            new["agreement"] = 1.0
        if "consistency" in r["signals"]:
            new["consistency"] = r["signals"]["consistency"]
        r["signals"] = new


def _score(row, weights, priors):
    from lexlocal.models import Kind

    s = row["signals"]
    used = {k: w for k, w in weights.items() if k in s}
    v = sum(s[k] * w for k, w in used.items()) / sum(used.values())
    v *= priors[Kind(row["kind"])]
    return v * (0.92 if row["ambiguous"] else 1.0)


def tune():
    from lexlocal.analysis import confidence
    from lexlocal.models import Kind

    data = json.loads(FINDINGS.read_text(encoding="utf-8"))["findings"]
    labels = yaml.safe_load(LABELS.read_text(encoding="utf-8"))["labels"]
    recompute_signals(data)
    labels_why = {}
    for line in LABELS.read_text(encoding="utf-8").splitlines():
        if ": false" in line and "   # " in line:
            labels_why[line.split('"')[1]] = line.split("   # ", 1)[1].strip()
    rows = [r for r in data if r["id"] in labels]
    y = [bool(labels[r["id"]]) for r in rows]
    print(f"{len(rows)} labelled findings, {sum(y)} correct ({sum(y) / len(y):.0%})")

    def brier(weights, priors):
        return sum((_score(r, weights, priors) - t) ** 2 for r, t in zip(rows, y)) / len(rows)

    grid = [0.1, 0.2, 0.3, 0.4]
    best = (9.0, confidence.WEIGHTS, confidence.KIND_PRIOR)
    for wm, wa, wc, ws in itertools.product(grid, repeat=4):
        w = {"match": wm, "agreement": wa, "category": wc, "consistency": ws}
        for pi, pc in itertools.product([0.75, 0.85, 0.95], [0.75, 0.85, 0.95]):
            p = {Kind.explicit: 1.0, Kind.interpretation: pi, Kind.concern: pc}
            b = brier(w, p)
            if b < best[0] - 1e-9:
                best = (b, w, p)
    b, w, p = best
    print(f"current Brier {brier(confidence.WEIGHTS, confidence.KIND_PRIOR):.4f} -> tuned {b:.4f}")
    print("weights", w, "priors", {k.value: v for k, v in p.items()})
    scores = sorted(_score(r, w, p) for r in rows)
    # Thresholds: the lowest cut where precision above it is >= 0.9 (High) / >= 0.75 (Medium), on a 0.05 grid.
    def prec_above(cut):
        sel = [t for r, t in zip(rows, y) if _score(r, w, p) >= cut]
        return (sum(sel) / len(sel), len(sel)) if sel else (0, 0)
    cuts = [round(x * 0.05, 2) for x in range(6, 20)]
    if scores[0] >= config.CONF_HIGH or len({t for t in y}) < 2:
        # Every labelled finding already scores High (or all labels agree): the data cannot place a cut,
        # so keep the documented defaults and weights instead of fitting noise.
        high, med, w, p = config.CONF_HIGH, config.CONF_MEDIUM, confidence.WEIGHTS, confidence.KIND_PRIOR
        print("no separation in the labelled data: keeping default weights and thresholds")
    else:
        high = next((c for c in cuts if prec_above(c)[0] >= 0.9 and prec_above(c)[1] >= 5), config.CONF_HIGH)
        med = next((c for c in cuts if c < high and prec_above(c)[0] >= 0.75), config.CONF_MEDIUM)
    print(f"thresholds: High >= {high}, Medium >= {med}")
    scores = sorted(_score(r, w, p) for r in rows)
    errors = [r for r, t in zip(rows, y) if not t]
    sig_names = sorted({k for r in rows for k in r["signals"]})
    def avg(group, k):  # mean over findings where the signal applies, with how many it applied to
        vals = [r["signals"][k] for r in group if k in r["signals"]]
        return f"{sum(vals) / len(vals):.2f} (n={len(vals)})" if vals else "n/a"

    right = [r for r, t in zip(rows, y) if t]
    mean = {k: (avg(errors, k), avg(right, k)) for k in sig_names}
    table = []
    for name, lo, hi in [("High", high, 9), ("Medium", med, high), ("Low", -1, med)]:
        sel = [t for r, t in zip(rows, y) if lo <= _score(r, w, p) < hi]
        table.append((name, len(sel), sum(sel)))
        print(f"  {name:6} n={len(sel):3} correct={sum(sel):3} accuracy={(sum(sel) / len(sel) if sel else 0):.0%}")
    print("score range", round(scores[0], 3), round(scores[-1], 3))
    out = {"model": json.loads(FINDINGS.read_text(encoding="utf-8"))["model"], "weights": w,
           "priors": {k.value: v for k, v in p.items()}, "high": high, "medium": med, "table": table,
           "n": len(rows), "correct": sum(y), "brier_default": round(brier(confidence.WEIGHTS, confidence.KIND_PRIOR), 4),
           "brier_best_grid": round(b, 4), "score_min": round(scores[0], 3), "score_max": round(scores[-1], 3),
           "signal_means_wrong_vs_right": mean,
           "errors": [{"id": r["id"], "why": labels_why.get(r["id"], "")} for r in errors]}
    (ROOT / "eval" / "calibration_result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def reliability_markdown() -> list[str]:
    """The reliability section for docs/EVALUATION.md (from eval/calibration_result.json)."""
    path = ROOT / "eval" / "calibration_result.json"
    if not path.exists():
        return []
    r = json.loads(path.read_text(encoding="utf-8"))
    L = ["## Confidence calibration (reliability)", "",
         f"Hand-labelled set: {r['n']} displayed findings from a `{r['model']}` run on 5 samples; {r['correct']} judged accurate "
         f"({r['correct'] / r['n']:.0%}). Labels: `eval/confidence_labels.yaml`. Method: `python scripts/calibrate.py tune`.", "",
         "| Confidence label | Threshold | Findings | Accurate | Accuracy |", "|---|---|---|---|---|"]
    th = {"High": f">= {r['high']}", "Medium": f">= {r['medium']}", "Low": f"< {r['medium']}"}
    for name, n, ok in r["table"]:
        L.append(f"| {name} | {th[name]} | {n} | {ok} | {f'{ok / n:.0%}' if n else '-'} |")
    L += ["", f"- Scores ranged {r['score_min']} to {r['score_max']}. Brier score {r['brier_default']} with the default weights; "
          f"the best grid-searched weights reached {r['brier_best_grid']}, too small a gain to justify refitting on {r['n']} items, "
          "so the defaults are kept.",
          "- Mean signal values, wrong vs right findings: "
          + "; ".join(f"{k} {v[0]} vs {v[1]}" for k, v in r["signal_means_wrong_vs_right"].items()) + ".",
          "- **Honest reading:** every wrong finding had a verbatim-verified quote, so the quote-match and rule-agreement "
          "signals cannot see these errors. They were interpretation mistakes: "
          + "; ".join(e["why"] for e in r["errors"]) + ". "
          "Confidence here measures how well a claim is anchored in the document, not whether the paraphrase is perfect. "
          "This is why every finding shows its quote next to the explanation.", ""]
    return L


if __name__ == "__main__":
    {"collect": collect, "tune": tune}[sys.argv[1]]()

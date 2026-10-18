"""Presentation helpers shared by the UI and exports (text labels, never colour only)."""
from __future__ import annotations

from lexlocal import knowledge
from lexlocal.extract.categories import label
from lexlocal.models import Finding, Kind, Report, Severity

KIND_LABEL = {
    Kind.explicit: "EXPLICIT · the document states this",
    Kind.interpretation: "INTERPRETATION · a reading of the wording",
    Kind.concern: "CONCERN · worth asking a lawyer about",
}
SEVERITY_LABEL = {Severity.high: "HIGH", Severity.medium: "MEDIUM", Severity.low: "LOW", Severity.info: "INFO"}


def confidence_label(c: float) -> str:
    from lexlocal.analysis.confidence import label

    return label(c)


FACT_LABELS = {"party": "Parties", "role": "Roles", "date": "Dates", "amount": "Amounts",
               "duration": "Durations", "notice_period": "Notice periods", "percentage": "Percentages",
               "governing_law": "Governing law / courts"}


def facts_by_type(report: Report) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in report.facts:
        out.setdefault(f.type, []).append(f)
    return out


def top_concerns(report: Report, n: int = 5) -> list[Finding]:
    pri = [f for f in report.findings if f.kind == Kind.concern or f.severity == Severity.high]
    return pri[:n]


def by_category(report: Report) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for f in report.findings:
        out.setdefault(f.category, []).append(f)
    return out


def finding_markdown(f: Finding) -> str:
    lines = [f"### [{SEVERITY_LABEL[f.severity]}] {f.title}",
             f"*{SEVERITY_LABEL[f.severity]} severity · {KIND_LABEL[f.kind]} · confidence {confidence_label(f.confidence)}*",
             "", f.plain_explanation, "", f"> **Document says (page {f.page}):** “{f.quote}”"]
    if f.ambiguity_note:
        lines += ["", f"**Unclear wording:** {f.ambiguity_note}"]
    if f.needs_lawyer:
        lines += ["", "*Ask a lawyer about this.*"]
    return "\n".join(lines)


def report_markdown(report: Report) -> str:
    d = knowledge.disclaimer("en")
    parts = [f"# LexLocal report — {report.doc_name}", "", f"_{d['disclaimer']}_", "",
             f"Document type: **{report.doc_type}** · Model: `{report.model}` (local)", "", "## Summary", report.summary or "_n/a_", ""]
    for cat, items in by_category(report).items():
        parts += [f"## {label(cat)}", ""] + [finding_markdown(f) + "\n" for f in items]
    if report.missing_clauses:
        parts += ["## Not found in the document", ""] + [f"- The document does not appear to mention **{m}**." for m in report.missing_clauses]
    parts += ["", f"_{d['escalation']}_"]
    return "\n".join(parts)


_SIGNAL_NAMES = {"match": "quote match", "agreement": "agrees with rule-extracted facts", "category": "clause topic fits",
                 "consistency": "found again in a second sample", "ocr": "OCR confidence of the page"}


def signals_text(signals: dict) -> str:
    """Plain-text breakdown of what the confidence is based on."""
    if not signals:
        return "No confidence signals recorded."
    return "Confidence is based on: " + "; ".join(f"{_SIGNAL_NAMES.get(k, k)} {v:.2f}" for k, v in signals.items())

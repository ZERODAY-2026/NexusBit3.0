"""Local report export: Markdown and PDF, with citations and the fixed disclaimers.

Built entirely on this machine (PyMuPDF Story for the PDF). Nothing is written to disk by this module:
the caller gets bytes and hands them to the browser as a download.
"""
from __future__ import annotations

import html
import io
from datetime import datetime

from lexlocal import knowledge
from lexlocal.extract.categories import label
from lexlocal.models import Report
from lexlocal.report import render


def _md_quote(q: str, page: int) -> str:
    return f"> \"{q}\" (page {page})"


def to_markdown(report: Report) -> str:
    d = knowledge.disclaimer("en")
    when = datetime.now().strftime("%d %B %Y, %H:%M")
    L = [f"# LexLocal report: {report.doc_name}", "",
         f"*{d['disclaimer']}*", "",
         f"Document type: {report.doc_type}. Generated {when} on this device with `{report.model}` via Ollama "
         "(127.0.0.1). Every quote below was verified against the document.", ""]
    L += ["## Summary", "", report.summary or "_Summary unavailable._", ""]
    if report.key_terms:
        L += ["## Key terms", "", "| Term | Value | Page | Document says |", "|---|---|---|---|"]
        L += [f"| {k.field} | {k.value} | {k.page} | \"{k.quote.replace('|', '/')}\" |" for k in report.key_terms]
        L.append("")
    if report.conflicts:
        L += ["## Places that seem to disagree", ""]
        for c in report.conflicts:
            L += [f"### {c.title}", "", c.explanation, "", _md_quote(c.quote_a, c.page_a)]
            if c.quote_b:
                L += ["", _md_quote(c.quote_b, c.page_b)]
            L.append("")
    top = render.top_concerns(report, n=10)
    if top:
        L += ["## Top concerns", ""] + [render.finding_markdown(f) + "\n" for f in top]
    if report.unusual:
        L += ["## Worth asking about", ""]
        for u in report.unusual:
            L += [f"- **{u.title}** ({u.basis}): {u.explanation}", f"  {_md_quote(u.quote, u.page)}"]
        L.append("")
    for cat, items in render.by_category(report).items():
        L += [f"## {label(cat)}", ""] + [render.finding_markdown(f) + "\n" for f in items]
    if report.missing_clauses:
        L += ["## Not found in the document", ""]
        L += [f"- The document does not appear to mention **{m}**." for m in report.missing_clauses] + [""]
    if report.vague_terms:
        L += ["## Vague wording", ""] + [f"- \"{v.term}\" (page {v.page}): \"{v.quote}\"" for v in report.vague_terms[:25]] + [""]
    if report.jurisdiction_items:
        j = report.jurisdiction
        L += ["## Jurisdiction-dependent topics (general information)", ""]
        if j.state:
            L += [f"The document points to **{j.state}** ({j.basis}: \"{j.value}\").", ""]
        L += [f"- **{n.topic}**: {n.note}" for n in report.jurisdiction_items] + [""]
    if report.adversarial or report.injection_flags:
        L += ["## Safety", ""]
        L += [f"- Page {a.page}: {a.kind}, {a.detail}" for a in report.adversarial]
        L += [f"- Page {f.page}: instruction-like text removed from what the model saw: \"{f.quote}\"" for f in report.injection_flags]
        L.append("")
    L += ["---", "", f"*{d['disclaimer']}* {d['escalation']}", ""]
    return "\n".join(L)


_CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #1F1D1A; }
h1 { font-family: serif; font-size: 18pt; }
h2 { font-family: serif; font-size: 13pt; margin-top: 14pt; border-bottom: 1px solid #E7DFCC; }
h3 { font-family: serif; font-size: 11pt; }
blockquote { margin-left: 10pt; color: #5E574C; }
.note { color: #5E574C; font-size: 9pt; }
table { border-collapse: collapse; }
td, th { border: 1px solid #E7DFCC; padding: 3pt; font-size: 9pt; vertical-align: top; }
"""


def _md_to_html(md: str) -> str:
    """Tiny converter for the Markdown that to_markdown() produces (headings, lists, quotes, tables, bold/italic)."""
    import re

    out, in_table, in_list = [], False, False

    def inline(t: str) -> str:
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", t)
        return re.sub(r"`(.+?)`", r"\1", t)

    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-"):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
            continue
        if in_list and not line.startswith("  "):
            out.append("</ul>")
            in_list = False
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.strip().startswith("> "):
            out.append(f"<blockquote>{inline(line.strip()[2:])}</blockquote>")
        elif line.strip() == "---":
            out.append("<hr/>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def to_pdf(report: Report) -> bytes:
    import pymupdf

    story = pymupdf.Story(html=_md_to_html(to_markdown(report)), user_css=_CSS)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page = pymupdf.paper_rect("a4")
    area = page + (48, 48, -48, -48)
    more = 1
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()

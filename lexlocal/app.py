"""LexLocal Streamlit UI. Run with:  streamlit run app.py"""
from __future__ import annotations

import gc
import hashlib
import html
import re
import time

from lexlocal import config  # noqa: F401  (sets HF offline env vars first)
from lexlocal.privacy import netguard

if config.NETGUARD_MODE == "strict":
    netguard.install()

import streamlit as st  # noqa: E402

from lexlocal import knowledge  # noqa: E402
from lexlocal.analysis.analyzer import Analyzer  # noqa: E402
from lexlocal.analysis.qa import QAEngine  # noqa: E402
from lexlocal.extract.categories import label  # noqa: E402
from lexlocal.ingest.parser import IngestError, parse_bytes  # noqa: E402
from lexlocal.llm.client import OllamaClient  # noqa: E402
from lexlocal.models import Kind  # noqa: E402
from lexlocal.privacy.logging_setup import clear_document, register_document, setup_logging  # noqa: E402
from lexlocal.report import render  # noqa: E402
from lexlocal.retrieval.index import HybridIndex, embedder_status, get_embedder  # noqa: E402

setup_logging(config.LOG_LEVEL, config.LOG_DIR / "lexlocal.log")

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|$~])")


def esc(text: str) -> str:
    """Escape markdown so document text renders literally (and $ never triggers LaTeX)."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def highlight(passage: str, quote: str) -> str:
    """HTML-escaped passage with the quote wrapped in <mark>."""
    i = passage.find(quote)
    if i < 0:
        return html.escape(passage)
    return (html.escape(passage[:i]) + "<mark>" + html.escape(quote) + "</mark>" + html.escape(passage[i + len(quote):]))


DOC_KEYS = ["doc", "report", "chunks", "qa", "history", "doc_hash", "error", "index"]


def clear_doc():
    for k in DOC_KEYS:
        st.session_state.pop(k, None)
    clear_document()
    gc.collect()


# ------------------------------------------------------------------ page
st.set_page_config(page_title="LexLocal — private contract triage", page_icon="⚖️", layout="wide")
disc = knowledge.disclaimer("en")

st.markdown(
    "<div style='padding:10px 14px;border:2px solid #2e7d32;border-radius:8px;margin-bottom:8px'>"
    "<b>🔒 Runs 100% on your device · Not legal advice</b><br>"
    f"<span style='font-size:0.9em'>{html.escape(disc['disclaimer'])}</span></div>",
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def _warm_embedder():
    return get_embedder() is not None


llm = OllamaClient(model=st.session_state.get("model", config.MODEL))

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("⚖️ LexLocal")
    health = llm.health()
    if health["ok"] and health["model_available"]:
        st.success(f"✓ Ollama local (127.0.0.1) · {llm.model}")
    elif health["ok"]:
        st.warning(f"Ollama running, but model `{llm.model}` is not pulled")
    else:
        st.error("✗ Ollama not reachable on 127.0.0.1:11434 — rule-based mode only")
    if netguard.is_active():
        st.success("✓ Network guard active (loopback only)")
    else:
        st.warning("Network guard OFF")
    blocked = netguard.blocked_attempts()
    st.info(f"Blocked outbound attempts: **{len(blocked)}**")
    if blocked:
        with st.expander("Blocked attempts"):
            for b in blocked[-20:]:
                st.text(f"{b['time']} {b['via']} → {b['host']}:{b['port']}")
    emb_ok = _warm_embedder()
    st.caption(f"Embeddings: {'local bge-small ✓' if emb_ok else 'BM25 only (' + embedder_status() + ')'}")
    models = health.get("models") or [config.MODEL]
    st.selectbox("Model", models, index=models.index(llm.model) if llm.model in models else 0, key="model")
    doc_type_choice = st.selectbox("Document type", ["auto", "rental", "employment"],
                                   help="auto = detect from the text")
    st.divider()
    if st.button("🗑️ Clear document", use_container_width=True, help="Removes the document and results from memory"):
        clear_doc()
        st.rerun()
    st.caption("Session data is held in memory only. Nothing is uploaded or saved to disk.")

# ------------------------------------------------------------------ upload
up = st.file_uploader("Upload a rental/lease or employment agreement (PDF, DOCX or TXT, max 25 MB)",
                      type=["pdf", "docx", "txt"])
if up is not None:
    data = up.getvalue()
    h = hashlib.sha256(data).hexdigest()
    if st.session_state.get("doc_hash") != h:
        clear_doc()
        st.session_state.doc_hash = h
        try:
            doc = parse_bytes(up.name, data)
            st.session_state.doc = doc
            register_document(doc.text)
        except IngestError as e:
            st.session_state.error = e.message
        del data

if st.session_state.get("error"):
    st.error(f"⚠️ {st.session_state.error}")

doc = st.session_state.get("doc")
if doc is not None and "report" not in st.session_state:
    st.write(f"**{esc(doc.name)}** · {len(doc.pages)} page(s) · {len(doc.text):,} characters")
    for w in doc.warnings:
        st.warning(w)
    if st.button("🔍 Analyse document", type="primary"):
        t0 = time.perf_counter()
        with st.status("Analysing locally…", expanded=True) as status:
            bar = st.progress(0.0)
            log_area = st.empty()
            steps: list[str] = []
            last = [time.perf_counter()]

            def progress(stage: str, frac: float):
                now = time.perf_counter()
                if steps:
                    steps[-1] += f" — {now - last[0]:.1f}s"
                last[0] = now
                steps.append(stage)
                bar.progress(min(frac, 1.0), text=stage)
                log_area.markdown("\n".join(f"- {s}" for s in steps))

            report, chunks = Analyzer(llm).analyze(doc, doc_type_choice, progress)
            progress("Building search index", 0.98)
            index = HybridIndex(chunks)
            st.session_state.update(report=report, chunks=chunks, index=index, history=[],
                                    qa=QAEngine(doc, chunks, report.doc_type, llm, index, report.injection_flags,
                                                [f.value for f in report.facts]))
            status.update(label=f"Analysis complete in {time.perf_counter() - t0:.1f}s", state="complete", expanded=False)
        st.rerun()

report = st.session_state.get("report")
if report is None:
    if doc is None:
        st.info("Upload a document to begin. Try the files in `samples/`.")
    st.stop()

chunks = st.session_state.chunks
by_id = {c.id: c for c in chunks}


def show_finding(f, key: str):
    with st.container(border=True):
        st.markdown(f"**{render.SEVERITY_ICON[f.severity]} {esc(f.title)}**")
        st.caption(f"{render.SEVERITY_LABEL[f.severity]} severity · {render.KIND_LABEL[f.kind]} · "
                   f"Confidence: {render.confidence_label(f.confidence)} ({f.confidence:.2f}) · "
                   f"✓ Quote verified ({f.match_score:.0f}% match) · source: {f.source}")
        st.markdown(esc(f.plain_explanation))
        st.markdown(f"> **Document says (page {f.page}):** “{esc(f.quote)}”")
        if f.ambiguity_note:
            st.markdown(f"⚠️ **Unclear wording:** {esc(f.ambiguity_note)}")
        with st.expander(f"Show source passage · clause {f.chunk_id} · page {f.page}"):
            c = by_id.get(f.chunk_id)
            if c:
                st.markdown(f"<div style='white-space:pre-wrap;font-size:0.9em'>{highlight(c.text, f.quote)}</div>",
                            unsafe_allow_html=True)
        if f.needs_lawyer:
            st.markdown(f"⚖️ **Ask a lawyer about this:** bring the agreement, point to page {f.page}, and ask how this clause affects you.")


st.subheader(f"📄 {esc(report.doc_name)} — {report.doc_type} agreement")
for w in report.warnings:
    st.warning(w)
if report.injection_flags:
    st.error(f"🛡️ **Instruction-like text found in the document ({len(report.injection_flags)}).** "
             "It was treated as untrusted data and did not change the analysis. See the *Safety* tab.")

tabs = st.tabs(["Overview", "Top concerns", "Findings by category", "Missing & vague", "Ask", "Safety & privacy"])

with tabs[0]:
    st.markdown("#### Plain-language summary")
    st.markdown(esc(report.summary) if report.summary else "_Summary unavailable (local model not reachable)._")
    if report.summary_verified_quotes:
        st.markdown("**Key points (each backed by a verified quote):**")
        for f in report.summary_verified_quotes:
            st.markdown(f"- {esc(f.plain_explanation)}  \n  > “{esc(f.quote)}” — *page {f.page}*")
    st.markdown("#### Key facts (extracted by rules, verbatim)")
    fb = render.facts_by_type(report)
    cols = st.columns(3)
    for i, (ftype, items) in enumerate(fb.items()):
        with cols[i % 3]:
            st.markdown(f"**{render.FACT_LABELS.get(ftype, ftype)}**")
            for f in items[:8]:
                st.markdown(f"- {esc(f.value)} *(p.{f.page})*", help=f.quote[:300])
    if report.jurisdiction_notes:
        st.markdown("#### Jurisdiction-dependent")
        for n in report.jurisdiction_notes:
            st.info(f"📍 {n} *(general information, not a conclusion about this document)*")
    st.markdown("#### Stage timings")
    st.dataframe([{"stage": t.stage, "seconds": t.seconds} for t in report.timings], hide_index=True)

with tabs[1]:
    tc = render.top_concerns(report)
    if not tc:
        st.info("No high-severity points or concerns were identified. This does not mean the document is fine — "
                + disc["escalation"])
    for i, f in enumerate(tc):
        show_finding(f, f"tc{i}")

with tabs[2]:
    groups = render.by_category(report)
    if not groups:
        st.info("No verified findings.")
    for cat, items in groups.items():
        with st.expander(f"{label(cat)} ({len(items)})", expanded=False):
            for i, f in enumerate(items):
                show_finding(f, f"{cat}{i}")

with tabs[3]:
    st.markdown("#### Clauses you might expect but that were not found")
    if report.missing_clauses:
        for m in report.missing_clauses:
            st.markdown(f"- ❓ The document does not appear to mention **{esc(m)}**.")
        st.caption("Based on a checklist for this document type. A clause may exist under different wording.")
    else:
        st.write("All checklist items appear to be mentioned.")
    st.markdown("#### Vague or open-ended wording")
    if report.vague_terms:
        for v in report.vague_terms[:40]:
            st.markdown(f"- **“{esc(v.term)}”** (page {v.page}): “{esc(v.quote)}”")
        st.caption("These words can be interpreted in different ways. Consider asking what they mean in practice.")
    else:
        st.write("No vague terms from the list were found.")

with tabs[4]:
    st.caption("Answers come only from the document. Questions about legality or what you should do are escalated to a lawyer.")
    hist = st.session_state.setdefault("history", [])
    for a in hist:
        with st.chat_message("user"):
            st.write(a.question)
        with st.chat_message("assistant"):
            tag = {"document_fact": "📄 Document question", "legal_verdict": "⚖️ Needs a lawyer",
                   "out_of_scope": "🚫 Out of scope"}[a.qtype]
            st.caption(f"{tag} · {a.seconds:.1f}s")
            st.markdown(esc(a.answer))
            for c in a.citations:
                st.markdown(f"> “{esc(c.quote)}” — *page {c.page}, clause {c.chunk_id}* ✓ verified")
            if a.related:
                with st.expander("Closest related clauses"):
                    for r in a.related:
                        st.markdown(f"**Clause {r.id} · page {r.page}** — {esc(r.text[:500])}{'…' if len(r.text) > 500 else ''}")
            if a.general_info:
                st.info(f"**General information (not about your document, not legal advice):** {a.general_info}")
            if a.escalation:
                st.markdown(a.escalation)
    q = st.chat_input("Ask about this document, e.g. “What is the notice period?”")
    if q:
        with st.spinner("Thinking locally…"):
            hist.append(st.session_state.qa.ask(q))
        st.rerun()

with tabs[5]:
    st.markdown("#### Prompt-injection scan")
    if report.injection_flags:
        for f in report.injection_flags:
            st.markdown(f"- 🛡️ page {f.page}: “{esc(f.quote)}”")
        st.caption("These passages look like instructions to an AI. LexLocal removed them from what the model sees and kept them here for you to review.")
    else:
        st.write("No instruction-like text detected.")
    st.markdown("#### Privacy")
    st.markdown(f"- Model: `{report.model}` via Ollama on 127.0.0.1\n- Network guard: {'active' if netguard.is_active() else 'off'} · blocked attempts: {len(netguard.blocked_attempts())}\n"
                "- Document text is never written to disk or logs (log filter redacts any document text).\n"
                "- Click **Clear document** in the sidebar to remove everything from memory.")
    st.markdown(f"#### Verification\n{len(report.findings)} findings shown, all with verified verbatim quotes. "
                f"{len(report.rejected)} model claims were rejected or trimmed by the verifier/guardrails and are not shown.")

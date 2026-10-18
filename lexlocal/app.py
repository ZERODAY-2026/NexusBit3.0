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
from lexlocal.analysis import consistency  # noqa: E402
from lexlocal.analysis.analyzer import Analyzer  # noqa: E402
from lexlocal.analysis.qa import QAEngine  # noqa: E402
from lexlocal.extract import structured  # noqa: E402
from lexlocal.extract.categories import label  # noqa: E402
from lexlocal.ingest.parser import IngestError, parse_bytes  # noqa: E402
from lexlocal.llm.client import OllamaClient  # noqa: E402
from lexlocal.models import SEVERITY_ORDER, Kind, Severity  # noqa: E402
from lexlocal.privacy.vault import Vault  # noqa: E402
from lexlocal.privacy.logging_setup import clear_document, register_document, setup_logging  # noqa: E402
from lexlocal.report import export, render  # noqa: E402
from lexlocal.retrieval.index import HybridIndex, embedder_status, get_embedder  # noqa: E402
from lexlocal.ui import theme  # noqa: E402

setup_logging(config.LOG_LEVEL, config.LOG_DIR / "lexlocal.log")

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|$~])")


def esc(text: str) -> str:
    """Escape markdown so document text renders literally (and $ never triggers LaTeX)."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def show_text(text: str) -> None:
    """Show one of LexLocal's own explanations (escaped so document text renders literally)."""
    st.markdown(esc(text))


def highlight(passage: str, quote: str | list[str]) -> str:
    """HTML-escaped passage with each quote wrapped in <mark> (overlapping spans are merged)."""
    spans = []
    for q in [quote] if isinstance(quote, str) else quote:
        i = passage.find(q) if q else -1
        if i >= 0:
            spans.append((i, i + len(q)))
    out, pos = [], 0
    for s, e in sorted(spans):
        if s < pos:
            s = pos
        if s >= e:
            continue
        out += [html.escape(passage[pos:s]), "<mark>", html.escape(passage[s:e]), "</mark>"]
        pos = e
    return "".join(out) + html.escape(passage[pos:])


DOC_KEYS = ["pdf_report", "cmp_result", "cmp_key", "doc", "doc_bytes", "report", "chunks", "qa", "history", "doc_hash", "error", "index",
            "nav_clause", "nav_quote", "view"]
VIEWS = ["Overview", "Top concerns", "Worth asking about", "Findings by category", "Missing and vague", "Glossary", "Document", "Safety and privacy"]


def jump_to(chunk_id: str, quote: str | None = None):
    """Button callback: open the Document view at a clause (runs before widgets are rebuilt)."""
    st.session_state.view = "Document"
    st.session_state.nav_clause = chunk_id
    st.session_state.nav_quote = quote


def session_vault() -> Vault:
    """This browser session's encrypted scratch space (wiped with the document or when the session ends)."""
    v = st.session_state.get("vault")
    if v is None or not v.active:
        v = st.session_state.vault = Vault()
    return v


def clear_doc():
    for k in DOC_KEYS:
        st.session_state.pop(k, None)
    v = st.session_state.pop("vault", None)
    if v is not None and v.active:
        v.wipe()
    clear_document()
    gc.collect()


def panic_wipe():
    """Remove everything this session holds: document, results, history, vault, caches."""
    clear_doc()
    gen = st.session_state.get("upload_gen", 0) + 1  # a fresh uploader widget drops the uploaded file
    keep = {"splash_shown"}
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]
    st.session_state.upload_gen = gen
    st.cache_data.clear()
    gc.collect()
    st.session_state.wiped = True


# ------------------------------------------------------------------ page
ASSETS = config.ROOT / "lexlocal" / "ui" / "assets"
st.set_page_config(page_title="LexLocal", page_icon=str(ASSETS / "favicon.png"), layout="wide")
disc = knowledge.disclaimer("en")

st.markdown(theme.CSS, unsafe_allow_html=True)
if not st.session_state.get("splash_shown"):
    st.session_state.splash_shown = True
    st.markdown(theme.SPLASH, unsafe_allow_html=True)

st.markdown(
    "<div class='ll-masthead'><span class='ll-title'>LexLocal</span>"
    "<span class='ll-tag'>Runs entirely on your device &middot; Not legal advice</span></div>"
    f"<div class='ll-notice'>{html.escape(disc['disclaimer'])}</div>",
    unsafe_allow_html=True,
)

# Shown until the local models are ready (first start loads the embedding model, about 10 s), so the page
# never looks stuck. Cleared at the end of the sidebar status block below.
_loading = st.empty()
_loading.markdown(theme.loading_tag("Loading local models, please wait. The first start takes about 10-20 seconds."),
                  unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def _ocr_status():
    from lexlocal.ingest import ocr

    return ocr.available()


@st.cache_resource(show_spinner=False)
def _warm_embedder():
    return get_embedder() is not None


MODE = config.MODES[st.session_state.get("analysis_mode", "Thorough")]
llm = OllamaClient(model=st.session_state.get("model_override") or MODE["model"])

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("<div class='ll-serif' style='font-size:1.4rem'>LexLocal</div>", unsafe_allow_html=True)
    st.markdown("<div class='ll-meta' style='margin-bottom:6px'>Status</div>", unsafe_allow_html=True)
    health = llm.health()
    if health["ok"] and health["model_available"]:
        ollama_chip = theme.chip(f"Ollama local (127.0.0.1) &middot; {html.escape(llm.model)}", True)
    elif health["ok"]:
        ollama_chip = theme.chip(f"Ollama running, model {html.escape(llm.model)} not pulled", None)
    else:
        ollama_chip = theme.chip("Ollama not reachable: rule-based mode only", False)
    blocked = netguard.blocked_attempts()
    emb_ok = _warm_embedder()
    st.markdown(
        ollama_chip
        + theme.chip("Network guard active (loopback only)" if netguard.is_active() else "Network guard OFF",
                     True if netguard.is_active() else None)
        + theme.chip(f"Blocked outbound attempts: <b>{len(blocked)}</b>", not blocked),
        unsafe_allow_html=True)
    _loading.empty()  # models ready: remove the "please wait" tag
    if blocked:
        with st.expander("Blocked attempts"):
            for b in blocked[-20:]:
                st.text(f"{b['time']} {b['via']} -> {b['host']}:{b['port']}")
    st.radio("Analysis mode", list(config.MODES), key="analysis_mode", index=1, horizontal=True,
             help=" ".join(f"{k}: {v['help']}" for k, v in config.MODES.items()))
    st.caption(MODE["help"])
    models = health.get("models") or []
    if health["ok"] and llm.model not in models and models:
        st.warning(f"{llm.model} is not pulled. Pick an available model below or run `ollama pull {llm.model}`.")
    with st.expander("Use a different local model"):
        st.selectbox("Model", ["(mode default)"] + models, key="model_pick",
                     on_change=lambda: st.session_state.update(
                         model_override=None if st.session_state.model_pick == "(mode default)" else st.session_state.model_pick))
    doc_type_choice = st.selectbox("Document type", ["auto", "rental", "employment"],
                                   help="auto = detect from the text")
    mode = st.radio("Mode", ["Analyse a document", "Compare two versions"], key="mode")
    st.divider()
    if st.button("Delete document", width="stretch",
                 help="Removes the document, results and its encrypted temporary files from this session"):
        clear_doc()
        st.session_state.upload_gen = st.session_state.get("upload_gen", 0) + 1
        st.rerun()
    st.button("Panic wipe", width="stretch", type="primary", on_click=panic_wipe,
              help="Immediately removes everything this session holds, including chat history and settings")
    st.caption("Documents stay in memory. Temporary files (OCR only) are encrypted with a key that exists only in "
               "memory, and are wiped on delete, on panic wipe and when the session ends.")
    if st.session_state.pop("wiped", False):
        st.success("Everything from this session was wiped.")

if mode == "Compare two versions":
    from lexlocal.ui import compare_page

    compare_page.render(llm, session_vault(), esc)
    st.stop()

# ------------------------------------------------------------------ upload
def load_document(name: str, data: bytes) -> None:
    """Parse an uploaded file or pasted text into the session (memory only). Same path for both inputs."""
    h = hashlib.sha256(data).hexdigest()
    if st.session_state.get("doc_hash") == h:
        return
    clear_doc()
    st.session_state.doc_hash = h
    try:
        with st.spinner("Reading the document locally (scanned pages are read with local OCR, about 5 s per page)..."):
            doc = parse_bytes(name, data, vault=session_vault())
        st.session_state.doc = doc
        if doc.kind == "pdf":  # kept in memory only, for the highlighted page view
            st.session_state.doc_bytes = data
        register_document(doc.text)
    except IngestError as e:
        st.session_state.error = e.message


gen = st.session_state.get("upload_gen", 0)
source = st.radio("How do you want to add the agreement?", ["Upload a file", "Type or paste text"],
                  horizontal=True, key="input_source")
if source == "Upload a file":
    up = st.file_uploader("Upload a rental/lease or employment agreement (PDF, DOCX or TXT, max 25 MB)",
                          type=["pdf", "docx", "txt"], key=f"upload_{gen}")
    if up is not None:
        load_document(up.name, up.getvalue())
else:
    # A form submits the text and the button together (a plain button can arrive before the pasted text does).
    with st.form(f"paste_form_{gen}", border=False):
        pasted = st.text_area("Type or paste the agreement text", height=240, key=f"paste_{gen}",
                              placeholder="Paste the full text of the rental, lease or employment agreement here. "
                                          "It stays on this device.")
        submitted = st.form_submit_button("Use this text", type="primary")
    if submitted:
        if pasted.strip():
            load_document("pasted-agreement.txt", pasted.encode("utf-8"))
        else:
            st.warning("Type or paste the agreement text first.")

if st.session_state.get("error"):
    st.error(st.session_state.error)

doc = st.session_state.get("doc")
if doc is not None and "report" not in st.session_state:
    st.write(f"**{esc(doc.name)}** · {len(doc.pages)} page(s) · {len(doc.text):,} characters")
    for w in doc.warnings:
        st.warning(w)
    if st.button("Analyse document", type="primary"):
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

            report, chunks = Analyzer(llm, MODE["self_consistency"], MODE["pairwise"]).analyze(doc, doc_type_choice, progress)
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
findings_by_chunk: dict[str, list] = {}
for _f in report.findings:
    findings_by_chunk.setdefault(_f.chunk_id, []).append(_f)


def clause_severity(cid: str):
    fs = findings_by_chunk.get(cid)
    return min((f.severity for f in fs), key=lambda s: SEVERITY_ORDER[s]) if fs else None


def clause_label(c) -> str:
    sev = clause_severity(c.id)
    name = c.heading or c.text.strip().splitlines()[0][:60]
    return f"{render.SEVERITY_LABEL[sev] if sev else 'No findings'} · {c.id} · {name}"


def show_finding(f, key: str):
    with st.container(border=True):
        st.markdown(f"{theme.severity_badge(f.severity, render.SEVERITY_LABEL[f.severity])} "
                    f"<span class='ll-ftitle'>{html.escape(f.title)}</span>", unsafe_allow_html=True)
        st.caption(f"{render.SEVERITY_LABEL[f.severity]} severity · {render.KIND_LABEL[f.kind]} · "
                   f"Confidence: {render.confidence_label(f.confidence)} ({f.confidence:.2f}) · "
                   f"Quote verified ({f.match_score:.0f}% match) · source: {f.source}"
                   + (f" · OCR page confidence {f.signals['ocr']:.0%}" if "ocr" in f.signals else ""),
                   help=render.signals_text(f.signals))
        show_text(f.plain_explanation)
        st.markdown(f"> **Document says (page {f.page}):** “{esc(f.quote)}”")
        if f.ambiguity_note:
            st.markdown(f"**Unclear wording:** {esc(f.ambiguity_note)}")
        with st.expander(f"Show source passage · clause {f.chunk_id} · page {f.page}"):
            c = by_id.get(f.chunk_id)
            if c:
                st.markdown(f"<div style='white-space:pre-wrap;font-size:0.9em'>{highlight(c.text, f.quote)}</div>",
                            unsafe_allow_html=True)
        if f.needs_lawyer:
            st.markdown(f"**Ask a lawyer about this:** bring the agreement, point to page {f.page}, and ask how this clause affects you.")
        st.button("View in document", key=f"jump_{key}", on_click=jump_to, args=(f.chunk_id, f.quote))


# Clause outline in the sidebar: every clause with a text severity label; click to jump.
with st.sidebar:
    st.divider()
    st.markdown("<div class='ll-meta' style='margin-bottom:4px'>Clause outline</div>", unsafe_allow_html=True)
    with st.container(height=360, border=False):
        for c in chunks:
            st.button(clause_label(c), key=f"outline_{c.id}", on_click=jump_to, args=(c.id,),
                      width="stretch", type="tertiary")

st.subheader(f"{esc(report.doc_name)} — {report.doc_type} agreement")
for w in report.warnings:
    if report.adversarial and w.startswith("Content a reader would not see"):
        continue  # shown as the red banner below
    st.warning(w)
if report.injection_flags:
    st.error(f"**Instruction-like text found in the document ({len(report.injection_flags)}).** "
             "It was treated as untrusted data and did not change the analysis. See *Safety and privacy*.")
if report.adversarial:
    st.error(f"**Hidden or disguised content found ({len(report.adversarial)}).** Text a reader cannot see, invisible "
             "characters or look-alike letters were kept out of the analysis. See *Safety and privacy*.")
if report.conflicts:
    st.warning(f"**{len(report.conflicts)} place(s) in the document seem to disagree with each other.** See *Worth asking about*.")

exp1, exp2, _ = st.columns([1.3, 1.3, 4])
_stem = report.doc_name.rsplit(".", 1)[0]
exp1.download_button("Download Markdown", export.to_markdown(report).encode("utf-8"),
                     file_name=f"{_stem}-lexlocal.md", mime="text/markdown", width="stretch",
                     help="Built on this device, with citations and disclaimers. Saved by your browser.")
if exp2.button("Prepare PDF report", width="stretch") or "pdf_report" in st.session_state:
    if "pdf_report" not in st.session_state:
        st.session_state.pdf_report = export.to_pdf(report)
    exp2.download_button("Download PDF", st.session_state.pdf_report, file_name=f"{_stem}-lexlocal.pdf",
                         mime="application/pdf", width="stretch")

st.session_state.setdefault("view", "Overview")
view = st.segmented_control("View", VIEWS, key="view", label_visibility="collapsed") or "Overview"

if view == "Overview":
    st.markdown("#### Plain-language summary")
    if report.summary:
        show_text(report.summary)
    else:
        st.markdown("_Summary unavailable (local model not reachable)._")
    if report.summary_verified_quotes:
        st.markdown("**Key points (each backed by a verified quote):**")
        for f in report.summary_verified_quotes:
            st.markdown(f"- {esc(f.plain_explanation)}  \n  > “{esc(f.quote)}” — *page {f.page}*")
    st.markdown("#### Key terms")
    st.caption("Extracted by deterministic rules. Each value is shown with the exact sentence it comes from; "
               "click the page to see it in the document.")
    widths = [1.4, 1.9, 4.6, 0.9]
    head = st.columns(widths)
    for col, name in zip(head, ["Term", "Value", "Document says", "Source"]):
        col.markdown(f"<div class='ll-meta'>{name}</div>", unsafe_allow_html=True)
    rows_by_field: dict[str, list] = {}
    for kt in report.key_terms:
        rows_by_field.setdefault(kt.field, []).append(kt)
    for field in structured.FIELDS:
        items = rows_by_field.get(field, [])
        if not items and field not in structured.EXPECTED.get(report.doc_type, []):
            continue
        st.markdown("<hr style='margin:2px 0;border:none;border-top:1px solid #E7DFCC'>", unsafe_allow_html=True)
        if not items:
            c1, c2 = st.columns([widths[0], sum(widths[1:])])
            c1.markdown(f"**{field}**")
            c2.caption("Not found by the rules. The document may still cover it in other words; check *Missing and vague*.")
            continue
        for j, kt in enumerate(items):
            c1, c2, c3, c4 = st.columns(widths, vertical_alignment="center")
            c1.markdown(f"**{field}**" if j == 0 else "")
            c2.markdown(f"{esc(kt.value)}  \n<span class='ll-meta'>{html.escape(kt.label)}</span>", unsafe_allow_html=True)
            c3.markdown(f"<div style='font-size:0.86em;color:#5E574C'>“{highlight(kt.quote, kt.value)}”</div>",
                        unsafe_allow_html=True)
            if kt.chunk_id:
                c4.button(f"Page {kt.page}", key=f"kt_{field}_{j}", on_click=jump_to, args=(kt.chunk_id, kt.quote),
                          type="tertiary", help="Show in document")
            else:
                c4.caption(f"Page {kt.page}")
    with st.expander("All rule-extracted facts"):
        for ftype, items in render.facts_by_type(report).items():
            st.markdown(f"**{render.FACT_LABELS.get(ftype, ftype)}:** " + "; ".join(f"{esc(f.value)} (p.{f.page})" for f in items))
    if report.jurisdiction_items or report.jurisdiction.state:
        st.markdown("#### Depends on where you are")
        j = report.jurisdiction
        if j.state:
            st.markdown(f"The document points to **{esc(j.state)}**, based on its {j.basis}: “{esc(j.value)}” (page {j.page}). "
                        "Some rules below differ from state to state.")
        else:
            st.markdown("LexLocal could not tell which state's rules apply. Some topics below differ from state to state.")
        st.caption("General information, not a conclusion about this document. No legal limits are stated here on purpose.")
        for i, n in enumerate(report.jurisdiction_items):
            with st.container(border=True):
                st.markdown(f"<span class='ll-ftitle'>{html.escape(n.topic[0].upper() + n.topic[1:])}</span>",
                            unsafe_allow_html=True)
                st.markdown(esc(n.note))
                st.markdown(f"> **Mentioned on page {n.page}:** “{esc(n.quote)}”")
    st.markdown("#### Stage timings")
    st.dataframe([{"stage": t.stage, "seconds": t.seconds} for t in report.timings], hide_index=True)

if view == "Top concerns":
    tc = render.top_concerns(report)
    if not tc:
        st.info("No high-severity points or concerns were identified. This does not mean the document is fine — "
                + disc["escalation"])
    for i, f in enumerate(tc):
        show_finding(f, f"tc{i}")

if view == "Worth asking about":
    st.markdown("#### Places that seem to disagree")
    if report.conflicts:
        st.caption("Two parts of the document appear to say different things about the same matter. "
                   "This is not a conclusion about which one applies. Ask the other party, or a lawyer, to clarify.")
        for i, cf in enumerate(report.conflicts):
            with st.container(border=True):
                src = "found by rules" if cf.source == "rules" else "found by the local model, both quotes verified"
                st.markdown(f"{theme.badge('Conflict', theme.SEVERITY_COLOR[Severity.medium])} "
                            f"<span class='ll-ftitle'>{html.escape(cf.title)}</span>", unsafe_allow_html=True)
                st.caption(src)
                st.markdown(esc(cf.explanation))
                qa_col, qb_col = st.columns(2) if cf.quote_b else (st.container(), None)
                with qa_col:
                    st.markdown(f"> **Page {cf.page_a}:** “{esc(cf.quote_a)}”")
                    if cf.chunk_a:
                        st.button("View in document", key=f"cfa_{i}", on_click=jump_to, args=(cf.chunk_a, cf.quote_a))
                if qb_col is not None:
                    with qb_col:
                        st.markdown(f"> **Page {cf.page_b}:** “{esc(cf.quote_b)}”")
                        if cf.chunk_b:
                            st.button("View in document", key=f"cfb_{i}", on_click=jump_to, args=(cf.chunk_b, cf.quote_b))
    else:
        st.write("No contradictions were detected by the checks LexLocal runs. That does not guarantee there are none.")
    st.markdown("#### One-sided or unusual wording")
    if report.unusual:
        st.caption("Worth asking about. These flags describe the wording, not whether a clause is valid or fair.")
        for i, u in enumerate(report.unusual):
            with st.container(border=True):
                basis = {"asymmetric notice": "Asymmetric terms", "one-sided wording": "One-sided wording",
                         "atypical wording": "Atypical wording"}[u.basis]
                st.markdown(f"{theme.badge(basis)} <span class='ll-ftitle'>{html.escape(u.title)}</span>",
                            unsafe_allow_html=True)
                st.markdown(esc(u.explanation))
                st.markdown(f"> **Page {u.page}:** “{esc(u.quote)}”")
                if u.quote_b:
                    st.markdown(f"> **Page {u.page_b}:** “{esc(u.quote_b)}”")
                if u.similarity is not None:
                    st.caption(f"Similarity to the closest typical clause: {u.similarity:.2f} (flagged below {consistency.ATYPICAL_THRESHOLD})")
                if u.chunk_id:
                    st.button("View in document", key=f"un_{i}", on_click=jump_to, args=(u.chunk_id, u.quote))
    else:
        st.write("No one-sided or unusual wording was flagged.")

if view == "Findings by category":
    groups = render.by_category(report)
    if not groups:
        st.info("No verified findings.")
    for cat, items in groups.items():
        with st.expander(f"{label(cat)} ({len(items)})", expanded=False):
            for i, f in enumerate(items):
                show_finding(f, f"{cat}{i}")

if view == "Missing and vague":
    st.markdown("#### Clauses you might expect but that were not found")
    if report.missing_clauses:
        for m in report.missing_clauses:
            st.markdown(f"- The document does not appear to mention **{esc(m)}**.")
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

if view == "Glossary":
    st.markdown("#### Legal terms in this document")
    st.caption("General meanings, not legal advice. How a term applies depends on the exact wording and the law.")
    if not report.glossary:
        st.write("No terms from the glossary were found.")
    for g in report.glossary:
        with st.container(border=True):
            src = "" if g.source == "glossary" else (" " + theme.badge("Explained by the local model"))
            st.markdown(f"<span class='ll-ftitle'>{html.escape(g.term)}</span>{src}", unsafe_allow_html=True)
            show_text(g.definition)
            st.markdown(f"> **In this document (page {g.page}):** “{esc(g.example)}”")

if view == "Document":
    ids = [c.id for c in chunks]
    if st.session_state.get("nav_clause") not in ids:
        st.session_state.nav_clause = ids[0]
    nav_a, nav_b, nav_c = st.columns([6, 1, 1], vertical_alignment="bottom")
    with nav_a:
        cid = st.selectbox("Clause", ids, key="nav_clause", format_func=lambda i: clause_label(by_id[i]),
                           on_change=lambda: st.session_state.update(nav_quote=None))
    pos = ids.index(cid)
    nav_b.button("Previous", disabled=pos == 0, width="stretch",
                 on_click=jump_to, args=(ids[max(pos - 1, 0)],))
    nav_c.button("Next", disabled=pos == len(ids) - 1, width="stretch",
                 on_click=jump_to, args=(ids[min(pos + 1, len(ids) - 1)],))
    c = by_id[cid]
    cf = findings_by_chunk.get(cid, [])
    focus = st.session_state.get("nav_quote")
    quotes = [focus] if focus else [f.quote for f in cf]
    pdf = st.session_state.get("doc_bytes")
    left, right = st.columns([1, 1]) if pdf else (st.container(), None)
    with left:
        st.markdown(f"<div class='ll-meta'>Clause {html.escape(c.id)} · page {c.page}"
                    f"{' · highlighted: the selected quote' if focus else ''}</div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(f"<div style='white-space:pre-wrap;font-size:0.93em;line-height:1.55'>{highlight(c.text, quotes)}</div>",
                        unsafe_allow_html=True)
        if cf:
            st.markdown(f"**Findings in this clause ({len(cf)})**")
            for f in cf:
                st.markdown(f"{theme.severity_badge(f.severity, render.SEVERITY_LABEL[f.severity])} "
                            f"{html.escape(f.title)}", unsafe_allow_html=True)
                st.caption(f.plain_explanation)
        else:
            st.caption("No verified findings point to this clause. That is not a guarantee it is unimportant.")
    if right is not None:
        with right:
            from lexlocal.report.pdfview import render_page

            page_no = next((f.page for f in cf if f.quote == focus), c.page)
            png, found = render_page(pdf, page_no, quotes)
            if quotes and not found and page_no < len(doc.pages):  # clause may continue on the next page
                png2, found2 = render_page(pdf, page_no + 1, quotes)
                if found2:
                    png, found, page_no = png2, found2, page_no + 1
            st.markdown(f"<div class='ll-meta'>Original PDF · page {page_no} of {len(doc.pages)}"
                        f"{f' · {found} quote(s) highlighted' if quotes else ''}</div>", unsafe_allow_html=True)
            st.image(png, width="stretch")
            if quotes and not found:
                st.caption("The quote could not be located on the page image (PDF text layout), "
                           "but it was verified against the extracted text.")
    if doc.kind != "pdf":
        st.caption("Page images are available for PDF uploads. For DOCX and TXT the clause text is shown with the quote highlighted.")

if view == "Safety and privacy":
    st.markdown("#### Hidden or disguised content")
    if report.adversarial:
        st.caption("A reader would not see this content, but a computer reading the file would. LexLocal removed hidden "
                   "text before analysis, stripped invisible characters and normalised look-alike letters. "
                   "Ask whoever sent the document why it is there.")
        for a in report.adversarial:
            with st.container(border=True):
                st.markdown(f"{theme.badge(a.kind.capitalize(), theme.SEVERITY_COLOR[Severity.high])} "
                            f"<span class='ll-meta'>page {a.page}</span>", unsafe_allow_html=True)
                st.markdown(esc(a.detail))
                if a.text and a.kind == "hidden text":
                    st.markdown(f"> “{esc(a.text)}”")
    else:
        st.write("No hidden text, invisible characters or look-alike letters were found.")
    st.markdown("#### Prompt-injection scan")
    if report.injection_flags:
        for f in report.injection_flags:
            st.markdown(f"- Page {f.page}: “{esc(f.quote)}”")
        st.caption("These passages look like instructions to an AI. LexLocal removed them from what the model sees and kept them here for you to review.")
    else:
        st.write("No instruction-like text detected.")
    st.markdown("#### Privacy")
    st.markdown(f"- Model: `{report.model}` via Ollama on 127.0.0.1\n- Network guard: {'active' if netguard.is_active() else 'off'} · blocked attempts: {len(netguard.blocked_attempts())}\n"
                "- Document text is never written to disk or logs (log filter redacts any document text).\n"
                "- **Delete document** removes it from memory; **Panic wipe** removes everything this session holds.")
    v = st.session_state.get("vault")
    st.markdown(f"- Encrypted temporary store: {'active, ' + str(len(v.files())) + ' encrypted file(s)' if v is not None and v.active else 'empty (nothing written to disk)'}.")
    st.markdown(f"#### Verification\n{len(report.findings)} findings shown, all with verified verbatim quotes. "
                f"{len(report.rejected)} model claims were rejected or trimmed by the verifier/guardrails and are not shown.")

# ------------------------------------------------------------------ follow-up questions (shown under every view)
st.divider()
st.markdown("#### Follow-up questions")
st.caption("Ask anything about this agreement. Answers come only from the document, with verified quotes. "
           "If the document doesn't say, LexLocal tells you. Questions about legality or what you should do get "
           "a specific lawyer referral instead of a verdict.")
hist = st.session_state.setdefault("history", [])


def ask(question: str) -> None:
    with st.spinner("Answering locally..."):
        hist.append(st.session_state.qa.ask(question))


if not hist:
    examples = (["What is the monthly rent and when is it due?", "How much notice do I need to give to leave?",
                 "When will I get my deposit back?", "Can I keep a pet?"] if report.doc_type != "employment" else
                ["What is my notice period?", "How many days of paid leave do I get?",
                 "What happens if I resign early?", "Can I work from home?"])
    cols = st.columns(len(examples))
    for col, ex in zip(cols, examples):
        if col.button(ex, width="stretch", type="tertiary", key=f"ex_{ex}"):
            ask(ex)
            st.rerun()
for a in hist:
    with st.chat_message("user", avatar=str(ASSETS / "avatar_user.png")):
        st.write(a.question)
    with st.chat_message("assistant", avatar=str(ASSETS / "avatar_assistant.png")):
        tag = {"document_fact": "From the document", "legal_verdict": "Needs a lawyer",
               "out_of_scope": "Out of scope"}[a.qtype]
        st.caption(f"{tag} · answered in {a.seconds:.1f}s")
        st.markdown(esc(a.answer))
        for c in a.citations:
            st.markdown(f"> “{esc(c.quote)}” — *page {c.page}, clause {c.chunk_id}* · verified")
        if a.related:
            with st.expander("Closest related clauses"):
                for r in a.related:
                    st.markdown(f"**Clause {r.id} · page {r.page}** — {esc(r.text[:500])}{'…' if len(r.text) > 500 else ''}")
        if a.general_info:
            st.info(f"**General information (not about your document, not legal advice):** {a.general_info}")
        if a.escalation:
            st.markdown(a.escalation)

# Top-level chat input: Streamlit pins it to the bottom of the page, so it is always within reach.
q = st.chat_input("Ask a follow-up question about this agreement, e.g. “What is the notice period?”")
if q and q.strip():
    ask(q.strip())
    st.rerun()

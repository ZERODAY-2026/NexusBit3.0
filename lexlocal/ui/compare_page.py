"""Two-version comparison page."""
from __future__ import annotations

import html
import time

import streamlit as st

from lexlocal.analysis.compare import compare
from lexlocal.ingest.parser import IngestError, parse_bytes
from lexlocal.ui import theme

STATUS_COLOR = {"modified": "#A86412", "added": "#3F6E4A", "removed": "#9B2C2C"}
STATUS_LABEL = {"modified": "Changed", "added": "Added", "removed": "Removed"}
DIFF_CSS = """<style>
.ll-diff { white-space: pre-wrap; font-size: 0.92em; line-height: 1.6; }
.ll-diff del { background: #F6E1DC; color: #7A2E2E; text-decoration: line-through; padding: 0 2px; }
.ll-diff ins { background: #E3EEDD; color: #2F5538; text-decoration: none; padding: 0 2px; }
</style>"""


def render(llm, vault, esc) -> None:
    st.markdown("#### Compare two versions")
    st.caption("Upload the earlier and the revised version of the same agreement. LexLocal lines up the clauses "
               "(even if they were renumbered), shows exactly which words changed, and points out changes to money, "
               "dates, time periods, termination, penalties and the deposit.")
    gen = st.session_state.get("upload_gen", 0)
    c1, c2 = st.columns(2)
    old_up = c1.file_uploader("Earlier version", type=["pdf", "docx", "txt"], key=f"cmp_old_{gen}")
    new_up = c2.file_uploader("Revised version", type=["pdf", "docx", "txt"], key=f"cmp_new_{gen}")
    if not (old_up and new_up):
        st.info("Try samples/rental_clean.txt and samples/rental_clean_v2.txt.")
        return
    key = (old_up.name, old_up.size, new_up.name, new_up.size)
    if st.session_state.get("cmp_key") != key:
        st.session_state.pop("cmp_result", None)
    if "cmp_result" not in st.session_state:
        if not st.button("Compare", type="primary"):
            return
        try:
            with st.spinner("Comparing locally..."):
                t0 = time.perf_counter()
                old = parse_bytes(old_up.name, old_up.getvalue(), vault=vault)
                new = parse_bytes(new_up.name, new_up.getvalue(), vault=vault)
                changes = compare(old, new, llm)
                st.session_state.cmp_result = (old.name, new.name, changes, time.perf_counter() - t0)
                st.session_state.cmp_key = key
        except IngestError as e:
            st.error(e.message)
            return
    old_name, new_name, changes, secs = st.session_state.cmp_result
    shown = [c for c in changes if c.status != "unchanged"]
    material = [c for c in shown if c.material]
    counts = {s: sum(c.status == s for c in changes) for s in ("modified", "added", "removed", "unchanged")}
    st.markdown(f"**{esc(old_name)}** compared with **{esc(new_name)}** in {secs:.1f} s: "
                f"{counts['modified']} changed, {counts['added']} added, {counts['removed']} removed, "
                f"{counts['unchanged']} unchanged clauses. **{len(material)}** change(s) touch money, dates, periods, "
                "termination, penalties or the deposit.")
    only_material = st.toggle("Show only those changes", value=bool(material))
    st.markdown(DIFF_CSS, unsafe_allow_html=True)
    for c in (material if only_material else shown):
        with st.container(border=True):
            tags = " ".join(theme.badge(m) for m in c.material)
            where = (f"was clause {c.old_id}, page {c.old_page}" if c.status == "removed" else
                     f"clause {c.new_id}, page {c.new_page}" + (f" (was {c.old_id})" if c.old_id and c.old_id != c.new_id else ""))
            st.markdown(f"{theme.badge(STATUS_LABEL[c.status], STATUS_COLOR[c.status])} {tags} "
                        f"<span class='ll-meta'>{html.escape(where)}</span>", unsafe_allow_html=True)
            if c.status == "modified":
                st.markdown(f"<div class='ll-diff'>{c.diff_html}</div>", unsafe_allow_html=True)
                st.caption(f"Word changes: {c.summary}")
                if c.explanation:
                    st.markdown(f"**What this means (local model, both quotes verified):** {esc(c.explanation)}")
                    q1, q2 = st.columns(2)
                    q1.markdown(f"> **Earlier:** “{esc(c.quote_old)}”")
                    q2.markdown(f"> **Revised:** “{esc(c.quote_new)}”")
            else:
                text = c.new_text if c.status == "added" else c.old_text
                cls = "ins" if c.status == "added" else "del"
                st.markdown(f"<div class='ll-diff'><{cls}>{html.escape(text)}</{cls}></div>", unsafe_allow_html=True)
    st.caption("This shows what changed in the wording. It does not say whether a change is acceptable, legal or fair. "
               "For a decision, ask a lawyer to review both versions.")

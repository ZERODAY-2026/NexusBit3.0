# Decisions log

| # | Decision | Why | Alternatives considered |
|---|---|---|---|
| D1 | **Python 3.13** venv instead of the planned 3.11 | Only 3.13 was installed on the dev machine, and all dependencies ship 3.13 wheels. Setup scripts accept ≥ 3.11 | Installing 3.11 would have cost time and gained nothing |
| D2 | **CPU torch** even though an RTX 2050 is present | bge-small embeds a whole agreement in well under a second on CPU. The CUDA wheel is ~2.5 GB, and the GPU is better left to Ollama | CUDA torch |
| D3 | Default model **gemma4:e4b** | Benchmarked at 14.4 tok/s, above the 8 tok/s threshold. Better at following schemas and picking quotes | E2B (65 tok/s) is the configurable fast option |
| D4 | **One LLM call per category** with ≤3 clauses (~3.5k chars) | Keeps each prompt under ~1.5k tokens: faster, more focused, and the model is less likely to mix clauses | Whole-document prompt (slow, unfocused, larger quote-hallucination surface); per-clause calls (too many calls) |
| D5 | **Verifier snaps quotes to the real span** | Even a fuzzy-accepted quote is displayed as verbatim document text, so model text can never appear as a quote | Showing the model's quote when it is "close enough" |
| D6 | Fuzzy threshold **partial_ratio ≥ 90 with ≥ 85% coverage** | Tolerates PDF extraction noise (hyphenation, ligatures, spacing) but rejects paraphrases. Tests cover typos, paraphrase and fabrication | Exact only (too brittle for PDFs) |
| D7 | **Numbers in explanations must be grounded** | Sentences with digits not present in the quote or rule-extracted facts are removed, which stops invented amounts and dates | Trusting the model |
| D8 | **Verdict scrubber** on all model text | A defence in depth, alongside the prompt rule, against "this clause is illegal/unenforceable/fair" | Prompt-only |
| D9 | **Rules first, then LLM** for question classification | Verdict and out-of-scope questions are caught with high precision and no latency, and the LLM handles the rest. If the LLM is down, the default is `document_fact`, which is safe because answers still need verified quotes | LLM-only |
| D10 | Silent answers need a **topic-overlap check** | Stops answers like "pets aren't allowed" being drawn from a "residential use only" clause. If no salient question term (or synonym) appears in the cited quotes, the answer becomes "The document is silent on this" | Trusting `found=true` |
| D11 | **Injection: flag + remove before the model sees it** | Removing the text, the delimiters and the system prompt each work independently. The user still sees the flagged text | Flag-only |
| D12 | **One-sided wording upgrades a finding to CONCERN** (from `one_sided_patterns.json`) | Gemma tended to label everything "explicit", so a deterministic rule makes labelling consistent | Prompt-only |
| D13 | **Global de-duplication** of findings by quote overlap; the stronger severity or concern wins | Otherwise the same clause appears under 3–4 categories | Per-category de-duplication |
| D14 | **Rule-based fallback findings** (amounts, notice periods) | Useful output when Ollama is down, and they fill recall gaps; marked `source: rules` | No fallback |
| D15 | **netguard** patches Python sockets in-process | Simple and testable, and catches every library using Python networking. Limitations are documented in PRIVACY.md | OS firewall rules (not portable); Docker `--network none` (Phase 2) |
| D16 | Knowledge-file loaders accept a plain list **or** `{"_placeholder": true, "items": [...]}`, and fall back to built-in defaults | Teammate files may be missing or partial, and the app must never crash on them | Strict schema |
| D17 | DOCX/TXT "pages" are ~3,000-character sections | These formats have no fixed pagination. The UI notes this | Reporting no page |
| D18 | Root `app.py` is a thin launcher for `lexlocal/app.py` | Keeps the empty `app.py` stub from the initial commit as the entry point (`streamlit run app.py`) | Moving the entry point |
| D19 | `dateparser` is pinned but not used yet | It is reserved for normalizing dates in the Phase 2 structured extraction table | Remove it |

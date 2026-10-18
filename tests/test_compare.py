from lexlocal.analysis import compare
from lexlocal.ingest.parser import parse_file
from tests.conftest import SAMPLES


def changes():
    return compare.compare(parse_file(SAMPLES / "rental_clean.txt"), parse_file(SAMPLES / "rental_clean_v2.txt"))


def by_status(cs, s):
    return [c for c in cs if c.status == s]


def test_alignment_survives_renumbering():
    cs = changes()
    assert len(by_status(cs, "added")) == 1 and "pets" in by_status(cs, "added")[0].new_text.lower()
    assert len(by_status(cs, "removed")) == 1 and "inspect" in by_status(cs, "removed")[0].old_text.lower()
    assert len(by_status(cs, "unchanged")) >= 12


def test_material_changes_flagged():
    mod = {c.old_id: c for c in by_status(changes(), "modified")}
    rent = next(c for c in mod.values() if "28,000" in c.new_text)
    assert "money" in rent.material and '"25,000/-" became "28,000/-"' in rent.summary
    late = next(c for c in mod.values() if "late fee" in c.new_text)
    assert {"money", "penalties"} <= set(late.material)
    refund = next(c for c in mod.values() if "60 days" in c.new_text)
    assert "time periods" in refund.material
    notice = next(c for c in mod.values() if "two months' prior written notice" in c.new_text)
    assert "termination or notice" in notice.material


def test_word_diff_marks_and_escapes():
    html, ch, _ = compare.word_diff("pay Rs. 500 <weekly>", "pay Rs. 1,000 <daily>")
    assert "<del>500 &lt;weekly&gt;</del>" in html and "<ins>1,000 &lt;daily&gt;</ins>" in html


def test_identical_documents_have_no_changes():
    d = parse_file(SAMPLES / "rental_clean.txt")
    assert all(c.status == "unchanged" for c in compare.compare(d, d))


def test_model_explanation_needs_verified_quotes(fake_llm_cls):
    good = {"explanation": "The monthly rent goes up from Rs. 25,000 to Rs. 28,000. This change is illegal.",
            "quote_old": "monthly rent of Rs. 25,000/-", "quote_new": "monthly rent of Rs. 28,000/-"}
    cs = compare.compare(parse_file(SAMPLES / "rental_clean.txt"), parse_file(SAMPLES / "rental_clean_v2.txt"),
                         fake_llm_cls({"ChangeOut": lambda u: good}), max_explanations=1)
    rent = next(c for c in cs if c.status == "modified" and "28,000" in c.new_text)
    assert rent.explanation and "illegal" not in rent.explanation
    assert rent.quote_old.startswith("monthly rent of Rs. 25,000") and rent.quote_old in rent.old_text
    bad = dict(good, quote_new="monthly rent of Rs. 30,000/- payable weekly")
    cs = compare.compare(parse_file(SAMPLES / "rental_clean.txt"), parse_file(SAMPLES / "rental_clean_v2.txt"),
                         fake_llm_cls({"ChangeOut": lambda u: bad}), max_explanations=1)
    assert not any(c.explanation for c in cs)

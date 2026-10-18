from lexlocal.analysis import confidence
from lexlocal.models import Fact, Finding, Kind


def F(**kw):
    base = dict(category="payments", title="t", plain_explanation="Rent is Rs. 25,000 a month.", quote="q",
                chunk_id="c1", page=1, match_score=100.0)
    return Finding(**{**base, **kw})


def test_more_agreeing_signals_give_higher_confidence():
    strong = confidence.combine({"match": 1.0, "agreement": 1.0, "category": 1.0, "consistency": 1.0}, Kind.explicit)
    weak = confidence.combine({"match": 0.9, "agreement": 0.5, "category": 0.4, "consistency": 0.0}, Kind.explicit)
    assert strong > weak
    assert confidence.label(strong) == "High" and confidence.label(weak) == "Low"


def test_missing_signals_are_ignored_not_zero():
    assert confidence.combine({"match": 1.0, "category": 1.0}, Kind.explicit) == 1.0


def test_ocr_confidence_downgrades():
    s = {"match": 1.0, "category": 1.0}
    assert confidence.combine({**s, "ocr": 0.4}, Kind.explicit) < confidence.combine(s, Kind.explicit)


def test_rule_llm_agreement_signal():
    fact = Fact(type="amount", value="Rs. 25,000/-", quote="", page=1, start=10, end=22)
    s = confidence.signals_for(F(), 0, 50, [fact], ["payments"])
    assert s["agreement"] == 1.0 and s["category"] == 1.0
    s = confidence.signals_for(F(plain_explanation="You pay rent monthly."), 0, 50, [fact], ["notice"])
    assert s["agreement"] == 0.5 and s["category"] == 0.4
    assert "agreement" not in confidence.signals_for(F(), 0, 5, [fact], [])  # no fact inside the quote

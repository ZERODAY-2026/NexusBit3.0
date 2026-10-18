"""Full offline pipeline against the real local Gemma, with netguard in strict mode.

    pytest -m needs_ollama
"""
import pytest

from lexlocal.analysis.analyzer import Analyzer
from lexlocal.analysis.qa import QAEngine
from lexlocal.ingest.parser import parse_file
from lexlocal.llm.client import OllamaClient
from lexlocal.privacy import netguard
from tests.conftest import SAMPLES

pytestmark = pytest.mark.needs_ollama


@pytest.fixture(scope="module")
def pipeline():
    netguard.install()
    netguard.reset_counter()
    llm = OllamaClient()
    if not llm.health().get("model_available"):
        pytest.skip(f"model {llm.model} not pulled")
    doc = parse_file(SAMPLES / "rental_clean.txt")
    report, chunks = Analyzer(llm).analyze(doc, "auto")
    qa = QAEngine(doc, chunks, report.doc_type, llm, injection_flags=report.injection_flags,
                  fact_values=[f.value for f in report.facts])
    yield doc, report, qa
    netguard.uninstall()


def test_full_pipeline_verified(pipeline):
    doc, report, _ = pipeline
    assert report.summary
    assert len(report.findings) >= 4
    assert all(f.verified and f.quote in doc.text for f in report.findings)
    assert netguard.blocked_attempts() == []  # nothing even tried to leave the machine


def test_pet_question_silent(pipeline):
    _, _, qa = pipeline
    assert qa.ask("Can I keep a pet?").silent


def test_enforceable_escalates(pipeline):
    _, _, qa = pipeline
    a = qa.ask("Is this enforceable?")
    assert a.qtype == "legal_verdict" and a.escalation


def test_fact_question(pipeline):
    _, _, qa = pipeline
    a = qa.ask("What is the monthly rent?")
    assert not a.silent and any("25,000" in c.quote for c in a.citations)

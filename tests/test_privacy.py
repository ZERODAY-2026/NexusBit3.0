import logging
import socket
import threading

import pytest

from lexlocal.llm.client import LLMError, OllamaClient
from lexlocal.privacy import netguard
from lexlocal.privacy.logging_setup import DocTextFilter, clear_document, register_document


@pytest.fixture
def guard():
    netguard.install()
    netguard.reset_counter()
    yield
    netguard.uninstall()


def test_netguard_blocks_external_ip(guard):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(PermissionError):
        s.connect(("93.184.216.34", 80))
    s.close()
    assert netguard.blocked_attempts()[-1]["host"] == "93.184.216.34"


def test_netguard_blocks_dns(guard):
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises((socket.gaierror, PermissionError, OSError)):
        socket.create_connection(("huggingface.co", 443), timeout=2)
    assert len(netguard.blocked_attempts()) >= 2


def test_netguard_blocks_requests_library(guard):
    import requests

    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get("https://example.com", timeout=3)


def test_netguard_allows_loopback(guard):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    t = threading.Thread(target=lambda: srv.accept()[0].close())
    t.start()
    c = socket.create_connection(("127.0.0.1", port), timeout=2)
    c.close()
    t.join(2)
    srv.close()
    assert netguard.blocked_attempts() == []


def test_llm_client_refuses_remote_host():
    with pytest.raises(LLMError):
        OllamaClient(base_url="http://api.example.com:11434")


def test_logging_filter_redacts_document_text(clean_doc):
    register_document(clean_doc.text)
    f = DocTextFilter()
    leak = logging.LogRecord("lexlocal", logging.INFO, __file__, 1, "parsed: %s",
                             ("The Tenant shall pay a monthly rent of Rs. 25,000/- (Rupees Twenty Five Thousand only) to the Landlord",), None)
    f.filter(leak)
    assert "REDACTED" in leak.getMessage() and "25,000" not in leak.getMessage()
    ok = logging.LogRecord("lexlocal", logging.INFO, __file__, 1, "llm call in_tok=%d out_tok=%d", (812, 120), None)
    f.filter(ok)
    assert ok.getMessage() == "llm call in_tok=812 out_tok=120"
    clear_document()


def test_pipeline_logs_contain_no_doc_text(clean_doc, caplog, fake_llm_cls):
    from lexlocal.analysis.analyzer import Analyzer

    caplog.set_level(logging.DEBUG, logger="lexlocal")
    Analyzer(fake_llm_cls()).analyze(clean_doc, "auto")
    logged = " ".join(r.getMessage() for r in caplog.records)
    for phrase in ["Ramesh Kumar", "Lakeview Apartments", "monthly rent of Rs", "Jayanagar"]:
        assert phrase not in logged

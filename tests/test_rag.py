from pathlib import Path

import pytest

from backend.rag.generate_policies import generate_knowledge_pdfs
from backend.rag.ingestion import ingest_pdf
from backend.rag.retriever import retrieve_policy


@pytest.fixture(scope="module")
def indexed_policies():
    kb = Path(__file__).resolve().parents[1] / "knowledge_base"
    generate_knowledge_pdfs(kb)
    result = ingest_pdf(kb / "refund_policy.pdf")
    if not result.get("ok"):
        pytest.skip("Could not index policies (embeddings unavailable).")
    ingest_pdf(kb / "escalation_policy.pdf")
    ingest_pdf(kb / "shipping_policy.pdf")
    return True


def test_refund_delay_retrieval(indexed_policies):
    result = retrieve_policy("When can a customer request a refund for delayed delivery?")
    assert result.get("ok") is True
    docs = [s["document"] for s in result.get("sources", [])]
    assert "refund_policy.pdf" in docs
    assert "5" in result.get("answer_context", "")


def test_high_value_policy_retrieval(indexed_policies):
    result = retrieve_policy("What happens for an 80000 rupee refund request?")
    docs = [s["document"] for s in result.get("sources", [])]
    combined = " ".join(docs) + result.get("answer_context", "")
    assert "escalation_policy.pdf" in docs or "refund_policy.pdf" in docs
    assert "50,000" in combined or "80000" in combined or "80,000" in combined or "high-value" in combined.lower()


def test_missing_policy_query(indexed_policies):
    result = retrieve_policy("What is the lunar mining subsidy for drones?")
    assert result.get("ok") is True
    context = result.get("answer_context") or ""
    assert "lunar mining" not in context.lower()

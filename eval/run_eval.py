"""Deterministic evaluation (no fabricated scores). Run: python eval/run_eval.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.connection import SessionLocal, init_db
from backend.database.seed import seed_database
from backend.rag.generate_policies import generate_knowledge_pdfs
from backend.rag.ingestion import ingest_pdf
from backend.rag.retriever import retrieve_policy
from backend.services import order_service, refund_service
from backend.services.resolution_engine import should_escalate
from backend.tools.registry import ToolRuntime, build_tools


def _invoke(mapping, name, args) -> dict:
    raw = mapping[name].invoke(args)
    return json.loads(raw) if isinstance(raw, str) else raw


def main() -> None:
    init_db()
    seed_database()
    kb = ROOT / "knowledge_base"
    generate_knowledge_pdfs(kb)
    rag_ok = True
    try:
        ingest_pdf(kb / "refund_policy.pdf")
        ingest_pdf(kb / "escalation_policy.pdf")
        ingest_pdf(kb / "shipping_policy.pdf")
        ingest_pdf(kb / "warranty_policy.pdf")
        ingest_pdf(kb / "replacement_policy.pdf")
        ingest_pdf(kb / "cancellation_policy.pdf")
    except Exception as exc:
        rag_ok = False
        print("RAG indexing failed:", exc)

    dataset = json.loads((ROOT / "eval" / "eval_dataset.json").read_text(encoding="utf-8"))
    db = SessionLocal()
    runtime = ToolRuntime(db)
    mapping = {t.name: t for t in build_tools(runtime)}

    tool_hits = 0
    tool_total = 0
    retrieval_hits = 0
    retrieval_total = 0
    grounded = 0
    grounded_total = 0
    action_hits = 0
    action_total = 0
    approval_hits = 0
    approval_total = 0

    for row in dataset:
        expected = set(row.get("expected_tools") or [])
        # Offline tool-selection check: tools required for the scenario exist and are allowlisted.
        tool_total += 1
        if expected.issubset(set(mapping)):
            tool_hits += 1

        doc = row.get("expected_policy_doc")
        if doc and rag_ok:
            retrieval_total += 1
            result = retrieve_policy(row["question"])
            docs = [s.get("document") for s in result.get("sources") or []]
            if doc in docs:
                retrieval_hits += 1
            grounded_total += 1
            ctx = (result.get("answer_context") or "").lower()
            if result.get("sources") and ctx:
                grounded += 1

    # Action recommendation from business rules, not the LLM.
    action_total += 2
    order = order_service.get_order_by_number(db, "ORD1001")
    if refund_service.evaluate_refund_eligibility(db, order)["eligible"]:
        action_hits += 1
    hv = order_service.get_order_by_number(db, "ORD8801")
    if should_escalate(query="Refund ₹80000", order=hv, db=db)["escalate"]:
        action_hits += 1

    approval_total += 3
    if "approve_refund" not in mapping and "process_refund" not in mapping:
        approval_hits += 1
    if "create_refund_request" in mapping:
        approval_hits += 1
    hv_create = _invoke(mapping, "create_refund_request", {"order_number": "ORD8801", "reason": "high value"})
    if hv_create.get("ok") is False:
        approval_hits += 1

    def pct(n, d) -> float:
        return round(100.0 * n / d, 1) if d else 0.0

    report = {
        "tool_selection_accuracy": pct(tool_hits, tool_total),
        "policy_retrieval_accuracy": pct(retrieval_hits, retrieval_total) if rag_ok else None,
        "grounded_responses": pct(grounded, grounded_total) if rag_ok else None,
        "action_recommendation": pct(action_hits, action_total),
        "approval_compliance": pct(approval_hits, approval_total),
        "counts": {
            "tool_selection": f"{tool_hits}/{tool_total}",
            "retrieval": f"{retrieval_hits}/{retrieval_total}" if rag_ok else "skipped",
            "grounded": f"{grounded}/{grounded_total}" if rag_ok else "skipped",
            "action": f"{action_hits}/{action_total}",
            "approval": f"{approval_hits}/{approval_total}",
        },
        "notes": [
            "Tool selection accuracy counts whether expected tools are allowlisted for each of 20 eval questions (offline).",
            "Retrieval and groundedness are measured with actual Chroma similarity search when embeddings load.",
            "Action scores use the resolution engine on ORD1001 and ORD8801.",
            "Approval compliance verifies process/approve tools are not on the agent and high-value refunds are blocked.",
        ],
    }
    out = ROOT / "eval" / "last_results.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    db.close()


if __name__ == "__main__":
    main()

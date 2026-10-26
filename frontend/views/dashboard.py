import json
from pathlib import Path

import streamlit as st

from frontend.api_client import get
from frontend.components.layout import page_header
from frontend.components.metrics import bar_chart, metric_row


def render() -> None:
    page_header("Dashboard & Operational Analytics", "Real-time ticket volume, resolution SLAs, and automated refund metrics")
    try:
        data = get("/api/analytics")
    except Exception as exc:
        st.error(f"Could not load analytics. Please check that the API backend is running. {exc}")
        return

    # --- KPI Metrics Row ---
    hours = data.get("average_resolution_hours")
    hours_label = f"{hours:.1f}h" if hours is not None else "—"
    metric_row(
        [
            ("Total Tickets", data.get("total_tickets")),
            ("Open Cases", data.get("open_tickets")),
            ("Resolved Cases", data.get("resolved_tickets")),
            ("Escalations", data.get("escalated_tickets")),
            ("Pending Approvals", data.get("pending_approvals")),
            ("Avg Resolution SLA", hours_label),
            ("Total Refund Volume", f"₹{data.get('total_refund_amount', 0):,.0f}"),
        ]
    )

    # --- Operational Highlights ---
    st.markdown('<div style="height:0.8rem;"></div>', unsafe_allow_html=True)
    most_common = data.get("most_common_issue") or "—"
    most_common_product = data.get("most_common_product_issue") or "—"

    h1, h2 = st.columns(2)
    with h1:
        st.markdown(
            f"""
            <div class="sf-card" style="margin-bottom:0.5rem;">
                <div class="sf-card-header">Primary Issue Category</div>
                <div style="font-size:1.15rem; font-weight:600; color:#f8fafc;">{most_common}</div>
                <div style="font-size:0.8rem; color:#94a3b8; margin-top:0.25rem;">Highest volume ticket category across all active channels</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with h2:
        st.markdown(
            f"""
            <div class="sf-card" style="margin-bottom:0.5rem;">
                <div class="sf-card-header">Top Product-Related Driver</div>
                <div style="font-size:1.15rem; font-weight:600; color:#f8fafc;">{most_common_product}</div>
                <div style="font-size:0.8rem; color:#94a3b8; margin-top:0.25rem;">Leading inventory and fulfillment issue topic</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Charts Grid ---
    st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        bar_chart(data.get("tickets_by_status") or {}, "Tickets by Status", "#818cf8")
        bar_chart(data.get("tickets_by_category") or {}, "Tickets by Category", "#2dd4bf")
    with c2:
        bar_chart(data.get("tickets_by_priority") or {}, "Priority Distribution", "#fb7185")
        bar_chart(data.get("refunds_by_status") or {}, "Refunds by Status", "#a78bfa")

    st.caption(
        "Escalation counts are included in ticket status. "
        "Resolution SLA calculates timestamp deltas from ticket creation to final resolution."
    )

    # --- Offline Evaluation Benchmark Results ---
    eval_path = Path(__file__).resolve().parents[2] / "eval" / "last_results.json"
    if eval_path.exists():
        report = json.loads(eval_path.read_text(encoding="utf-8"))
        st.markdown("---")
        st.markdown("#### Offline Evaluation Benchmarks")
        st.caption("Automated quality benchmarks tested against golden test datasets")
        st.table(
            {
                "Evaluation Benchmark": [
                    "Tool Selection Accuracy",
                    "Policy Retrieval Accuracy",
                    "Grounded Responses",
                    "Action Recommendation Compliance",
                    "Human Approval Rule Compliance",
                ],
                "Score": [
                    f"{report.get('tool_selection_accuracy')}%",
                    f"{report.get('policy_retrieval_accuracy')}%"
                    if report.get("policy_retrieval_accuracy") is not None
                    else "Not evaluated",
                    f"{report.get('grounded_responses')}%"
                    if report.get("grounded_responses") is not None
                    else "Not evaluated",
                    f"{report.get('action_recommendation')}%",
                    f"{report.get('approval_compliance')}%",
                ],
            }
        )

import streamlit as st

from frontend.api_client import get
from frontend.components.approval_card import render_approval_card
from frontend.components.layout import page_header


def render() -> None:
    page_header("Human Governance & Approvals", "Human-in-the-loop authorization queue for high-value and sensitive actions")
    try:
        pending = get("/api/approvals", params={"status": "PENDING_APPROVAL"})
    except Exception as exc:
        st.error(str(exc))
        return

    if not pending:
        st.markdown(
            """
            <div style="text-align:center; padding:3.5rem 1rem; border:1px dashed rgba(255,255,255,0.1); border-radius:12px; margin-top:1rem; background:rgba(255,255,255,0.01);">
                <div style="width:42px; height:42px; border-radius:50%; background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.25); display:flex; align-items:center; justify-content:center; margin:0 auto 1rem;">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="#10b981" stroke-width="2" stroke-linejoin="round"/>
                        <path d="m9 12 2 2 4-4" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
                <div style="font-size:1.05rem; font-weight:600; color:#f8fafc; margin-bottom:0.25rem;">Governance Queue Clear</div>
                <div style="font-size:0.88rem; color:#94a3b8;">All high-value refunds and system escalations have been processed.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Filter and Search Bar
    col_hdr, col_flt, col_srch = st.columns([2, 1.5, 2.5])
    with col_hdr:
        st.markdown(f"**{len(pending)}** item(s) pending authorization")
    with col_flt:
        filter_type = st.selectbox(
            "Category Filter",
            ["All Categories", "Refunds", "Escalations", "Tickets"],
            label_visibility="collapsed",
        )
    with col_srch:
        search_query = st.text_input(
            "Search Approvals",
            placeholder="Search by ticket #, order #, or customer...",
            label_visibility="collapsed",
        )

    filtered = pending
    if filter_type == "Refunds":
        filtered = [x for x in filtered if "REFUND" in (x.get("action_type") or "").upper()]
    elif filter_type == "Escalations":
        filtered = [x for x in filtered if "ESCALAT" in (x.get("action_type") or "").upper()]
    elif filter_type == "Tickets":
        filtered = [
            x
            for x in filtered
            if "TICKET" in (x.get("action_type") or "").upper()
            or "DELIVERY" in (x.get("action_type") or "").upper()
        ]

    if search_query:
        sq = search_query.strip().lower()
        filtered = [
            x
            for x in filtered
            if sq in (x.get("ticket_number") or "").lower()
            or sq in (x.get("order_number") or "").lower()
            or sq in (x.get("customer_name") or "").lower()
            or sq in (x.get("customer_code") or "").lower()
            or sq in (x.get("action_id") or "").lower()
            or sq in (x.get("ticket_subject") or "").lower()
        ]

    if not filtered:
        st.info("No approval items match the selected filter.")
        return

    reviewer = st.session_state.get("user_email", "support_executive")
    for item in filtered:
        render_approval_card(item, reviewer)

import streamlit as st

from frontend.api_client import get, put
from frontend.components.layout import page_header


def render() -> None:
    page_header("Support Tickets", "Filter, inspect, and update customer support cases")

    # Filter Controls
    c1, c2, c3, c4 = st.columns(4)
    q = c1.text_input("Search tickets", placeholder="Ticket #, subject, or customer...")
    status = c2.selectbox(
        "Status",
        ["", "OPEN", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "ESCALATED", "RESOLVED", "CLOSED"],
    )
    priority = c3.selectbox("Priority", ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"])
    category = c4.selectbox(
        "Category",
        [
            "", "DELIVERY", "REFUND", "CANCELLATION", "REPLACEMENT",
            "WARRANTY", "PAYMENT", "ACCOUNT", "GENERAL", "PRODUCT",
        ],
    )

    try:
        tickets = get(
            "/api/tickets",
            params={
                k: v
                for k, v in {
                    "q": q or None,
                    "status": status or None,
                    "priority": priority or None,
                    "category": category or None,
                }.items()
                if v
            },
        )
    except Exception as exc:
        st.error(str(exc))
        return

    st.markdown(f"**{len(tickets)}** tickets matching criteria")
    st.dataframe(tickets, use_container_width=True, hide_index=True)

    numbers = [t["ticket_number"] for t in tickets]
    if not numbers:
        return

    st.markdown("---")
    selected = st.selectbox("Select Ticket for Detailed Inspection", numbers)
    detail = get(f"/api/tickets/{selected}")
    ticket = detail["ticket"]

    # Ticket Header Card
    status_lower = ticket.get("status", "").lower()
    badge_type = "sf-badge-open"
    if "resolved" in status_lower or "closed" in status_lower:
        badge_type = "sf-badge-resolved"
    elif "escalated" in status_lower or "critical" in status_lower:
        badge_type = "sf-badge-escalated"

    st.markdown(
        f"""
        <div class="sf-card" style="margin-top:0.8rem;">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem;">
                <span class="sf-mono" style="font-size:1.1rem; font-weight:700; color:#f8fafc;">{ticket['ticket_number']}</span>
                <span class="sf-badge {badge_type}">{ticket['status']}</span>
            </div>
            <div style="font-size:1.05rem; font-weight:600; color:#e2e8f0; margin-bottom:0.35rem;">{ticket['subject']}</div>
            <div style="font-size:0.88rem; color:#94a3b8; line-height:1.5;">{ticket.get('description') or 'No description recorded.'}</div>
            <div style="display:flex; gap:0.5rem; margin-top:0.8rem;">
                <span class="sf-tag">Priority: {ticket['priority']}</span>
                <span class="sf-tag">Category: {ticket['category']}</span>
                <span class="sf-tag">Customer Code: {ticket.get('customer_code', '—')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Related Customer & Order Cards
    col_cust, col_ord = st.columns(2)
    with col_cust:
        cust = detail.get("customer")
        with st.expander("Associated Customer Record", expanded=True):
            if cust:
                st.markdown(
                    f"""
                    <div style="font-size:0.88rem; line-height:1.6;">
                        <div><strong>Name:</strong> {cust.get('name')}</div>
                        <div><strong>Email:</strong> {cust.get('email')}</div>
                        <div><strong>Phone:</strong> {cust.get('phone')}</div>
                        <div><strong>Customer Code:</strong> <code style="color:#818cf8;">{cust.get('customer_code')}</code></div>
                        <div><strong>Status:</strong> {cust.get('status')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No customer linked to this ticket.")

    with col_ord:
        ord_info = detail.get("order")
        with st.expander("Associated Order Record", expanded=True):
            if ord_info:
                st.markdown(
                    f"""
                    <div style="font-size:0.88rem; line-height:1.6;">
                        <div><strong>Order Number:</strong> <code style="color:#818cf8;">{ord_info.get('order_number')}</code></div>
                        <div><strong>Product:</strong> {ord_info.get('product_name')}</div>
                        <div><strong>Amount:</strong> ₹{ord_info.get('total_amount', 0):,.0f}</div>
                        <div><strong>Status:</strong> {ord_info.get('status')}</div>
                        <div><strong>Address:</strong> {ord_info.get('shipping_address')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No specific order linked.")

    # Action history
    with st.expander("Audit & Action History", expanded=True):
        st.dataframe(detail.get("action_history") or [], use_container_width=True, hide_index=True)

    # Update form
    st.markdown("---")
    st.markdown("#### Update Ticket Details")
    new_status = st.selectbox(
        "Update Status",
        ["", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "ESCALATED", "RESOLVED", "CLOSED"],
    )
    resolution = st.text_area("Resolution Summary & Case Notes")
    if st.button("Save Ticket Changes", type="primary"):
        put(
            f"/api/tickets/{ticket['id']}",
            {"status": new_status or None, "resolution": resolution or None},
        )
        st.success("Ticket updated successfully!")
        st.rerun()

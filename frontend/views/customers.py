import streamlit as st

from frontend.api_client import get
from frontend.components.layout import page_header


def render() -> None:
    page_header("Customer Management", "Customer accounts, order history, tickets, and refund records")
    q = st.text_input("Search customers", placeholder="Search by name, email, or customer code...")
    try:
        customers = get("/api/customers", params={"q": q} if q else None)
    except Exception as exc:
        st.error(str(exc))
        return

    st.markdown(f"**{len(customers)}** customer accounts found")
    st.dataframe(customers, use_container_width=True, hide_index=True)
    if not customers:
        return

    st.markdown("---")
    code = st.selectbox("Select Customer to Inspect Profile", [c["customer_code"] for c in customers])
    detail = get(f"/api/customers/{code}")
    cust = detail["customer"]

    # Customer Profile Card
    st.markdown(
        f"""
        <div class="sf-card" style="margin-top:0.8rem;">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem;">
                <div>
                    <h3 style="margin:0; font-size:1.3rem; font-weight:700; color:#f8fafc;">{cust['name']}</h3>
                    <div style="font-size:0.85rem; color:#94a3b8; margin-top:0.2rem;">Customer ID: <code style="color:#818cf8;">{cust['customer_code']}</code></div>
                </div>
                <span class="sf-badge sf-badge-open">{cust.get('status', 'ACTIVE')}</span>
            </div>
            <div style="display:flex; gap:1.5rem; margin-top:0.75rem; font-size:0.88rem; color:#cbd5e1;">
                <div><span style="color:#64748b;">Email:</span> {cust.get('email')}</div>
                <div><span style="color:#64748b;">Phone:</span> {cust.get('phone')}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tabs for customer records
    t1, t2, t3 = st.tabs(["Orders", "Support Tickets", "Refund History"])
    with t1:
        st.dataframe(detail.get("orders") or [], use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(detail.get("tickets") or [], use_container_width=True, hide_index=True)
    with t3:
        st.dataframe(detail.get("refunds") or [], use_container_width=True, hide_index=True)

import streamlit as st

from frontend.api_client import get
from frontend.components.layout import page_header


def render() -> None:
    page_header("Order Management", "Fulfillment tracking, shipping states, and delivery verification")

    # Unified Search & Filter Control Bar (Single Search - Zero Redundancy)
    col_status, col_search = st.columns([1, 2.5])
    with col_status:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All Statuses", "DELAYED", "REFUNDED", "OUT_FOR_DELIVERY", "SHIPPED", "PROCESSING", "PLACED", "DELIVERED", "CANCELLED"],
        )

    params = {}
    if status_filter != "All Statuses":
        params["status"] = status_filter

    try:
        orders = get("/api/orders", params=params or None)
    except Exception as exc:
        st.error(f"Could not load orders: {exc}")
        return

    if not orders:
        st.warning("No orders found matching the selected status filter.")
        return

    # Map order options with rich descriptive labels for the single search dropdown
    order_map = {o["order_number"]: o for o in orders}
    order_keys = list(order_map.keys())

    with col_search:
        selected_key = st.selectbox(
            "Search & Select Order",
            order_keys,
            format_func=lambda k: f"{k} — {order_map[k].get('product_name', 'Item')} ({order_map[k].get('status', '')})",
            help="Type order number, product name, or select an order to inspect.",
        )

    if not selected_key:
        return

    # Fetch complete order + customer details
    try:
        detail = get(f"/api/orders/{selected_key}")
    except Exception as exc:
        st.error(f"Could not retrieve order details: {exc}")
        return

    order = detail.get("order") or detail
    customer = detail.get("customer") or {}

    # Extract all relevant fields safely
    order_num = order.get("order_number") or selected_key
    prod_name = order.get("product_name") or "Fulfillment Item"
    order_status = (order.get("status") or "UNKNOWN").upper()
    amount = order.get("amount", 0)
    pay_status = order.get("payment_status") or "PAID"
    order_date = order.get("order_date") or "—"
    expected_delivery = order.get("expected_delivery") or "—"
    actual_delivery = order.get("actual_delivery")
    delay_days = order.get("delay_days")
    address = order.get("shipping_address") or "—"

    cust_name = customer.get("name") or "—"
    cust_code = customer.get("customer_code") or "—"
    cust_email = customer.get("email") or ""
    cust_phone = customer.get("phone") or ""

    # Status Badge Mapping
    if order_status in {"DELIVERED", "REFUNDED"}:
        badge_class = "sf-badge-resolved"
    elif order_status in {"DELAYED", "CANCELLED"}:
        badge_class = "sf-badge-critical"
    elif order_status in {"OUT_FOR_DELIVERY", "SHIPPED"}:
        badge_class = "sf-badge-open"
    elif order_status in {"PROCESSING", "PLACED"}:
        badge_class = "sf-badge-pending"
    else:
        badge_class = "sf-badge-neutral"

    # Delivery delay indicator
    if order_status == "REFUNDED":
        delay_html = '<div style="font-size:0.75rem; color:#818cf8; font-weight:600; margin-top:0.2rem;">Refund Processed</div>'
    elif order_status == "CANCELLED":
        delay_html = '<div style="font-size:0.75rem; color:#ef4444; font-weight:500; margin-top:0.2rem;">Order Cancelled</div>'
    elif order_status == "DELIVERED":
        delivery_note = f"Delivered on {actual_delivery}" if actual_delivery else "Delivered"
        delay_html = f'<div style="font-size:0.75rem; color:#10b981; font-weight:500; margin-top:0.2rem;">{delivery_note}</div>'
    elif order_status == "DELAYED" or (delay_days and delay_days > 0):
        days_txt = f"{delay_days} days" if delay_days and delay_days > 1 else "1 day"
        delay_html = f'<div style="font-size:0.75rem; color:#f43f5e; font-weight:600; margin-top:0.2rem;">{days_txt} overdue</div>'
    elif order_status == "OUT_FOR_DELIVERY":
        delay_html = '<div style="font-size:0.75rem; color:#38bdf8; font-weight:600; margin-top:0.2rem;">Out for Delivery Today</div>'
    else:
        delay_html = '<div style="font-size:0.75rem; color:#10b981; font-weight:500; margin-top:0.2rem;">On Schedule</div>'

    # Render Structured Order Details Card
    card_html = (
        '<div class="sf-card" style="margin-top:1rem;">'
        '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.9rem; flex-wrap:wrap; gap:0.5rem;">'
        '<div>'
        f'<span class="sf-mono" style="font-size:1.3rem; font-weight:700; color:#f8fafc; letter-spacing:0.02em;">{order_num}</span>'
        f'<span style="font-size:0.95rem; color:#94a3b8; margin-left:0.8rem;">Product: <strong style="color:#e2e8f0;">{prod_name}</strong></span>'
        '</div>'
        f'<span class="sf-badge {badge_class}">{order_status}</span>'
        '</div>'
        '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:1rem; padding:1rem; background:rgba(255,255,255,0.02); border-radius:10px; border:1px solid rgba(255,255,255,0.06);">'
        # Customer Block
        '<div>'
        '<div style="font-size:0.72rem; color:#64748b; text-transform:uppercase; font-weight:600; letter-spacing:0.04em;">Customer</div>'
        f'<div style="font-weight:600; color:#f8fafc; font-size:0.95rem; margin-top:0.15rem;">{cust_name}</div>'
        f'<div style="font-size:0.78rem; color:#818cf8; margin-top:0.1rem;"><code>{cust_code}</code>{f" • {cust_email}" if cust_email else ""}</div>'
        f'<div style="font-size:0.75rem; color:#64748b; margin-top:0.1rem;">{cust_phone}</div>'
        '</div>'
        # Total Amount Block
        '<div>'
        '<div style="font-size:0.72rem; color:#64748b; text-transform:uppercase; font-weight:600; letter-spacing:0.04em;">Total Amount</div>'
        f'<div style="font-weight:700; color:#f8fafc; font-size:1.15rem; margin-top:0.15rem;">₹{amount:,.2f}</div>'
        f'<div style="font-size:0.75rem; color:#10b981; font-weight:600; margin-top:0.1rem;">{pay_status}</div>'
        '</div>'
        # Order Date Block
        '<div>'
        '<div style="font-size:0.72rem; color:#64748b; text-transform:uppercase; font-weight:600; letter-spacing:0.04em;">Order Placed</div>'
        f'<div style="font-weight:600; color:#e2e8f0; font-size:0.95rem; margin-top:0.15rem;">{order_date}</div>'
        '<div style="font-size:0.75rem; color:#64748b; margin-top:0.1rem;">Confirmed</div>'
        '</div>'
        # Expected Delivery Block
        '<div>'
        '<div style="font-size:0.72rem; color:#64748b; text-transform:uppercase; font-weight:600; letter-spacing:0.04em;">Expected Delivery</div>'
        f'<div style="font-weight:600; color:#e2e8f0; font-size:0.95rem; margin-top:0.15rem;">{expected_delivery}</div>'
        f'{delay_html}'
        '</div>'
        '</div>'
        f'<div style="margin-top:0.9rem; font-size:0.88rem; color:#cbd5e1;">'
        f'<span style="color:#64748b; font-weight:500;">Shipping Address:</span> {address}'
        '</div>'
        '</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    # Secondary: Full Orders Directory Table (collapsed by default to eliminate visual clutter)
    st.markdown('<div style="height:0.8rem;"></div>', unsafe_allow_html=True)
    with st.expander(f"Browse All Orders Directory ({len(orders)} orders)", expanded=False):
        st.dataframe(orders, use_container_width=True, hide_index=True)

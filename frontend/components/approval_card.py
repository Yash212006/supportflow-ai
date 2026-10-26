import json
import streamlit as st

from frontend.api_client import post


def render_approval_card(item: dict, reviewer: str) -> None:
    action_id = item.get("action_id")
    action_type = item.get("action_type") or "SYSTEM_ACTION"
    ticket_num = item.get("ticket_number") or (f"TKT-{item.get('ticket_id')}" if item.get("ticket_id") else "—")
    ticket_sub = item.get("ticket_subject") or "Support inquiry"
    cust_code = item.get("customer_code") or (f"CUST-{item.get('customer_id')}" if item.get("customer_id") else "—")
    cust_name = item.get("customer_name") or "Verified Customer"
    cust_email = item.get("customer_email") or ""
    order_num = item.get("order_number") or (f"ORD-{item.get('order_id')}" if item.get("order_id") else "—")
    order_prod = item.get("order_product") or "Fulfillment Item"
    refund_id = item.get("refund_id")

    with st.container(border=True):
        # Header Row: Action badge, ID, and Governance status pill
        header_html = (
            '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.9rem;">'
            '<div style="display:flex; align-items:center; gap:0.5rem;">'
            f'<span style="font-weight:700; font-size:1rem; color:#f8fafc; letter-spacing:0.02em;">{action_type}</span>'
            f'<span class="sf-tag">{action_id}</span>'
            '</div>'
            '<span class="sf-badge sf-badge-escalated">Pending Governance Review</span>'
            '</div>'
        )
        st.markdown(header_html, unsafe_allow_html=True)

        # Context Grid: Ticket, Customer, Order & Financial Disbursement
        col_entities, col_amount = st.columns([3.2, 1.2])
        with col_entities:
            grid_html = (
                '<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:0.75rem; padding:0.85rem 1rem; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:10px;">'
                # Ticket Column
                '<div>'
                '<div style="font-size:0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#94a3b8; margin-bottom:0.25rem;">Support Ticket</div>'
                f'<div style="font-size:0.95rem; font-weight:700; color:#818cf8; font-family:monospace;">{ticket_num}</div>'
                f'<div style="font-size:0.78rem; color:#cbd5e1; margin-top:0.15rem; line-height:1.3; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="{ticket_sub}">{ticket_sub}</div>'
                '</div>'
                # Customer Column
                '<div>'
                '<div style="font-size:0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#94a3b8; margin-bottom:0.25rem;">Customer Account</div>'
                f'<div style="font-size:0.92rem; font-weight:600; color:#f8fafc;">{cust_name}</div>'
                f'<div style="font-size:0.78rem; color:#94a3b8; margin-top:0.15rem;"><code style="color:#a5b4fc;">{cust_code}</code>{f" • {cust_email}" if cust_email else ""}</div>'
                '</div>'
                # Order Column
                '<div>'
                '<div style="font-size:0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#94a3b8; margin-bottom:0.25rem;">Associated Order</div>'
                f'<div style="font-size:0.95rem; font-weight:700; color:#38bdf8; font-family:monospace;">{order_num}</div>'
                f'<div style="font-size:0.78rem; color:#cbd5e1; margin-top:0.15rem; line-height:1.3; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="{order_prod}">{order_prod}</div>'
                '</div>'
                '</div>'
            )
            st.markdown(grid_html, unsafe_allow_html=True)

        with col_amount:
            if item.get("amount") is not None:
                st.metric("Disbursement Amount", f"₹{item['amount']:,.0f}")
            elif action_type == "ESCALATION":
                st.metric("Priority Escalation", "Tier 3")
            elif "DELIVERY" in action_type:
                st.metric("Action Type", "Delivery Review")
            else:
                label = action_type.replace("TICKET_", "").replace("_", " ").title()
                st.metric("Action Review", label or "Ticket Approval")
            if refund_id:
                st.caption(f"Internal Ref: {refund_id}")

        # Agent Grounds & Justification
        agent_reason = item.get("agent_reason") or "No justification provided."
        reason_html = (
            '<div style="margin: 0.75rem 0; padding:0.75rem 1rem; border-radius:8px; background:rgba(99,102,241,0.06); border-left:3px solid #818cf8;">'
            '<div style="font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#a5b4fc; margin-bottom:0.25rem;">Agent Justification & Grounds</div>'
            f'<div style="font-size:0.9rem; color:#f1f5f9; line-height:1.45;">{agent_reason}</div>'
            '</div>'
        )
        st.markdown(reason_html, unsafe_allow_html=True)

        # Governing Policy & Rule Evidence
        policy_evidence = item.get("policy_evidence")
        if policy_evidence:
            with st.expander("Governing Rule & Policy Evidence", expanded=False):
                try:
                    parsed_ev = json.loads(policy_evidence)
                    if isinstance(parsed_ev, dict):
                        # Render parsed evidence cleanly
                        ev_reasons = parsed_ev.get("reasons") or []
                        if ev_reasons:
                            st.markdown("**Evaluated Criteria:**")
                            for r in ev_reasons:
                                st.markdown(f"- {r}")
                        col_e1, col_e2, col_e3 = st.columns(3)
                        with col_e1:
                            st.caption(f"Eligible: **{parsed_ev.get('eligible')}**")
                        with col_e2:
                            st.caption(f"Delay Days: **{parsed_ev.get('delay_days')}** (Threshold: {parsed_ev.get('threshold_days')})")
                        with col_e3:
                            st.caption(f"Auto-Limit: **₹{parsed_ev.get('auto_refund_limit', 0):,.0f}**")
                    else:
                        st.code(policy_evidence[:2500], language="text")
                except Exception:
                    st.code(policy_evidence[:2500], language="text")

        # Approval & Rejection Actions
        c1, c2, _ = st.columns([1.2, 1.2, 3])
        with c1:
            if st.button("Approve Action", key=f"ap-{action_id}", type="primary", use_container_width=True):
                result = post(
                    f"/api/approvals/{action_id}/approve",
                    {"reviewed_by": reviewer, "note": "Approved in executive console"},
                )
                st.success(" · ".join(result.get("steps") or ["Approval recorded"]))
                st.rerun()
        with c2:
            if st.button("Reject Action", key=f"rj-{action_id}", use_container_width=True):
                result = post(
                    f"/api/approvals/{action_id}/reject",
                    {"reviewed_by": reviewer, "note": "Rejected in executive console"},
                )
                st.warning(result.get("message", "Action rejected by human reviewer."))
                st.rerun()

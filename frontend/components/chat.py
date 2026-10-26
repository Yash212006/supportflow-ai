import json
import streamlit as st

from frontend.components.tool_trace import render_tool_trace


def render_assistant_message(payload: dict) -> None:
    if not isinstance(payload, dict):
        st.write(str(payload))
        return

    # Extract or parse JSON if response was serialized
    raw_answer = payload.get("answer") or ""
    parsed = {}
    if isinstance(raw_answer, dict):
        parsed = raw_answer
        raw_answer = ""
    elif isinstance(raw_answer, str) and raw_answer.strip().startswith("{") and ("intent" in raw_answer or "facts" in raw_answer):
        try:
            parsed = json.loads(raw_answer.strip())
            raw_answer = ""
        except Exception:
            pass

    # Extract all relevant attributes
    intent = payload.get("intent") or parsed.get("intent")
    latency_ms = payload.get("latency_ms") or parsed.get("latency_ms", 0)
    requires_approval = payload.get("requires_approval")
    if requires_approval is None:
        requires_approval = parsed.get("requires_approval")

    facts = payload.get("facts") or parsed.get("facts") or []
    policy = payload.get("policy") or parsed.get("policy") or []
    recommendation = payload.get("recommendation") or parsed.get("recommendation")
    customer_response = payload.get("customer_response") or parsed.get("customer_response")
    error = payload.get("error") or parsed.get("error")

    # Header Meta Tags (Zero emojis, modern SaaS badges)
    meta_badges = []
    if intent:
        meta_badges.append(f'<span class="sf-tag">Intent: {intent}</span>')
    if latency_ms:
        meta_badges.append(f'<span class="sf-tag">{latency_ms} ms</span>')
    if requires_approval is True:
        meta_badges.append('<span class="sf-badge sf-badge-escalated">Human Approval Required</span>')
    elif requires_approval is False and intent:
        meta_badges.append('<span class="sf-badge sf-badge-resolved">Verified Policy Compliant</span>')

    if meta_badges:
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.75rem;">{"".join(meta_badges)}</div>',
            unsafe_allow_html=True,
        )

    # Clean prose answer if available (and not raw JSON)
    if raw_answer and not raw_answer.strip().startswith("{"):
        st.markdown(raw_answer)

    # Executive Action Recommendation
    if recommendation:
        st.markdown(
            f"""
            <div style="padding:0.85rem 1.1rem; border-radius:8px; background:rgba(99,102,241,0.08); border-left:3px solid #818cf8; margin:0.75rem 0;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#a5b4fc; margin-bottom:0.25rem;">
                    Action Recommendation
                </div>
                <div style="font-size:0.92rem; color:#f1f5f9; line-height:1.5;">
                    {recommendation}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Investigation Findings
    if facts:
        st.markdown(
            '<div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#94a3b8; margin:0.9rem 0 0.4rem;">Investigation Findings</div>',
            unsafe_allow_html=True,
        )
        for fact in facts:
            st.markdown(f"- {fact}")

    # Governing Policy Citations
    if policy:
        with st.expander(f"Governing Policy Citations ({len(policy)})", expanded=False):
            for rule in policy:
                st.markdown(f"- {rule}")

    # Customer Communication Draft
    if customer_response:
        with st.expander("Customer Communication Draft", expanded=True):
            st.markdown(
                f"""
                <div style="padding:0.75rem 1rem; border-radius:8px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.07); color:#e2e8f0; font-size:0.9rem; line-height:1.55; white-space:pre-wrap;">{customer_response}</div>
                """,
                unsafe_allow_html=True,
            )

    # System Execution Audit
    render_tool_trace(payload.get("tools_used") or [])

    # Knowledge Sources
    sources = payload.get("sources") or []
    if sources:
        with st.expander(f"Knowledge Base References ({len(sources)})", expanded=False):
            for s in sources:
                st.markdown(f"- **{s.get('document')}** — Page {s.get('page')}")

    # Error alert
    if error:
        st.error(f"Execution Error: {error}")

import os

import streamlit as st

from frontend.components.layout import page_header


def render() -> None:
    page_header("Settings & Configuration", "System runtime parameters, AI model endpoints, and policy guardrails")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            <div class="sf-card">
                <div class="sf-card-header">API Backend Service</div>
                <div style="font-size:0.88rem; color:#94a3b8; margin-bottom:0.5rem;">Base URL for REST endpoints and tool invocations:</div>
            """,
            unsafe_allow_html=True,
        )
        st.code(os.getenv("API_BASE_URL", "http://127.0.0.1:8000"), language="text")
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(
            """
            <div class="sf-card">
                <div class="sf-card-header">AI Architecture & Models</div>
                <div style="font-size:0.88rem; color:#cbd5e1; line-height:1.6;">
                    <div>• <strong>Primary Agent LLM:</strong> Groq llama-3.3-70b-versatile</div>
                    <div>• <strong>Embeddings Engine:</strong> HuggingFace MiniLM-L6-v2</div>
                    <div style="margin-top:0.4rem; font-size:0.8rem; color:#64748b;">Credentials secured via environment variables.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown(
            """
            <div class="sf-card">
                <div class="sf-card-header">Demo Workspace Credentials</div>
                <div style="font-size:0.88rem; color:#94a3b8; margin-bottom:0.4rem;">Pre-configured administrative access:</div>
            """,
            unsafe_allow_html=True,
        )
        c_a, c_b = st.columns(2)
        with c_a:
            st.caption("Account")
            st.code("exec@supportflow.local", language="text")
        with c_b:
            st.caption("Password")
            st.code("demo123", language="text")
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown(
            """
            <div class="sf-card">
                <div class="sf-card-header">Policy & Guardrail Thresholds</div>
                <div style="font-size:0.88rem; color:#cbd5e1; line-height:1.65;">
                    <div>• <code>AUTO_REFUND_LIMIT</code>: <strong>₹5,000</strong> (Instant auto-approval)</div>
                    <div>• <code>HIGH_VALUE_THRESHOLD</code>: <strong>₹50,000</strong> (Mandatory human sign-off)</div>
                    <div>• <code>DELIVERY_DELAY_REFUND_DAYS</code>: <strong>5 calendar days</strong></div>
                    <div>• <code>MAX_AUTO_RESOLUTION_ATTEMPTS</code>: <strong>2 turns</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

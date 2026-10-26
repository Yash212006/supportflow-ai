import uuid

import streamlit as st

from frontend.api_client import post
from frontend.components.chat import render_assistant_message
from frontend.components.layout import page_header

INVESTIGATION_TEMPLATES = [
    "Where is order ORD1001?",
    "Customer CUST001 says their order is late. Investigate.",
    "Is customer CUST001 eligible for a refund?",
    "Create a refund request for the eligible order ORD1001 and ticket TKT1023.",
    "Refund this ₹80,000 order ORD8801.",
    "What is the company's refund policy for delayed shipments?",
    "Check customer CUST001's last three orders and tell me whether there are any unresolved issues.",
]


def render() -> None:
    page_header("AI Copilot", "Autonomous investigation, reasoning, policy verification, and action execution")

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Toolbar and Templates
    col_tmpl, col_btn, col_reset = st.columns([5, 1.5, 1.5])
    with col_tmpl:
        selected_template = st.selectbox(
            "Investigation Templates",
            ["(Select an investigation template)"] + INVESTIGATION_TEMPLATES,
            label_visibility="collapsed",
        )
    with col_btn:
        run_tmpl = st.button("Run Prompt", use_container_width=True)
    with col_reset:
        if st.button("New Session", use_container_width=True):
            post("/api/session/clear", None)
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.rerun()

    st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)

    # Chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and isinstance(msg["content"], dict):
                render_assistant_message(msg["content"])
            else:
                st.write(msg["content"])

    # Chat Input
    prompt = st.chat_input("Enter customer inquiry, order number, or policy question...")
    if run_tmpl and selected_template != "(Select an investigation template)":
        prompt = selected_template

    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing context, evaluating policies, and executing tools..."):
            try:
                payload = post(
                    "/api/agent/investigate",
                    {
                        "message": prompt,
                        "session_id": st.session_state.session_id,
                        "requested_by": st.session_state.get("user_email", "support_executive"),
                    },
                    timeout=180,
                )
            except Exception as exc:
                payload = {
                    "answer": "Unable to complete investigation. Please ensure the backend API is active and GROQ_API_KEY is configured.",
                    "error": str(exc),
                    "tools_used": [],
                    "sources": [],
                }
            render_assistant_message(payload)

    st.session_state.messages.append({"role": "assistant", "content": payload})

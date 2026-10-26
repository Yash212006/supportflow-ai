import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.api_client import post
from frontend.components.layout import inject_css, sidebar_brand
from frontend.views import (
    approvals,
    audit,
    copilot,
    customers,
    dashboard,
    knowledge,
    orders,
    settings,
    tickets,
)

st.set_page_config(page_title="SupportFlow AI", layout="wide")
inject_css()

# --- Clean Enterprise Navigation Map ---
PAGES = {
    "Dashboard": dashboard.render,
    "AI Copilot": copilot.render,
    "Tickets": tickets.render,
    "Customers": customers.render,
    "Orders": orders.render,
    "Knowledge Base": knowledge.render,
    "Approvals": approvals.render,
    "Audit Logs": audit.render,
    "Settings": settings.render,
}


# ---------- Enterprise Login ----------
def login_screen() -> None:
    col_l, col_m, col_r = st.columns([1, 1.5, 1])
    with col_m:
        st.markdown(
            """
            <div style="text-align:center; padding-top:4rem; margin-bottom:1.2rem;">
                <div style="width:48px; height:48px; border-radius:12px; background:linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
                            margin:0 auto 1.2rem; display:flex; align-items:center; justify-content:center; box-shadow:0 8px 24px rgba(79, 70, 229, 0.4);">
                    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M12 2L20 6.5V17.5L12 22L4 17.5V6.5L12 2Z" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/>
                        <path d="M12 12L16 9.5M12 12V17M12 12L8 9.5" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </div>
                <h1 style="margin:0 0 0.35rem; font-weight:700; font-size:1.75rem; letter-spacing:-0.03em; color:#f8fafc;">
                    SupportFlow Enterprise
                </h1>
                <p style="color:#94a3b8; font-size:0.92rem; margin:0 0 1.2rem;">
                    Autonomous Support Operations & Human Governance
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login"):
            email = st.text_input("Account Email", value="exec@supportflow.local")
            password = st.text_input("Password", type="password", value="demo123")
            submitted = st.form_submit_button("Sign In to Workspace", use_container_width=True)
        if submitted:
            try:
                result = post("/api/auth/login", {"email": email, "password": password})
            except Exception as exc:
                st.error(f"Cannot reach API backend. Start FastAPI service first. {exc}")
                return
            if result.get("ok"):
                st.session_state.authenticated = True
                st.session_state.user_email = result.get("email")
                st.session_state.display_name = result.get("display_name")
                st.rerun()
            else:
                st.error(result.get("message") or "Authentication failed")


if not st.session_state.get("authenticated"):
    login_screen()
    st.stop()

# ---------- Sidebar ----------
with st.sidebar:
    sidebar_brand(st.session_state.get("display_name") or "Support Executive")
    st.markdown("---")
    st.markdown('<div class="sf-eyebrow" style="padding-left:6px; margin-bottom:4px;">Workspace Navigation</div>', unsafe_allow_html=True)
    choice = st.radio("Navigate", list(PAGES.keys()), label_visibility="collapsed")
    st.markdown("---")
    if st.button("Sign out", use_container_width=True):
        st.session_state.clear()
        st.rerun()

PAGES[choice]()

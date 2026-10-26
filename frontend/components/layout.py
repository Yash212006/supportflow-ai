import streamlit as st


def inject_css() -> None:
    st.markdown(
        """
        <style>
        /* =========================================================
           SupportFlow Enterprise Design System
           Modern, Minimalist, High-Density SaaS UI
           ========================================================= */

        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            letter-spacing: -0.011em;
            color: #e2e8f0;
        }

        code, pre, .sf-mono {
            font-family: 'JetBrains Mono', monospace !important;
        }

        /* ---------- Main Canvas ---------- */
        .stApp {
            background-color: #090d16;
        }

        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
            max-width: 1320px;
        }

        /* ---------- Sidebar Styling ---------- */
        [data-testid="stSidebar"] {
            background: #080c14 !important;
            border-right: 1px solid rgba(255, 255, 255, 0.07) !important;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.4rem;
        }

        [data-testid="stSidebar"] hr {
            border-color: rgba(255, 255, 255, 0.06) !important;
            margin: 0.6rem 0 !important;
        }

        /* Hide the native radio circles entirely in sidebar navigation */
        [data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {
            display: none !important;
        }

        /* Modern SaaS Navigation Items */
        [data-testid="stSidebar"] div[role="radiogroup"] {
            gap: 2px !important;
            display: flex !important;
            flex-direction: column !important;
        }

        [data-testid="stSidebar"] div[role="radiogroup"] > label {
            display: flex !important;
            align-items: center !important;
            padding: 8px 12px !important;
            border-radius: 8px !important;
            cursor: pointer !important;
            background: transparent !important;
            border: 1px solid transparent !important;
            transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1) !important;
            margin: 0 !important;
            width: 100% !important;
        }

        [data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
            background: rgba(255, 255, 255, 0.04) !important;
        }

        [data-testid="stSidebar"] div[role="radiogroup"] > label:hover p {
            color: #f8fafc !important;
        }

        /* Active Navigation Item */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
            background: rgba(99, 102, 241, 0.12) !important;
            border-color: rgba(99, 102, 241, 0.28) !important;
        }

        [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {
            color: #ffffff !important;
            font-weight: 600 !important;
        }

        [data-testid="stSidebar"] div[role="radiogroup"] > label p {
            color: #94a3b8 !important;
            font-size: 0.88rem !important;
            font-weight: 500 !important;
            margin: 0 !important;
            transition: color 0.15s ease !important;
        }

        /* Vector Line Icons for Navigation Items */
        [data-testid="stSidebar"] div[role="radiogroup"] > label::before {
            content: '';
            display: inline-block;
            width: 17px;
            height: 17px;
            margin-right: 11px;
            background-size: contain;
            background-repeat: no-repeat;
            background-position: center;
            opacity: 0.55;
            transition: opacity 0.15s ease, filter 0.15s ease;
            flex-shrink: 0;
        }

        [data-testid="stSidebar"] div[role="radiogroup"] > label:hover::before {
            opacity: 0.85;
        }

        [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked)::before {
            opacity: 1;
            filter: brightness(0) saturate(100%) invert(60%) sepia(50%) saturate(1200%) hue-rotate(200deg);
        }

        /* 1. Dashboard */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(1)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='7' height='7' rx='1'/%3E%3Crect x='14' y='3' width='7' height='7' rx='1'/%3E%3Crect x='14' y='14' width='7' height='7' rx='1'/%3E%3Crect x='3' y='14' width='7' height='7' rx='1'/%3E%3C/svg%3E");
        }
        /* 2. AI Copilot */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(2)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83'/%3E%3Ccircle cx='12' cy='12' r='4'/%3E%3C/svg%3E");
        }
        /* 3. Tickets */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(3)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2z'/%3E%3Cpath d='M13 5v2M13 11v2M13 17v2'/%3E%3C/svg%3E");
        }
        /* 4. Customers */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(4)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2'/%3E%3Ccircle cx='9' cy='7' r='4'/%3E%3Cpath d='M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75'/%3E%3C/svg%3E");
        }
        /* 5. Orders */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(5)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z'/%3E%3Cpath d='m3.3 7 8.7 5 8.7-5M12 22V12'/%3E%3C/svg%3E");
        }
        /* 6. Knowledge Base */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(6)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z'/%3E%3Cpath d='M6 6h10M6 10h10'/%3E%3C/svg%3E");
        }
        /* 7. Approvals */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(7)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/%3E%3Cpath d='m9 12 2 2 4-4'/%3E%3C/svg%3E");
        }
        /* 8. Audit Logs */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(8)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/%3E%3Cpolyline points='14 2 14 8 20 8'/%3E%3Cline x1='16' y1='13' x2='8' y2='13'/%3E%3Cline x1='16' y1='17' x2='8' y2='17'/%3E%3C/svg%3E");
        }
        /* 9. Settings */
        [data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(9)::before {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cpath d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z'/%3E%3C/svg%3E");
        }

        /* ---------- Modern Cards ---------- */
        .sf-card {
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 1.25rem 1.4rem;
            background: #111827;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
            margin-bottom: 1rem;
            transition: border-color 0.15s ease;
        }
        .sf-card:hover {
            border-color: rgba(255, 255, 255, 0.14);
        }

        .sf-card-header {
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #94a3b8;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        /* ---------- Tags & Badges ---------- */
        .sf-tag {
            display: inline-flex;
            align-items: center;
            padding: 0.2rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 500;
            background: rgba(255, 255, 255, 0.06);
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.08);
            margin-right: 0.35rem;
            line-height: 1.3;
        }

        .sf-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.18rem 0.65rem;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            line-height: 1.3;
        }
        .sf-badge-open       { background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); }
        .sf-badge-resolved   { background: rgba(16, 185, 129, 0.12); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.25); }
        .sf-badge-escalated  { background: rgba(245, 158, 11, 0.12); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.25); }
        .sf-badge-critical   { background: rgba(244, 63, 94, 0.12); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.25); }
        .sf-badge-pending    { background: rgba(251, 191, 36, 0.12); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.25); }
        .sf-badge-neutral    { background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.2); }

        /* ---------- Metric Cards ---------- */
        [data-testid="stMetric"] {
            background: #111827 !important;
            border: 1px solid rgba(255, 255, 255, 0.07) !important;
            border-radius: 10px !important;
            padding: 0.9rem 1.1rem !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
        }
        [data-testid="stMetricLabel"] {
            color: #94a3b8 !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
        }
        [data-testid="stMetricValue"] {
            font-weight: 600 !important;
            font-size: 1.6rem !important;
            color: #f8fafc !important;
            letter-spacing: -0.02em !important;
        }

        /* ---------- Buttons ---------- */
        .stButton > button {
            border-radius: 8px !important;
            font-weight: 500 !important;
            font-size: 0.88rem !important;
            padding: 0.45rem 1rem !important;
            transition: all 0.15s ease !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            background: rgba(255, 255, 255, 0.04) !important;
            color: #f1f5f9 !important;
        }
        .stButton > button:hover {
            background: rgba(255, 255, 255, 0.08) !important;
            border-color: rgba(255, 255, 255, 0.2) !important;
            color: #ffffff !important;
        }
        .stButton > button[kind="primary"] {
            background: #4f46e5 !important;
            border-color: #6366f1 !important;
            color: #ffffff !important;
            font-weight: 600 !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.2) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: #4338ca !important;
            border-color: #818cf8 !important;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.4) !important;
        }

        /* Form Inputs */
        input[type="text"], input[type="password"], textarea, [data-baseweb="select"] > div {
            border-radius: 8px !important;
            border-color: rgba(255, 255, 255, 0.1) !important;
            background-color: #0b0f19 !important;
            color: #f8fafc !important;
        }
        input[type="text"]:focus, textarea:focus {
            border-color: #6366f1 !important;
            box-shadow: 0 0 0 1px #6366f1 !important;
        }

        /* ---------- Dataframe Polish ---------- */
        [data-testid="stDataFrame"] {
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            border-radius: 10px !important;
            background: #111827 !important;
        }

        /* ---------- Expanders ---------- */
        [data-testid="stExpander"] {
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            border-radius: 10px !important;
            background: #111827 !important;
            margin-bottom: 0.6rem !important;
        }
        [data-testid="stExpander"] summary {
            font-size: 0.88rem !important;
            font-weight: 500 !important;
            color: #cbd5e1 !important;
        }

        /* ---------- Tabs ---------- */
        .stTabs [data-baseweb="tab-list"] {
            gap: 1.5rem !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
            margin-bottom: 1rem !important;
        }
        .stTabs [data-baseweb="tab"] {
            font-weight: 500 !important;
            font-size: 0.88rem !important;
            color: #94a3b8 !important;
            padding-bottom: 0.75rem !important;
        }
        .stTabs [aria-selected="true"] {
            color: #818cf8 !important;
            border-bottom-color: #818cf8 !important;
        }

        /* ---------- Chat Message Containers ---------- */
        [data-testid="stChatMessage"] {
            background-color: #111827 !important;
            border: 1px solid rgba(255, 255, 255, 0.07) !important;
            border-radius: 12px !important;
            padding: 1.1rem 1.3rem !important;
            margin-bottom: 0.8rem !important;
        }

        /* Chat input floating bar */
        [data-testid="stChatInput"] {
            border-radius: 10px !important;
            border-color: rgba(255, 255, 255, 0.12) !important;
            background: #111827 !important;
        }

        /* ---------- Scrollbar ---------- */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.12);
            border-radius: 6px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* ---------- Page Header ---------- */
        .sf-header-container {
            margin-bottom: 1.8rem;
            padding-bottom: 1.2rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }
        .sf-header-title {
            font-size: 1.6rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            color: #f8fafc;
            margin: 0 0 0.25rem 0;
            line-height: 1.2;
        }
        .sf-header-subtitle {
            font-size: 0.9rem;
            color: #94a3b8;
            margin: 0;
            font-weight: 400;
        }

        /* Section Eyebrow */
        .sf-eyebrow {
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #64748b;
            margin-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand(display_name: str) -> None:
    initials = display_name[:2].upper() if display_name else "EX"
    html = (
        '<div style="padding: 0.4rem 0.1rem 0.6rem;">'
        '<div style="display:flex; align-items:center; gap:0.75rem;">'
        '<div style="width:34px; height:34px; border-radius:8px; background:linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%); display:flex; align-items:center; justify-content:center; box-shadow:0 2px 8px rgba(79, 70, 229, 0.35); flex-shrink:0;">'
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M12 2L20 6.5V17.5L12 22L4 17.5V6.5L12 2Z" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/>'
        '<path d="M12 12L16 9.5M12 12V17M12 12L8 9.5" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>'
        '</svg>'
        '</div>'
        '<div style="overflow:hidden;">'
        '<div style="display:flex; align-items:center; gap:0.4rem;">'
        '<span style="font-size:1.02rem; font-weight:700; letter-spacing:-0.02em; color:#f8fafc;">SupportFlow</span>'
        '<span style="font-size:0.65rem; font-weight:600; padding:1px 5px; border-radius:4px; background:rgba(99,102,241,0.2); color:#a5b4fc; border:1px solid rgba(99,102,241,0.3);">AI</span>'
        '</div>'
        '<div style="font-size:0.75rem; color:#64748b; font-weight:500;">Enterprise Operations</div>'
        '</div>'
        '</div>'
        '<div style="margin-top:0.85rem; padding:0.6rem 0.75rem; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; display:flex; align-items:center; justify-content:space-between;">'
        '<div style="display:flex; align-items:center; gap:0.5rem; overflow:hidden;">'
        f'<div style="width:24px; height:24px; border-radius:50%; background:#1e293b; color:#cbd5e1; font-size:0.72rem; font-weight:600; display:flex; align-items:center; justify-content:center; border:1px solid rgba(255,255,255,0.1); flex-shrink:0;">{initials}</div>'
        '<div style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">'
        f'<div style="font-size:0.78rem; font-weight:600; color:#e2e8f0; line-height:1.2;">{display_name}</div>'
        '<div style="font-size:0.68rem; color:#64748b;">Support Operations</div>'
        '</div>'
        '</div>'
        '<div style="display:flex; align-items:center; gap:4px;">'
        '<div style="width:6px; height:6px; border-radius:50%; background:#10b981; box-shadow:0 0 6px #10b981;"></div>'
        '<span style="font-size:0.68rem; color:#10b981; font-weight:500;">Active</span>'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="sf-header-container">
            <h1 class="sf-header-title">{title}</h1>
            <p class="sf-header-subtitle">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

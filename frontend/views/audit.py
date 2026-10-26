import streamlit as st

from frontend.api_client import get
from frontend.components.layout import page_header


def render() -> None:
    page_header("System Audit Logs", "Immutable record of agent tool invocations, policy evaluations, and human governance decisions")
    try:
        rows = get("/api/audit")
    except Exception as exc:
        st.error(str(exc))
        return

    if not rows:
        st.info("No audit trail entries recorded yet.")
        return

    st.markdown(f"**{len(rows)}** total audit trail events")
    st.dataframe(rows, use_container_width=True, hide_index=True)

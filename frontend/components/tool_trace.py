import streamlit as st


def render_tool_trace(tools: list[dict]) -> None:
    if not tools:
        return
    with st.expander(f"System Execution Audit ({len(tools)} tools invoked)", expanded=False):
        for item in tools:
            name = item.get("tool_name", "tool")
            status = (item.get("status") or "success").lower()
            latency = item.get("latency_ms", 0)

            badge_class = "sf-badge-resolved" if status == "success" else "sf-badge-escalated"
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; justify-content:space-between; padding:0.35rem 0; border-bottom:1px solid rgba(255,255,255,0.04);">
                    <div style="display:flex; align-items:center; gap:0.5rem;">
                        <span class="sf-badge {badge_class}">{status.upper()}</span>
                        <code style="font-size:0.82rem; color:#f1f5f9;">{name}()</code>
                    </div>
                    <span style="font-size:0.75rem; color:#64748b;">{latency} ms</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            facts = item.get("facts")
            if isinstance(facts, dict) and facts.get("error"):
                st.caption(f"Error detail: {facts.get('error')}")

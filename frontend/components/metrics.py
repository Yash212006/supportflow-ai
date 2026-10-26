import streamlit as st
import plotly.express as px


# ---------- Colour palette for charts ----------
CHART_COLORS = {
    "indigo":  "#818cf8",
    "violet":  "#a78bfa",
    "teal":    "#2dd4bf",
    "amber":   "#fbbf24",
    "rose":    "#fb7185",
    "sky":     "#38bdf8",
    "emerald": "#34d399",
}

_PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=12),
    margin=dict(t=44, b=24, l=24, r=16),
    height=340,
    xaxis=dict(showgrid=False, color="#94a3b8"),
    yaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.08)", color="#94a3b8"),
)


def metric_row(items: list[tuple[str, object]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value if value is not None else "—")


def bar_chart(data: dict, title: str, color: str = "#818cf8") -> None:
    if not data:
        st.info(f"No data for {title.lower()}.")
        return
    fig = px.bar(
        x=list(data.keys()),
        y=list(data.values()),
        title=title,
    )
    fig.update_traces(
        marker_color=color,
        marker_line_width=0,
        opacity=0.88,
        hovertemplate="%{x}: <b>%{y}</b><extra></extra>",
    )
    fig.update_layout(
        **_PLOTLY_LAYOUT,
        xaxis_title="",
        yaxis_title="Count",
        title_font=dict(size=14, color="#e2e8f0"),
    )
    st.plotly_chart(fig, use_container_width=True)

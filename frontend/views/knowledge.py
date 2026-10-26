import streamlit as st

from frontend.api_client import delete, get, post
from frontend.components.layout import page_header


def render() -> None:
    page_header("Knowledge Base", "Enterprise policies, terms of service, and RAG document indices")
    try:
        docs = get("/api/knowledge/documents")
    except Exception as exc:
        st.error(str(exc))
        return

    st.markdown(f"**{len(docs)}** active documents indexed in vector store")
    st.dataframe(docs, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Document Upload Section
    st.markdown("#### Document Ingestion")
    st.caption("Upload company policy manuals or support PDFs for automated chunking and embedding.")
    uploaded = st.file_uploader("Select Policy PDF", type=["pdf"], label_visibility="collapsed")
    if uploaded and st.button("Index Document", type="primary"):
        files = {"file": (uploaded.name, uploaded.getvalue(), "application/pdf")}
        result = post("/api/knowledge/upload", files=files, timeout=180)
        for step in result.get("steps") or []:
            st.markdown(f'<span class="sf-tag">{step}</span>', unsafe_allow_html=True)
        st.rerun()

    st.markdown("---")

    # Maintenance Section
    st.markdown("#### Index Maintenance & Operations")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Re-index All Documents", use_container_width=True):
            with st.spinner("Re-indexing knowledge base vector store..."):
                result = post("/api/knowledge/reindex", {}, timeout=180)
            st.success(f"Indexed {result.get('chunks', 0)} chunks successfully.")
            st.rerun()
    with c2:
        names = [d["filename"] for d in docs]
        if names:
            victim = st.selectbox("Select document to delete", names, label_visibility="collapsed")
            if st.button("Remove Document", use_container_width=True):
                delete(f"/api/knowledge/documents/{victim}")
                st.success(f"Removed {victim} from index.")
                st.rerun()

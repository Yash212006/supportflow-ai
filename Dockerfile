FROM python:3.11-slim

WORKDIR /app

# System dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data chroma_db knowledge_base uploads

# Copy Streamlit config to where Streamlit expects it (CWD/.streamlit)
RUN mkdir -p .streamlit && cp frontend/.streamlit/config.toml .streamlit/config.toml

# Default environment (secrets like GROQ_API_KEY are set in HF Space Settings)
ENV API_BASE_URL=http://localhost:8000 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DATABASE_URL=sqlite:///./data/supportflow.db \
    CHROMA_PERSIST_DIRECTORY=./chroma_db \
    EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
    RAG_TOP_K=4 \
    LOG_LEVEL=INFO \
    DEMO_USER_EMAIL=exec@supportflow.local \
    DEMO_USER_PASSWORD=demo123

# HF Spaces expects port 7860
EXPOSE 7860

RUN chmod +x start.sh

CMD ["bash", "start.sh"]

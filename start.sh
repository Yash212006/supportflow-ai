#!/bin/bash
set -e

echo "=== SupportFlow AI - Starting services ==="

# Start FastAPI backend in the background
echo "[1/2] Starting FastAPI backend on port 8000..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend to be ready..."
for i in $(seq 1 60); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "Backend is ready!"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "WARNING: Backend did not respond within 60s, starting frontend anyway..."
    fi
    sleep 2
done

# Start Streamlit frontend on port 7860 (HF Spaces default)
echo "[2/2] Starting Streamlit frontend on port 7860..."
streamlit run frontend/app.py \
    --server.port 7860 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false

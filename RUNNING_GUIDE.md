# SupportFlow AI — Local Setup & Execution Guide

This guide walks you through setting up and running **SupportFlow AI** locally on your machine without Docker.

---

## 🛠️ Prerequisites

* **Python 3.10 to 3.13** installed on your system.
* Internet connection (for first-time model and dependency downloads).
* A free **Groq API key** (obtainable from [console.groq.com](https://console.groq.com)).

---

## 🚀 Step-by-Step Setup

### Step 1: Open a Terminal & Navigate to Project

Open PowerShell, Command Prompt, or your IDE terminal:

```bash
cd "c:\Users\yash\Desktop\Summer Intern\supportflow-ai"
```

---

### Step 2: Create & Activate Virtual Environment

If the `venv` folder is not already created:

**Windows (PowerShell or CMD):**
```powershell
python -m venv venv
.\venv\Scripts\activate
```

*(You will see `(venv)` prefixed in your terminal prompt).*

---

### Step 3: Install Dependencies

```powershell
pip install -r requirements.txt
```

---

### Step 4: Configure Environment Variables

Make sure you have a `.env` file in the project root. You can copy the example:

**Windows PowerShell:**
```powershell
Copy-Item .env.example .env
```

Open `.env` in an editor and enter your Groq API key:
```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=sqlite:///./data/supportflow.db
CHROMA_PERSIST_DIRECTORY=./chroma_db
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_TOP_K=4
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://127.0.0.1:8000
LOG_LEVEL=INFO
DEMO_USER_EMAIL=exec@supportflow.local
DEMO_USER_PASSWORD=demo123
```

> **Note:** The project uses local **SQLite** (`./data/supportflow.db`) and local **ChromaDB** (`./chroma_db`) by default. No external database servers or Docker containers are required.

---

### Step 5: Seed the Database & Knowledge Base

Run the seed script to create initial data (customers, orders, tickets, fictional policy PDFs, and index them into vector search):

```powershell
python scripts/seed.py
```

*This will:*
1. Initialize the SQLite database schema.
2. Generate 7 fictional company policy PDFs in `./knowledge_base/`.
3. Ingest and index policies into ChromaDB vectorstore.
4. Populate customers, orders, support tickets, and default demo user.

---

### Step 6: Start the Backend (Terminal 1)

Open **Terminal 1**, activate the virtual environment, and run:

```powershell
.\venv\Scripts\activate
uvicorn backend.main:app --reload --port 8000
```

* **Swagger API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Backend Health Check:** [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

### Step 7: Start the Frontend UI (Terminal 2)

Open a **Second Terminal**, navigate to the project directory, activate the venv, and run:

```powershell
.\venv\Scripts\activate
streamlit run frontend/app.py
```

Streamlit will automatically open in your browser at:
👉 **[http://localhost:8501](http://localhost:8501)**

---

## 🔑 Login Credentials

When the Streamlit app loads, sign in with:
* **Email:** `exec@supportflow.local`
* **Password:** `demo123`

*(Pre-filled by default for quick demo testing).*

---

## 🧪 Demo Test Workflows to Try

Once logged in, open the **AI Copilot** page and test these agent prompts:

1. **Order Status Investigation:**
   > *"Where is order ORD1001?"*
   * **Expected Agent Action:** Calls `get_order` and `get_delivery_status`. Reports delay.

2. **Policy & Refund Eligibility Check:**
   > *"Is customer CUST001 eligible for a refund on order ORD1001?"*
   * **Expected Agent Action:** Calls `get_order`, searches policy via RAG (`search_company_policy`), and evaluates rules.

3. **Human-in-the-Loop Refund Action:**
   > *"Create a refund request for eligible order ORD1001 and ticket TKT1023."*
   * **Expected Agent Action:** Calls `create_refund_request`. Action status becomes `PENDING_APPROVAL`.
   * Go to the **Approvals** tab in the UI to approve or reject the refund. Money is never deducted without human approval!

4. **Automatic Escalation:**
   > *"Refund this ₹80,000 order ORD8801."*
   * **Expected Agent Action:** Identifies high-value threshold (> ₹5,000) and escalates the ticket rather than auto-refunding.

---

## 🔍 Running Tests & Evaluation

To verify system correctness and test suite:

```powershell
pytest
```

To run the offline evaluation harness:

```powershell
python eval/run_eval.py
```
*(Results are saved to `eval/last_results.json` and visible on the Dashboard page).*

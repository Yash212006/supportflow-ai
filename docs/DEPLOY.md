# Deploy a free demo (Render)

## Why Render and not Vercel

SupportFlow AI is a long-running FastAPI server plus PostgreSQL with pgvector plus Redis. AI chat turns can take
up to a minute.

- **Vercel** is great for the React frontend but runs backends as short serverless functions. It has no Docker
  support, no managed Postgres with pgvector or Redis in the same place, and function time limits. You would have to
  rewrite the backend.
- **Render** runs the existing Docker backend as-is. Its free plan includes Postgres (pgvector supported), Key Value
  (Redis) and static sites, and this repo ships a `render.yaml` Blueprint that creates all four in one click. Render
  is also a hackathon sponsor.

Free plan facts:
- The API sleeps after 15 minutes without traffic, and the first request after that takes about a minute.
- The free Postgres database expires 30 days after creation.
- Instances have 512 MB of RAM; the API uses about 160 MB at idle.
- No background workers, so the refund reconciler isn't included. Managers use **Refunds → Reconcile with
  PayPal**.

## Before you start

- The code is in a **GitHub repository** (public is fine) with `render.yaml` at the root.
- Your PayPal Sandbox **client ID** and **secret**, and your **Gemini API key**.
- Never put keys in the repo; you will paste them into Render's dashboard only.

## Step 1: Create everything from the Blueprint

1. Go to https://render.com → **Get Started** → sign up with GitHub.
2. **New +** → **Blueprint** → connect your GitHub account if asked → pick the SupportFlow repository.
3. Render reads `render.yaml` and lists 4 resources: `supportflow-db`, `supportflow-redis`, `supportflow-api`,
   `supportflow-web`. It asks for the values marked `sync: false`:

   | Value | What to enter now |
   | --- | --- |
   | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | from developer.paypal.com → Apps & Credentials → Sandbox |
   | `GEMINI_API_KEY` | your Gemini key |
   | `PAYPAL_WEBHOOK_ID` | leave blank for now (step 4) |
   | `FRONTEND_URL`, `CORS_ORIGINS`, `PUBLIC_API_URL`, `VITE_API_URL` | leave blank for now (step 2) |
   | `VITE_AG_LICENSE_KEY` | blank unless you have an AG Studio licence |

4. Click **Apply**. The first build takes about 5 to 10 minutes. The API runs migrations and loads the labelled
   sample data in USD on its first start.

## Step 2: Connect the frontend and the API

When both services show **Live**, open each one and copy its URL from the top of the page, for example
`https://supportflow-web.onrender.com` and `https://supportflow-api.onrender.com`. Your names may have a suffix.

1. `supportflow-api` → **Environment** → set:
   - `FRONTEND_URL` = the web URL (PayPal sends buyers back here after they pay)
   - `CORS_ORIGINS` = the web URL (exactly the same: `https://`, no trailing `/`)
   - `PUBLIC_API_URL` = the API URL

   Then **Save, rebuild and deploy**.
2. `supportflow-web` → **Environment** → set `VITE_API_URL` = the API URL (no trailing `/`).
   Then **Manual Deploy → Clear build cache & deploy**. This value is baked in at build time, so it must rebuild.

## Step 3: Check it

1. Open `https://<api url>/health`. It should show `"database": true`, `"paypal_configured": true` and
   `"llm_configured": true`. If it's slow, the API is waking up; wait a minute.
2. Open the web URL and use the one-click **Customer** login. Orders and chat should load.
3. Log in as the manager → **Integrations** → **Test AI connection** should say OK.
4. As a customer: **Shop** → item under $50 → **Pay with PayPal** → log in with a Sandbox **personal** account →
   approve. You should come back to the web URL with the order **Paid**.

## Step 4: Live PayPal webhooks (recommended)

1. developer.paypal.com → your Sandbox app → **Add Webhook**.
2. URL: `https://<api url>/api/paypal/webhooks`. Events: `CHECKOUT.ORDER.APPROVED`, `CHECKOUT.ORDER.COMPLETED`,
   all `PAYMENT.CAPTURE.*`, all `PAYMENT.REFUND.*`. Save.
3. Copy the **Webhook ID** → `supportflow-api` → Environment → `PAYPAL_WEBHOOK_ID` → save and deploy.
4. After the next payment, **Manager → Integrations** shows webhooks configured, and incoming events appear as
   verified.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Login shows a network error or CORS error in the browser console | `CORS_ORIGINS` must equal the web URL exactly; `VITE_API_URL` must be set and the web app rebuilt |
| Every page is slow the first time | The free API was asleep; wait about a minute |
| After paying on PayPal you land on `localhost` | `FRONTEND_URL` on the API is still blank or wrong |
| PayPal error 422 about currency | The data must be USD: the Blueprint sets `DEMO_CURRENCY=USD`. If you changed it, set it back |
| Need to wipe the demo data | Delete `supportflow-db` in Render, then **Blueprints → your blueprint → Manual Sync** to recreate it, and redeploy the API. It seeds on start |
| API logs say it ran out of memory | Tell us; as a quick check, set `LLM_PROVIDER=none` to see if the AI libraries are the cause |

Keep the API awake before a live judging session by opening `/health` a minute earlier.

# Demo guide

A 7–10 minute walkthrough. Part 1 works with no credentials (sample data, deterministic mode). Part 2 needs
PayPal Sandbox credentials and shows real money movement in the Sandbox.

Start fresh: `scripts/reset-demo.sh` (or `scripts/reset-demo.sh docker`). Order numbers below are from the seed.

## Part 1: no credentials needed

### 1. The customer asks about an order (1 min)
Log in as **Customer** (Priya) or Arjun (`arjun@customer.demo` / `Customer@123`). Open **AI support chat**:

> Where is my order #1102?   *(as Arjun)*

The reply comes from the database: payment captured, shipment carrier and tracking, delivered. It also says the
payment is **labelled sample data**. A ticket is created and linked.

Ask about someone else's order (e.g. `#1047`) and the assistant says it couldn't find that order on your account.
That is tenant and customer isolation working.

### 2. Three refund requests, three policy outcomes (2 min)
As Arjun:

| Message | What happens |
| --- | --- |
| `Refund order #1068 please, wrong size` (₹7,996) | **Escalated** by Policy C (above ₹5,000). Card says no refund was issued |
| `I want a refund for order #1013, it stopped working` (₹899) | **Requires approval**: outside the product's refund window |

As Meera (`meera@customer.demo`):

| Message | What happens |
| --- | --- |
| `The lamp in order #1074 arrived broken, I want a refund` (₹899) | Policy A allows **auto-execute**, the execution engine revalidates, sees the payment is sample data (no PayPal capture), and **fails honestly**. Nothing is shown as refunded |

Point out the action cards: the status comes from the execution engine, not from the AI's wording.

### 3. The manager's view (2–3 min)
Log in as **Support manager**.

- **Overview:** KPIs and alerts (approvals waiting, failed agent runs, high-priority tickets).
- **Approvals:** open the #1013 request. Show the risk summary, the policy trace (each condition, expected vs actual,
  which rule matched and its version), and the live re-check. Approve it: it fails with "sample data, no PayPal
  capture". Reject another one with a note and show the customer's ticket updates.
- **AI operations:** open the chat run. Each agent step, each tool call with authorization, the policy decision,
  and "Deterministic mode". No chain-of-thought anywhere.
- **Policies:** open Refund Policy v2, change the Policy B upper bound, save → v3 is created. Use **Dry run** on an
  order to see the outcome without executing anything.
- **Manager copilot:** ask "How many refunds are pending approval?" or "Prepare a refund proposal for order #1054".
  The proposal is a dry run; submitting goes through the policy engine.
- **Analytics (AG Studio):** switch between Financial, Support, AI operations and Risk; click **Edit** to change a
  widget and **Save** a layout. Every row carries `data_origin`.
- **Audit log** and **Risk monitor** for governance.

### 4. Isolation (30 s)
Log in as `manager@contoso.demo` / `Demo@12345`: a different business with none of Northwind's data.

## Part 2: with PayPal Sandbox

Set `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` and `DEMO_CURRENCY=USD`, then re-seed (thresholds
become $50 / $250). Have a Sandbox **personal** buyer account ready.

1. **Buy:** as a customer, **Shop** → add a product under $50 → **Place order** → **Pay … with PayPal** → log in with the
   Sandbox buyer → approve. Back in the app, the capture runs and the order shows **Paid** with the PayPal capture id.
   **Payments** shows the PayPal API log for each call.
2. **Auto refund:** in chat, `I want a refund for order #<new order>`. Policy A auto-executes; the card shows
   **Refund completed by PayPal** with the PayPal refund id (or *pending at PayPal* if Sandbox returns PENDING).
3. **Approval refund:** buy something between $50 and $250, request a refund, approve it as the manager. The
   approval re-checks the payment and then calls PayPal.
4. **Duplicate safety:** submit the same refund twice (e.g. double-click, or repeat the API call). Only one PayPal
   refund exists; the second request returns the original action.
5. **Webhooks:** with a public URL, PayPal's `PAYMENT.CAPTURE.*` and refund events arrive verified and update the
   records. Unverified events appear as rejected in the webhook list.

## Part 3: with an LLM key (optional)

Set `LLM_PROVIDER=openai` (or `gemini`) and the key. Chat replies become natural language (still built only from the
fact sheet), the copilot reasons over its tools, and the AG Studio AI panel can build widgets ("Add a line chart of
daily refunded amount"). Decisions are unchanged: the policy engine still decides.

## Talking points

- "The AI proposes, the policy engine decides, PayPal confirms."
- Idempotency key + row lock + `PayPal-Request-Id`: a refund can't happen twice.
- Unknown outcomes stay pending and are reconciled with the same request id, never assumed.
- Sample data is labelled everywhere and can't be refunded.

# Agent architecture

SupportFlow runs six LangGraph agents plus the AG Studio dashboard agent. **No agent holds financial
authority.** Agents can read scoped data and *request* actions; the deterministic policy engine decides, and
the execution engine is the only code that calls PayPal.

## Customer support graph (`app/agents/support_graph.py`)

```
  orchestrator ──► order_investigation ──► policy_intelligence ──► risk_assessment ──► resolution ──► respond
        │                                       ▲                                        ▲
        └──────────────(general / account)──────┘                    (non-refund) ────────┘
```

| Agent | Job | Tools it may call |
| --- | --- | --- |
| **Orchestrator** | Classifies intent (order inquiry, payment failure, refund, delayed shipment, cancellation, product issue, account, general), extracts the order number and amount, handles "talk to a human", routes | `list_customer_orders`, `get_conversation_context`, `create_or_update_ticket` |
| **Order investigation** | Loads the order, payments and shipments and writes a factual finding (e.g. "captured, not shipped") | `list_customer_orders`, `get_order_details`, `get_payment_records`, `get_shipment_records` |
| **Policy intelligence** | Retrieves current knowledge-base passages with citations and loads the active policy | `search_knowledge_base`, `get_active_policy` |
| **Risk assessment** | Runs the deterministic risk scorer (signals, score, level, next step) | `assess_refund_risk` |
| **Resolution** | Chooses the response type and, when appropriate, *requests* an action from the execution engine | `request_refund_action`, `cancel_unpaid_order`, `escalate_ticket`, `resolve_ticket`, `notify_customer` |
| *respond* (node) | Writes the customer-facing reply from structured facts only | none |

The allow-lists live in `app/agents/tooling.py` (`AGENT_PERMISSIONS`). `ToolRunner` refuses any call outside the
list, and records every call, allowed or refused, as an `agent_tool_calls` row.

### Tenant and customer scoping

Tools receive a `ToolContext` with `business_id` and, in customer workflows, `customer_id`. Every tool query
filters on these, so a customer asking about someone else's order number gets "I couldn't find that order on your
account", not a leak.

### What the LLM does and does not do

| Step | With an LLM | Without (deterministic mode) |
| --- | --- | --- |
| Intent classification | Structured output (Pydantic schema) | Keyword/regex classifier (`rule_classify`) |
| Order, payment, shipment facts | Tools (database) | Same tools |
| Policy decision, risk, execution | **Never the LLM** | Same deterministic code |
| Reply wording | Generated from a JSON fact sheet with strict rules ("never claim a refund happened unless resolution says so") | Templated reply |

If the provider fails or times out the step falls back to the deterministic path. The mode used is stored on each
`agent_executions.llm_mode` and shown in the UI ("Deterministic mode"), so nothing pretends to be an LLM.

The customer-facing action card is rendered from the execution engine's state, not from the model's text, so a
model that wrote "your refund is done" could not change what the card says.

## Manager copilot (`app/agents/copilot.py`)

A LangGraph ReAct agent over **read-only, tenant-scoped** tools: `search_orders`, `get_order`,
`search_customers`, `search_payments`, `search_refunds`, `search_tickets`, `list_pending_approvals`,
`get_policies`, `explain_decision`, `get_analytics_summary`, `summarize_agent_executions`, `top_complaints`,
`refund_rate_by_product`, `autonomy_trend`, `prepare_refund_proposal`, `search_knowledge_base`.

`prepare_refund_proposal` only dry-runs the policy engine. The manager submits the proposal through the normal
refund API, where the policy engine and execution engine apply. Without an LLM, the copilot uses a transparent
intent router over the same tools and says so.

## AG Studio dashboard agent (`app/api/routes/studio_ai.py`)

AG Studio's AI harness calls our `SupportFlowStudioAdapter`, which posts the turn to `/api/studio-ai/turn`. The
backend runs the model with **only the tools AG Studio declares** (widgets, pages, data views), executed in the
browser on data the manager already loaded. Tool names starting with `refund`, `payment`, `paypal`, `approve` or
`execute_` are rejected outright. Each turn is recorded as an `agent_executions` row (`workflow=dashboard`).

## Observability

Every run writes an `agent_executions` row (workflow, intent, input summary, outcome, duration, LLM mode, error)
with ordered `steps` (agent, summary, time) and its `agent_tool_calls` (tool, arguments, result summary, success,
authorized). The manager's **AI operations** page lists runs; the execution detail page shows the step timeline,
tool calls and linked policy decision.

**Chain-of-thought is never stored or shown.** Steps hold short summaries written by our code, not model
reasoning.

## Adding an agent or tool

1. Implement the tool in `support_tools.py` or `copilot.py` with a `ToolContext` and scoped queries.
2. Add it to the agent's set in `AGENT_PERMISSIONS`.
3. If it changes money or state, it must go through `ExecutionEngine`; a test should prove it cannot bypass the policy engine.

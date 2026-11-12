# AG Studio integration

Analytics at `/manager/analytics` (staff only) is built on **AG Studio 3.1** (`ag-studio`, `ag-studio-react`), AG
Grid's dashboard product, which embeds AG Grid 36 and AG Charts 14.

## Pieces

| File | Role |
| --- | --- |
| `frontend/src/pages/manager/Analytics.tsx` | Mounts `<AgStudio>`, loads data sources, view/edit mode, page tabs, save/load/delete layouts, AI harness |
| `frontend/src/integrations/ag-studio/dashboards.ts` | `defaultReportState()`: the Financial, Support, AI operations and Risk pages as AG Studio report state |
| `frontend/src/integrations/ag-studio/theme.ts` | `studioTheme.withParams(...)` with SupportFlow colours and font |
| `frontend/src/integrations/ag-studio/supportflowAdapter.ts` | `AgLlmAdapter` that forwards AI turns to the backend |
| `backend/app/analytics/service.py` | `DATASETS`: fixed-column, tenant-scoped datasets |
| `backend/app/api/routes/platform.py` | `GET /api/analytics/datasets`, `/api/dashboards` CRUD |
| `backend/app/api/routes/studio_ai.py` | `GET /api/studio-ai/config`, `POST /api/studio-ai/turn` |

## Data sources

`GET /api/analytics/datasets` returns, for the caller's business only:

| Source id | Contents |
| --- | --- |
| `orders` | orders with customer, status, totals, category, dates |
| `payments` | payment status, amount, refunded amount, source |
| `refunds` | refund amount, status, risk level, policy outcome, auto vs approved |
| `tickets` | ticket category, status, priority, resolved by (AI / human / open), CSAT, resolution hours |
| `agent_executions` | workflow, intent, outcome, LLM mode, duration, autonomy |
| `customers` | per-customer orders, refunds, refund rate |
| `revenue_daily` | captured and refunded amount per day |

Every row has a `data_origin` column (`sample`, `live`, `paypal_sandbox`) so sample data stays visible as such
inside the dashboards. Columns are fixed server-side: names, amounts, statuses and dates only, with no emails, phone numbers, tokens or PayPal credentials.

## Default dashboards

| Page | Widgets |
| --- | --- |
| Financial | captured, refunded, net revenue, payment count; daily captured vs refunded; payment outcomes; revenue by category; monthly revenue; transactions grid |
| Support | tickets, resolved, average resolution hours, escalated; tickets by category; resolved by AI vs human; tickets per month by priority; tickets grid |
| AI operations | executions, resolved autonomously, needed a human, average duration; executions by intent; policy outcomes; executions per day |
| Risk | refund requests, refund volume, auto-executed, average refund ratio; refunds by risk level; policy outcome by status; customers by refund rate; refunds grid |

Widgets use AG Studio's report-state format: `type` (`value`, `grid`, `line-chart`, `column-chart-grouped`,
`bar-chart-grouped`, `donut-chart`), `dataMapping` with `<source>.<field>` references and aggregations, and a
24-column `widgetLayout`.

## Saved layouts

In **Edit** mode a manager can change widgets and pages and **Save** under a name. The state from
`api.getState()` is stored per user in `dashboard_preferences` (`POST /api/dashboards`) and can be reloaded from the
selector, deleted, or reset to the SupportFlow defaults.

## AI agent framework

AG Studio ships no model. When the backend has an LLM configured (`GET /api/studio-ai/config` → `enabled`), the
page calls `createAiHarness(api, { adapter, primary: 'lead', models, promptStarters })` with
`SupportFlowStudioAdapter`. The adapter:

1. posts the `AgLlmRequest` to `POST /api/studio-ai/turn` with the user's JWT (no model key in the browser);
2. receives a complete `AgLlmResponse` and replays it as `TEXT_MESSAGE_*` and `TOOL_CALL_*` events;
3. turns HTTP or network errors into a failed turn instead of inventing output.

The backend accepts only AG Studio's own dashboard tools and rejects any tool name starting with `refund`,
`payment`, `paypal`, `approve` or `execute_`. Tool calls run in the browser on data the manager already has. Each
turn is logged as an agent execution (`workflow=dashboard`). Without an LLM the panel is off and the page says so.

## Licence

Set `VITE_AG_LICENSE_KEY` (build-time, public by design; AG Grid licence keys are meant to ship to the browser).
Without it AG Studio runs with all features and an evaluation watermark, and the page shows a badge saying so.

## Bundle size

AG Studio is lazy-loaded with the Analytics route, so it does not affect other pages. The Analytics chunk is about
6.7 MB minified (AG Studio, Grid and Charts).

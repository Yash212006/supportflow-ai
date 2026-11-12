/**
 * Default SupportFlow dashboards for AG Studio, as AgReportState pages.
 * Field references use `<source id>.<field id>` against the data sources from /api/analytics/datasets.
 * Users can edit these in Studio and save their own versions (persisted server-side via /api/dashboards).
 */
type Ref = { id: string; aggregation?: 'sum' | 'avg' | 'min' | 'max' | 'count' | 'countd' };
type Widget = Record<string, unknown>;

const f = (id: string, aggregation?: Ref['aggregation']): Ref => (aggregation ? { id, aggregation } : { id });
const title = (text: string) => ({ title: { text, enabled: true } });

const kpi = (text: string, value: Ref): Widget => ({ type: 'value', format: title(text), dataMapping: { value: [value] } });
const column = (text: string, category: Ref, values: Ref[], legend?: Ref): Widget => ({ type: 'column-chart-grouped', format: title(text), dataMapping: { categoryKey: [category], valueKey: values, ...(legend ? { legendKey: [legend] } : {}) } });
const line = (text: string, category: Ref, values: Ref[]): Widget => ({ type: 'line-chart', format: title(text), dataMapping: { categoryKey: [category], valueKey: values } });
const donut = (text: string, category: Ref, value: Ref): Widget => ({ type: 'donut-chart', format: title(text), dataMapping: { categoryKey: [category], valueKey: [value] } });
const bar = (text: string, category: Ref, values: Ref[]): Widget => ({ type: 'bar-chart-grouped', format: title(text), dataMapping: { categoryKey: [category], valueKey: values } });
const grid = (text: string, cols: Ref[]): Widget => ({ type: 'grid', format: title(text), dataMapping: { cols } });

type Cell = [Widget, number, number, number, number]; // widget, x, y, w, h (24-column grid)

function page(id: string, cells: Cell[]) {
  const widgets: Record<string, Widget> = {};
  const widgetLayout: Record<string, { xTrack: number; yTrack: number; xSpan: number; ySpan: number }> = {};
  cells.forEach(([w, x, y, xs, ys], i) => {
    const wid = `${id}-w${i + 1}`;
    widgets[wid] = w;
    widgetLayout[wid] = { xTrack: x, yTrack: y, xSpan: xs, ySpan: ys };
  });
  return { id, widgets, widgetLayout };
}

export const DASHBOARD_PAGES = [
  { id: 'financial', label: 'Financial' },
  { id: 'support', label: 'Support' },
  { id: 'ai-ops', label: 'AI operations' },
  { id: 'risk', label: 'Risk' },
] as const;

export function defaultReportState() {
  return {
    selectedPageId: 'financial',
    pages: [
      page('financial', [
        [kpi('Captured revenue', f('payments.captured_amount', 'sum')), 0, 0, 6, 5],
        [kpi('Refunded', f('payments.refunded_amount', 'sum')), 6, 0, 6, 5],
        [kpi('Net revenue', f('payments.net_amount', 'sum')), 12, 0, 6, 5],
        [kpi('Payments', f('payments.payment_id', 'count')), 18, 0, 6, 5],
        [line('Daily captured vs refunded', f('revenue_daily.date'), [f('revenue_daily.captured', 'sum'), f('revenue_daily.refunded', 'sum')]), 0, 5, 16, 11],
        [donut('Payment outcomes', f('payments.outcome'), f('payments.payment_id', 'count')), 16, 5, 8, 11],
        [column('Revenue by category', f('payments.category'), [f('payments.captured_amount', 'sum'), f('payments.refunded_amount', 'sum')]), 0, 16, 12, 11],
        [column('Monthly revenue', f('payments.month'), [f('payments.net_amount', 'sum')]), 12, 16, 12, 11],
        [grid('Transactions', [f('payments.order_number'), f('payments.customer'), f('payments.status'), f('payments.amount'), f('payments.refunded_amount'), f('payments.created_date'), f('payments.data_origin')]), 0, 27, 24, 12],
      ]),
      page('support', [
        [kpi('Tickets', f('tickets.ticket_number', 'count')), 0, 0, 6, 5],
        [kpi('Resolved', f('tickets.is_resolved', 'sum')), 6, 0, 6, 5],
        [kpi('Avg. resolution hours', f('tickets.resolution_hours', 'avg')), 12, 0, 6, 5],
        [kpi('Escalated', f('tickets.is_escalated', 'sum')), 18, 0, 6, 5],
        [bar('Tickets by category', f('tickets.category'), [f('tickets.ticket_number', 'count')]), 0, 5, 12, 12],
        [donut('Resolved by', f('tickets.resolved_by'), f('tickets.ticket_number', 'count')), 12, 5, 12, 12],
        [column('Tickets per month by priority', f('tickets.month'), [f('tickets.ticket_number', 'count')], f('tickets.priority')), 0, 17, 24, 11],
        [grid('Tickets', [f('tickets.ticket_number'), f('tickets.customer'), f('tickets.category'), f('tickets.status'), f('tickets.priority'), f('tickets.resolved_by'), f('tickets.csat'), f('tickets.data_origin')]), 0, 28, 24, 12],
      ]),
      page('ai-ops', [
        [kpi('Agent executions', f('agent_executions.execution_id', 'count')), 0, 0, 6, 5],
        [kpi('Resolved autonomously', f('agent_executions.autonomous', 'sum')), 6, 0, 6, 5],
        [kpi('Needed a human', f('agent_executions.human_required', 'sum')), 12, 0, 6, 5],
        [kpi('Avg. duration (ms)', f('agent_executions.duration_ms', 'avg')), 18, 0, 6, 5],
        [column('Executions by intent', f('agent_executions.intent'), [f('agent_executions.autonomous', 'sum'), f('agent_executions.human_required', 'sum')]), 0, 5, 14, 12],
        [donut('Policy outcomes', f('agent_executions.decision_outcome'), f('agent_executions.execution_id', 'count')), 14, 5, 10, 12],
        [line('Executions per day', f('agent_executions.created_date'), [f('agent_executions.execution_id', 'count'), f('agent_executions.failed', 'sum')]), 0, 17, 24, 11],
      ]),
      page('risk', [
        [kpi('Refund requests', f('refunds.refund_id', 'count')), 0, 0, 6, 5],
        [kpi('Refund volume', f('refunds.amount', 'sum')), 6, 0, 6, 5],
        [kpi('Auto-executed', f('refunds.auto_executed', 'sum')), 12, 0, 6, 5],
        [kpi('Avg. refund ratio', f('refunds.refund_ratio', 'avg')), 18, 0, 6, 5],
        [donut('Refunds by risk level', f('refunds.risk_level'), f('refunds.refund_id', 'count')), 0, 5, 8, 12],
        [column('Policy outcome by status', f('refunds.policy_outcome'), [f('refunds.refund_id', 'count')], f('refunds.status')), 8, 5, 16, 12],
        [bar('Customers by refund rate', f('customers.customer'), [f('customers.refund_rate', 'max')]), 0, 17, 12, 12],
        [grid('Refunds', [f('refunds.order_number'), f('refunds.customer'), f('refunds.amount'), f('refunds.risk_level'), f('refunds.policy_outcome'), f('refunds.status'), f('refunds.paypal_status'), f('refunds.data_origin')]), 12, 17, 12, 12],
      ]),
    ],
  };
}

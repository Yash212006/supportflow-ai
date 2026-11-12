import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useApi } from '@/lib/queries';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { DataTable } from '@/components/ui/table';
import { PageHeader, Skeleton } from '@/components/ui/misc';
import { money, pct } from '@/lib/utils';
import { useAuth } from '@/stores/auth';

interface Row { refund_id: string; order_number: number; customer: string; amount: number; order_value: number; refund_ratio: number; status: string; policy_outcome: string; risk_level: string; reason: string; created_date: string; data_origin: string }
interface RiskResp { high_risk_refunds: Row[]; repeat_requesters: { customer: string; refund_requests: number }[]; refund_spikes: { date: string; refunds: number; baseline: number }[]; manual_review_queue: Row[] }

export default function Risk() {
  const cur = useAuth((s) => s.user?.currency) ?? 'USD';
  const { data, isLoading } = useApi<RiskResp>(['risk'], '/api/analytics/risk');
  if (isLoading || !data) return <Skeleton className="h-96" />;
  const cols = [
    { key: 'o', header: 'Order', cell: (r: Row) => <span className="font-medium">#{r.order_number} <SampleBadge show={r.data_origin === 'sample'} /></span> },
    { key: 'c', header: 'Customer', cell: (r: Row) => r.customer },
    { key: 'a', header: 'Amount', align: 'right' as const, cell: (r: Row) => money(r.amount, cur) },
    { key: 'rr', header: 'Of order', align: 'right' as const, cell: (r: Row) => pct(r.refund_ratio) },
    { key: 'r', header: 'Risk', cell: (r: Row) => <StatusBadge status={r.risk_level} /> },
    { key: 'p', header: 'Policy', cell: (r: Row) => <StatusBadge status={r.policy_outcome} /> },
    { key: 's', header: 'Status', cell: (r: Row) => <StatusBadge status={r.status} /> },
    { key: 'd', header: 'Date', cell: (r: Row) => r.created_date },
  ];
  return (
    <div>
      <PageHeader title="Risk monitor" description="Signals computed by the risk assessment agent. Risk can block auto-execution but never approves anything by itself." actions={<Link to="/manager/approvals" className="text-sm font-medium text-brand-600 hover:underline">Go to approvals</Link>} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Repeat refund requesters" description="Last 90 days" />
          <CardBody className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.repeat_requesters} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid stroke="#e2e8f0" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="customer" width={110} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="refund_requests" name="Requests" fill="#f59e0b" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Refund spikes" description="Days with refunds well above the daily baseline" />
          <CardBody>
            {!data.refund_spikes.length ? <p className="text-sm text-muted">No spikes detected.</p> : (
              <ul className="space-y-2">{data.refund_spikes.map((s) => <li key={s.date} className="flex items-center justify-between rounded-lg bg-amber-50 px-3 py-2 text-sm"><span className="font-medium">{s.date}</span><span>{s.refunds} refunds <span className="text-muted">vs baseline {s.baseline}</span></span></li>)}</ul>
            )}
          </CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="High-risk refunds" />
          <DataTable rows={data.high_risk_refunds} rowKey={(r) => r.refund_id} columns={cols} empty="No high-risk refunds." />
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Manual review queue" />
          <DataTable rows={data.manual_review_queue} rowKey={(r) => r.refund_id} columns={cols} empty="Queue is empty." />
        </Card>
      </div>
    </div>
  );
}

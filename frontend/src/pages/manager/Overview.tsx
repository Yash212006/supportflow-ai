import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle, Bot, CreditCard, LifeBuoy, ReceiptText, Smile, Timer, Wallet } from 'lucide-react';
import { useApi } from '@/lib/queries';
import type { Overview as O } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { ErrorState, PageHeader, Skeleton, Stat, Tabs } from '@/components/ui/misc';
import { money, pct } from '@/lib/utils';

export default function Overview() {
  const [days, setDays] = useState<'7' | '30' | '90'>('30');
  const { data: d, isLoading, error, refetch } = useApi<O>(['overview', days], `/api/analytics/overview?days=${days}`);
  if (error) return <ErrorState error={error} retry={refetch} />;
  const cur = d?.currency ?? 'USD';
  return (
    <div>
      <PageHeader title="Operations overview" description="Includes seeded sample data (labelled) and any live PayPal Sandbox activity." actions={<Tabs value={days} onChange={setDays} tabs={[{ value: '7', label: '7d' }, { value: '30', label: '30d' }, { value: '90', label: '90d' }]} />} />
      {!!d?.alerts?.length && (
        <div className="mb-6 grid gap-3 md:grid-cols-3">
          {d.alerts.map((a, i) => (
            <Link key={i} to={a.link ?? '#'} className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm hover:shadow-sm ${a.level === 'danger' ? 'border-rose-200 bg-rose-50 text-rose-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
              <AlertTriangle className="h-4 w-4 shrink-0" /> <span className="font-medium">{a.title}</span>
            </Link>
          ))}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {isLoading || !d ? [...Array(8)].map((_, i) => <Skeleton key={i} className="h-28" />) : (
          <>
            <Stat label="Captured revenue" value={money(d.revenue, cur)} hint={`Net of refunds ${money(d.net_revenue, cur)}`} icon={<Wallet className="h-4 w-4" />} tone="good" />
            <Stat label="Payment success rate" value={pct(d.payment_success_rate, 1)} hint={`${d.total_payments} payments · ${d.failed_payments} failed`} icon={<CreditCard className="h-4 w-4" />} tone={d.payment_success_rate < 0.9 ? 'warn' : 'good'} />
            <Stat label="Refund rate" value={pct(d.refund_rate, 1)} hint={`${d.refund_count} refunds · ${money(d.refund_volume, cur)}`} icon={<ReceiptText className="h-4 w-4" />} tone={d.refund_rate > 0.08 ? 'warn' : 'default'} />
            <Stat label="Pending approvals" value={d.pending_approvals} hint="Refunds waiting for a manager" icon={<AlertTriangle className="h-4 w-4" />} tone={d.pending_approvals ? 'warn' : 'default'} />
            <Stat label="Open tickets" value={d.open_tickets} hint={`${d.resolved_tickets} resolved · ${pct(d.escalation_rate)} escalated`} icon={<LifeBuoy className="h-4 w-4" />} />
            <Stat label="Avg. resolution time" value={`${d.avg_resolution_hours.toFixed(1)} h`} icon={<Timer className="h-4 w-4" />} />
            <Stat label="AI autonomous resolution" value={pct(d.ai_autonomous_rate)} hint={`${d.ai_executions} agent runs · ${pct(d.ai_human_rate)} needed a human`} icon={<Bot className="h-4 w-4" />} tone="good" />
            <Stat label="Customer satisfaction" value={d.csat ? `${d.csat.toFixed(2)} / 5` : '—'} icon={<Smile className="h-4 w-4" />} />
          </>
        )}
      </div>
      <Card className="mt-6">
        <CardHeader title="Captured vs refunded" description="Daily, business currency" action={<Link to="/manager/analytics" className="text-xs font-medium text-brand-600 hover:underline">Open in AG Studio</Link>} />
        <CardBody className="h-72">
          {d && (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={d.series} margin={{ left: 8, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="cap" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} /><stop offset="100%" stopColor="#6366f1" stopOpacity={0} /></linearGradient>
                  <linearGradient id="ref" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f43f5e" stopOpacity={0.3} /><stop offset="100%" stopColor="#f43f5e" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} width={64} tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v))} />
                <Tooltip formatter={(v) => money(Number(v), cur)} />
                <Area type="monotone" dataKey="captured" name="Captured" stroke="#6366f1" fill="url(#cap)" strokeWidth={2} />
                <Area type="monotone" dataKey="refunded" name="Refunded" stroke="#f43f5e" fill="url(#ref)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, LifeBuoy, MessageSquareText, Package, Sparkles } from 'lucide-react';
import { useApi } from '@/lib/queries';
import type { Order, Refund, Ticket } from '@/lib/types';
import { Card, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { PageHeader, Skeleton, Stat, ErrorState } from '@/components/ui/misc';
import { useAuth } from '@/stores/auth';
import { ago, money } from '@/lib/utils';

interface Dash { recent_orders: Order[]; open_tickets: Ticket[]; recent_refunds: Refund[]; recent_conversations: { id: string; title: string; updated_at: string }[]; stats: { total_orders: number; open_tickets: number; unread_notifications: number } }

export default function CustomerDashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { data, isLoading, error, refetch } = useApi<Dash>(['customer', 'dashboard'], '/api/customer/dashboard');
  if (error) return <ErrorState error={error} retry={refetch} />;
  return (
    <div>
      <PageHeader title={`Hi ${user?.full_name?.split(' ')[0] ?? ''} 👋`} description="Track orders, payments and refunds, or ask our AI assistant for help." actions={<Button onClick={() => nav('/customer/chat')}><MessageSquareText className="h-4 w-4" /> Get help</Button>} />
      <div className="mb-6 overflow-hidden rounded-xl bg-gradient-to-r from-brand-600 to-violet-600 p-6 text-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-white/15"><Sparkles className="h-5 w-5" /></span>
            <div>
              <p className="font-semibold">Need a refund, a delivery update or help with a payment?</p>
              <p className="mt-0.5 text-sm text-brand-100">Our assistant checks your order, applies the refund policy, and tells you exactly what happens next.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {['Where is my order?', 'I want a refund', 'My payment failed'].map((q) => (
              <button key={q} onClick={() => nav('/customer/chat', { state: { prefill: q } })} className="rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium hover:bg-white/25">{q}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        {isLoading ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />) : (
          <>
            <Stat label="Orders" value={data?.stats.total_orders ?? 0} icon={<Package className="h-4 w-4" />} />
            <Stat label="Open tickets" value={data?.stats.open_tickets ?? 0} icon={<LifeBuoy className="h-4 w-4" />} tone={data?.stats.open_tickets ? 'warn' : 'default'} />
            <Stat label="Unread notifications" value={data?.stats.unread_notifications ?? 0} />
          </>
        )}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Recent orders" action={<Link to="/customer/orders" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>} />
          <ul className="divide-y divide-line">
            {data?.recent_orders.map((o) => (
              <li key={o.id}>
                <Link to={`/customer/orders/${o.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">Order #{o.order_number} <SampleBadge show={o.is_sample} /></p>
                    <p className="truncate text-xs text-muted">{o.items_summary}</p>
                  </div>
                  <span className="text-sm tabular-nums">{money(o.total_amount, o.currency)}</span>
                  <StatusBadge status={o.status} />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Open tickets" action={<Link to="/customer/tickets" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>} />
            <ul className="divide-y divide-line">
              {!data?.open_tickets.length && <li className="px-5 py-6 text-center text-sm text-muted">No open tickets.</li>}
              {data?.open_tickets.slice(0, 4).map((t) => (
                <li key={t.id}>
                  <Link to={`/customer/tickets/${t.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{t.subject}</p>
                      <p className="text-xs text-muted">#{t.ticket_number} · updated {ago(t.updated_at)}</p>
                    </div>
                    <StatusBadge status={t.status} />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <CardHeader title="Recent conversations" />
            <ul className="divide-y divide-line">
              {!data?.recent_conversations.length && <li className="px-5 py-6 text-center text-sm text-muted">No conversations yet.</li>}
              {data?.recent_conversations.slice(0, 4).map((c) => (
                <li key={c.id}>
                  <Link to={`/customer/chat/${c.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50">
                    <MessageSquareText className="h-4 w-4 text-slate-400" />
                    <span className="min-w-0 flex-1 truncate text-sm">{c.title}</span>
                    <span className="text-xs text-muted">{ago(c.updated_at)}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

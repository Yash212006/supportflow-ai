import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApi, useAction } from '@/lib/queries';
import { patch } from '@/lib/api';
import type { Ticket } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { Select, Textarea } from '@/components/ui/input';
import { KeyValue, PageHeader, Skeleton } from '@/components/ui/misc';
import { MessageBubble } from '@/pages/customer/Chat';
import { Timeline } from '@/pages/customer/TicketDetail';
import { dateTime, humanize, money } from '@/lib/utils';

export default function TicketDetail() {
  const { id } = useParams();
  const { data: t, isLoading } = useApi<Ticket>(['ticket', id], `/api/tickets/${id}`);
  const { data: staff } = useApi<{ id: string; full_name: string; role: string }[]>(['staff'], '/api/staff');
  const [reply, setReply] = useState('');
  const [note, setNote] = useState('');
  const upd = useAction((body: Record<string, unknown>) => patch(`/api/tickets/${id}`, body), { invalidate: [['ticket', id], ['/api/tickets']], success: 'Ticket updated' });
  if (isLoading || !t) return <Skeleton className="h-96" />;
  return (
    <div>
      <PageHeader title={<span className="flex flex-wrap items-center gap-2">#{t.ticket_number} {t.subject} <StatusBadge status={t.status} /> <SampleBadge show={t.is_sample} /></span>} description={`${t.customer_name} · opened ${dateTime(t.created_at)}`} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Conversation" description="Customer, AI assistant and staff messages" />
            <CardBody className="space-y-5 bg-slate-50/50">
              {!t.messages?.length && <p className="text-sm text-muted">{t.description}</p>}
              {t.messages?.map((m) => <MessageBubble key={m.id} m={m} />)}
            </CardBody>
            <div className="space-y-2 border-t border-line p-4">
              <Textarea value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Reply to the customer…" />
              <div className="flex justify-end"><Button disabled={!reply.trim()} loading={upd.isPending} onClick={async () => { await upd.mutateAsync({ reply_to_customer: reply }); setReply(''); }}>Send reply</Button></div>
            </div>
          </Card>
          <Card>
            <CardHeader title="Timeline" />
            <CardBody><Timeline events={t.events ?? []} /></CardBody>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Manage" />
            <CardBody className="space-y-3">
              <label className="block text-xs text-muted">Status
                <Select className="mt-1" value={t.status} onChange={(e) => upd.mutate({ status: e.target.value })}>
                  {['OPEN', 'IN_PROGRESS', 'WAITING_ON_CUSTOMER', 'ESCALATED', 'RESOLVED', 'CLOSED'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                </Select>
              </label>
              <label className="block text-xs text-muted">Priority
                <Select className="mt-1" value={t.priority} onChange={(e) => upd.mutate({ priority: e.target.value })}>
                  {['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                </Select>
              </label>
              <label className="block text-xs text-muted">Assignee
                <Select className="mt-1" value={t.assigned_to_user_id ?? ''} onChange={(e) => e.target.value && upd.mutate({ assigned_to_user_id: e.target.value })}>
                  <option value="">Unassigned</option>
                  {staff?.filter((s) => s.role !== 'CUSTOMER').map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
                </Select>
              </label>
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Internal note (not visible to customer)" />
              <Button variant="secondary" className="w-full" disabled={!note.trim()} onClick={async () => { await upd.mutateAsync({ note }); setNote(''); }}>Add note</Button>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Context" />
            <CardBody className="space-y-4">
              <KeyValue items={[["Customer", t.customer ? <Link className="text-brand-600 hover:underline" to={`/manager/customers/${t.customer.id}`}>{t.customer.full_name}</Link> : t.customer_name], ["Email", t.customer?.email], ["Category", humanize(t.category)], ["AI confidence", t.ai_classification_confidence ? `${(t.ai_classification_confidence * 100).toFixed(0)}%` : '—'], ["Order", t.order ? <Link className="text-brand-600 hover:underline" to={`/manager/orders/${t.order.id}`}>#{t.order.order_number} · {money(t.order.total_amount, t.order.currency)}</Link> : '—'], ["Resolved by", t.resolved_by ?? '—']]} />
              {!!t.refunds?.length && (
                <div className="space-y-1.5 border-t border-line pt-3">
                  <p className="text-xs font-medium text-muted">Refunds</p>
                  {t.refunds.map((r) => <div key={r.id} className="flex items-center justify-between text-sm"><span>{money(r.amount, r.currency)}</span><StatusBadge status={r.status} /></div>)}
                </div>
              )}
              {!!t.executions?.length && (
                <div className="space-y-1.5 border-t border-line pt-3">
                  <p className="text-xs font-medium text-muted">Agent runs</p>
                  {t.executions.map((e) => <Link key={e.id} to={`/manager/ai-operations/${e.id}`} className="flex items-center justify-between text-sm hover:text-brand-600"><span>{humanize(e.intent)}</span><span className="text-xs text-muted">{dateTime(e.created_at)}</span></Link>)}
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

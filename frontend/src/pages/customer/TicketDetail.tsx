import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Star } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { Ticket } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/input';
import { KeyValue, PageHeader, Skeleton } from '@/components/ui/misc';
import { dateTime, humanize } from '@/lib/utils';

export function Timeline({ events }: { events: { id: string; actor: string; event: string; detail: string | null; created_at: string }[] }) {
  return (
    <ol className="relative space-y-4 border-l border-line pl-5">
      {events.map((e) => (
        <li key={e.id} className="relative">
          <span className="absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-500 ring-1 ring-brand-200" />
          <p className="text-sm"><span className="font-medium">{humanize(e.event)}</span> <span className="text-muted">by {e.actor.replace(/^agent:/, 'AI ').replace(/^user:.*/, 'staff')}</span></p>
          {e.detail && <p className="mt-0.5 text-sm text-slate-600">{e.detail}</p>}
          <p className="text-xs text-muted">{dateTime(e.created_at)}</p>
        </li>
      ))}
    </ol>
  );
}

export default function CustomerTicketDetail() {
  const { id } = useParams();
  const { data: t, isLoading } = useApi<Ticket>(['customer', 'ticket', id], `/api/customer/tickets/${id}`);
  const [reason, setReason] = useState('');
  const inv = [['customer']];
  const reopen = useAction(() => post(`/api/customer/tickets/${id}/reopen`, { reason }), { invalidate: inv, success: 'Ticket reopened' });
  const escalate = useAction(() => post(`/api/customer/tickets/${id}/escalate`, { reason }), { invalidate: inv, success: 'Escalated to our team' });
  const rate = useAction((s: number) => post(`/api/customer/tickets/${id}/rate?score=${s}`), { invalidate: inv, success: 'Thanks for the feedback' });
  if (isLoading || !t) return <Skeleton className="h-96" />;
  const closed = ['RESOLVED', 'CLOSED'].includes(t.status);
  return (
    <div>
      <PageHeader title={<span className="flex items-center gap-2">#{t.ticket_number} {t.subject} <StatusBadge status={t.status} /></span>} description={`Opened ${dateTime(t.created_at)}`} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Activity" />
          <CardBody><Timeline events={t.events ?? []} /></CardBody>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Details" />
            <CardBody>
              <KeyValue items={[["Category", humanize(t.category)], ["Priority", <StatusBadge status={t.priority} />], ["Resolved by", t.resolved_by ? humanize(t.resolved_by) : '—'], ["Order", t.order_id ? <Link className="text-brand-600 hover:underline" to={`/customer/orders/${t.order_id}`}>View order</Link> : '—']]} />
              {t.resolution_summary && <p className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">{t.resolution_summary}</p>}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={closed ? 'Not resolved?' : 'Need more help?'} />
            <CardBody className="space-y-3">
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Tell us what's still wrong (optional)" />
              <div className="flex gap-2">
                {closed ? <Button variant="secondary" loading={reopen.isPending} onClick={() => reopen.mutate(undefined)}>Reopen</Button> : null}
                {t.status !== 'ESCALATED' && <Button variant="secondary" loading={escalate.isPending} onClick={() => escalate.mutate(undefined)}>Talk to a human</Button>}
              </div>
              {closed && (
                <div className="border-t border-line pt-3">
                  <p className="text-xs text-muted">Rate this resolution</p>
                  <div className="mt-1 flex gap-1">
                    {[1, 2, 3, 4, 5].map((s) => (
                      <button key={s} onClick={() => rate.mutate(s)} aria-label={`${s} stars`}><Star className={`h-5 w-5 ${(t.satisfaction_score ?? 0) >= s ? 'fill-amber-400 text-amber-400' : 'text-slate-300'}`} /></button>
                    ))}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

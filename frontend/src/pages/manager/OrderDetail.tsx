import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { ActionCard, Order } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge, SampleBadge, SandboxBadge } from '@/components/ui/badge';
import { Field, Input, Textarea } from '@/components/ui/input';
import { DataTable } from '@/components/ui/table';
import { KeyValue, Modal, Notice, PageHeader, Skeleton } from '@/components/ui/misc';
import { ActionResultCard } from '@/components/ActionCard';
import { dateOnly, dateTime, humanize, money } from '@/lib/utils';

export default function OrderDetail() {
  const { id } = useParams();
  const { data: o, isLoading } = useApi<Order>(['order', id], `/api/orders/${id}`);
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [result, setResult] = useState<ActionCard | null>(null);
  const refund = useAction(() => post<ActionCard>('/api/refunds', { order_id: id, amount: amount ? Number(amount) : null, reason }), { invalidate: [['order', id], ['/api/refunds']] });
  if (isLoading || !o) return <Skeleton className="h-96" />;
  const pay = o.payments?.[o.payments.length - 1];
  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Order #{o.order_number} <StatusBadge status={o.status} /> <SampleBadge show={o.is_sample} /></span>}
        description={`${o.customer_name} · placed ${dateTime(o.placed_at)}`}
        actions={pay && ['CAPTURED', 'PARTIALLY_REFUNDED'].includes(pay.status) && <Button variant="secondary" onClick={() => { setResult(null); setOpen(true); }}>Propose refund</Button>}
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Items" />
            <DataTable rows={o.items ?? []} rowKey={(i) => i.id} columns={[
              { key: 'n', header: 'Product', cell: (i) => <span>{i.product_name} <span className="text-xs text-muted">{i.sku}</span></span> },
              { key: 'c', header: 'Category', cell: (i) => i.category },
              { key: 'q', header: 'Qty', align: 'right', cell: (i) => i.quantity },
              { key: 'p', header: 'Line total', align: 'right', cell: (i) => money(Number(i.unit_price) * i.quantity, o.currency) },
            ]} />
          </Card>
          <Card>
            <CardHeader title="Payments" />
            <DataTable rows={o.payments ?? []} rowKey={(p) => p.id} empty="No payment attempts." columns={[
              { key: 'a', header: 'Attempt', cell: (p) => <Link className="font-medium text-brand-600 hover:underline" to={`/manager/payments/${p.id}`}>#{p.attempt}</Link> },
              { key: 's', header: 'Source', cell: (p) => (p.is_sample ? <SampleBadge /> : <SandboxBadge />) },
              { key: 'st', header: 'Status', cell: (p) => <StatusBadge status={p.status} /> },
              { key: 'c', header: 'Capture', cell: (p) => <code className="text-xs">{p.paypal_capture_id ?? '—'}</code> },
              { key: 'r', header: 'Refunded', align: 'right', cell: (p) => money(p.refunded_amount, p.currency) },
              { key: 'am', header: 'Amount', align: 'right', cell: (p) => money(p.amount, p.currency) },
            ]} />
          </Card>
          {!!o.refunds?.length && (
            <Card>
              <CardHeader title="Refunds" />
              <DataTable rows={o.refunds} rowKey={(r) => r.id} columns={[
                { key: 'a', header: 'Amount', cell: (r) => money(r.amount, r.currency) },
                { key: 's', header: 'Status', cell: (r) => <StatusBadge status={r.status} /> },
                { key: 'p', header: 'PayPal refund', cell: (r) => <code className="text-xs">{r.paypal_refund_id ?? '—'}</code> },
                { key: 'd', header: 'Requested', cell: (r) => dateTime(r.created_at) },
              ]} />
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Customer" />
            <CardBody><KeyValue items={[["Name", o.customer ? <Link className="text-brand-600 hover:underline" to={`/manager/customers/${o.customer.id}`}>{o.customer.full_name}</Link> : o.customer_name], ["Email", o.customer?.email], ["City", o.customer?.city], ["Segment", humanize(o.customer?.segment)]]} /></CardBody>
          </Card>
          <Card>
            <CardHeader title="Shipment" />
            <CardBody>{o.shipments?.map((s) => <KeyValue key={s.id} items={[["Carrier", s.carrier], ["Tracking", s.tracking_number], ["Status", <StatusBadge status={s.status} />], ["ETA", dateOnly(s.estimated_delivery)], ["Last event", s.last_event]]} />) ?? null}{!o.shipments?.length && <p className="text-sm text-muted">No shipment.</p>}</CardBody>
          </Card>
          {!!o.tickets?.length && (
            <Card>
              <CardHeader title="Tickets" />
              <ul className="divide-y divide-line">{o.tickets.map((t) => <li key={t.id}><Link to={`/manager/tickets/${t.id}`} className="flex items-center justify-between px-5 py-2.5 text-sm hover:bg-slate-50"><span className="truncate">#{t.ticket_number} {t.subject}</span><StatusBadge status={t.status} /></Link></li>)}</ul>
            </Card>
          )}
        </div>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title={`Propose refund — order #${o.order_number}`} footer={result ? <Button onClick={() => setOpen(false)}>Done</Button> : <><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={reason.trim().length < 3} loading={refund.isPending} onClick={async () => setResult(await refund.mutateAsync(undefined))}>Submit to policy engine</Button></>}>
        {result ? <ActionResultCard card={{ ...result, kind: 'refund' }} staff /> : (
          <div className="space-y-4">
            <Notice>Staff refunds go through the same policy engine and execution engine as AI refunds.</Notice>
            {pay?.is_sample && <Notice tone="warning">This payment is sample data; PayPal cannot refund it.</Notice>}
            <Field label="Amount (empty = full refundable)" hint={`Refundable ${money(pay?.refundable_amount, o.currency)}`}><Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
            <Field label="Reason"><Textarea value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          </div>
        )}
      </Modal>
    </div>
  );
}

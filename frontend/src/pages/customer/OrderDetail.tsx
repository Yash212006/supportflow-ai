import { useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { CreditCard, MessageSquareText, Truck } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { ActionCard, Order, Payment } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge, SampleBadge, SandboxBadge } from '@/components/ui/badge';
import { Field, Input, Textarea } from '@/components/ui/input';
import { Modal, Notice, PageHeader, Skeleton, KeyValue } from '@/components/ui/misc';
import { ActionResultCard } from '@/components/ActionCard';
import { dateOnly, dateTime, money } from '@/lib/utils';

export default function CustomerOrderDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const { data: o, isLoading } = useApi<Order>(['customer', 'order', id], `/api/customer/orders/${id}`);
  const [refundOpen, setRefundOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [result, setResult] = useState<ActionCard | null>(null);
  const pay = useAction(() => post<Payment>(`/api/customer/orders/${id}/pay`), { invalidate: [['customer']] });
  const refund = useAction(() => post<ActionCard>('/api/customer/refunds', { order_id: id, amount: amount ? Number(amount) : null, reason }), { invalidate: [['customer']] });

  if (isLoading || !o) return <Skeleton className="h-96" />;
  const payment = o.payments?.[o.payments.length - 1];
  const canRefund = payment && ['CAPTURED', 'PARTIALLY_REFUNDED'].includes(payment.status) && Number(payment.refundable_amount) > 0;
  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Order #{o.order_number} <StatusBadge status={o.status} /> <SampleBadge show={o.is_sample} /></span>}
        description={`Placed ${dateTime(o.placed_at)}`}
        actions={
          <>
            <Button variant="secondary" onClick={() => nav('/customer/chat', { state: { prefill: `I need help with order #${o.order_number}` } })}><MessageSquareText className="h-4 w-4" /> Ask AI support</Button>
            {canRefund && <Button variant="secondary" onClick={() => { setResult(null); setRefundOpen(true); }}>Request refund</Button>}
          </>
        }
      />
      {(loc.state as { justPlaced?: boolean } | null)?.justPlaced && o.status === 'PENDING_PAYMENT' && <Notice tone="success" className="mb-4" title="Order placed">Pay with PayPal to confirm it.</Notice>}
      {o.status === 'PENDING_PAYMENT' && (
        <Card className="mb-6 border-brand-100 bg-brand-50/40">
          <CardBody className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 font-medium">Payment required <SandboxBadge /></p>
              <p className="text-sm text-muted">You'll approve the payment on PayPal's sandbox site, then we capture it. The status shown here comes from PayPal's response.</p>
            </div>
            <Button size="lg" loading={pay.isPending} onClick={async () => {
              const p = await pay.mutateAsync(undefined);
              if (p.approve_url) window.location.href = p.approve_url;
            }}>
              <CreditCard className="h-4 w-4" /> Pay {money(o.total_amount, o.currency)} with PayPal
            </Button>
          </CardBody>
        </Card>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Items" />
          <ul className="divide-y divide-line">
            {o.items?.map((i) => (
              <li key={i.id} className="flex justify-between px-5 py-3 text-sm">
                <span>{i.quantity}× {i.product_name} <span className="text-muted">· {i.category}</span></span>
                <span className="tabular-nums">{money(Number(i.unit_price) * i.quantity, o.currency)}</span>
              </li>
            ))}
            <li className="flex justify-between px-5 py-3 text-sm font-semibold"><span>Total</span><span className="tabular-nums">{money(o.total_amount, o.currency)}</span></li>
          </ul>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title={<span className="flex items-center gap-2"><Truck className="h-4 w-4" /> Delivery</span>} />
            <CardBody>
              {o.shipments?.length ? o.shipments.map((s) => (
                <KeyValue key={s.id} items={[["Carrier", s.carrier], ["Tracking", s.tracking_number], ["Status", <StatusBadge status={s.status} />], ["Estimated", dateOnly(s.estimated_delivery)], ["Latest event", s.last_event]]} />
              )) : <p className="text-sm text-muted">Not shipped yet.</p>}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Payment" />
            <CardBody className="space-y-4">
              {!o.payments?.length && <p className="text-sm text-muted">No payment yet.</p>}
              {o.payments?.map((p) => (
                <div key={p.id}>
                  <KeyValue items={[["Status", <StatusBadge status={p.status} />], ["Source", p.is_sample ? 'Sample data' : 'PayPal Sandbox'], ["Amount", money(p.amount, p.currency)], ["Refunded", money(p.refunded_amount, p.currency)], ["PayPal order", p.paypal_order_id], ["Capture ID", p.paypal_capture_id]]} />
                  {p.failure_reason && <Notice tone="danger" className="mt-3">{p.failure_reason}</Notice>}
                </div>
              ))}
            </CardBody>
          </Card>
        </div>
      </div>
      <Modal
        open={refundOpen}
        onClose={() => setRefundOpen(false)}
        title={`Request a refund — order #${o.order_number}`}
        footer={result ? <Button onClick={() => setRefundOpen(false)}>Done</Button> : (
          <>
            <Button variant="secondary" onClick={() => setRefundOpen(false)}>Cancel</Button>
            <Button disabled={reason.trim().length < 3} loading={refund.isPending} onClick={async () => setResult(await refund.mutateAsync(undefined))}>Submit request</Button>
          </>
        )}
      >
        {result ? (
          <ActionResultCard card={{ ...result, kind: 'refund' }} />
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted">Your request is checked against our refund policy. Small refunds may be issued automatically; others are reviewed by a manager. You'll see the real outcome, not a guess.</p>
            {payment?.is_sample && <Notice tone="warning">This order's payment is seeded sample data, not a PayPal Sandbox capture, so PayPal cannot actually refund it. Pay a new order with PayPal Sandbox to test a real refund.</Notice>}
            <Field label="Amount (leave empty for a full refund)" hint={`Refundable: ${money(payment?.refundable_amount, o.currency)}`}>
              <Input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={payment?.refundable_amount} />
            </Field>
            <Field label="Reason"><Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. The lamp arrived with a cracked shade" /></Field>
          </div>
        )}
      </Modal>
    </div>
  );
}

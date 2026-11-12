import { Link, useParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { Payment } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge, SampleBadge, SandboxBadge } from '@/components/ui/badge';
import { DataTable } from '@/components/ui/table';
import { KeyValue, Notice, PageHeader, Skeleton } from '@/components/ui/misc';
import { PayPalLog } from './PayPalLog';
import { useAuth, isManager } from '@/stores/auth';
import { dateTime, money } from '@/lib/utils';

export default function PaymentDetail() {
  const { id } = useParams();
  const role = useAuth((s) => s.user?.role);
  const { data: p, isLoading } = useApi<Payment>(['payment', id], `/api/payments/${id}`);
  const sync = useAction(() => post<Payment>(`/api/payments/${id}/sync`), { invalidate: [['payment', id]], success: (r) => `PayPal reports ${r.status}` });
  if (isLoading || !p) return <Skeleton className="h-96" />;
  return (
    <div>
      <PageHeader
        title={<span className="flex items-center gap-2">Payment for order #{p.order_number} <StatusBadge status={p.status} /> {p.is_sample ? <SampleBadge /> : <SandboxBadge />}</span>}
        description={`${p.customer_name} · attempt ${p.attempt} · ${dateTime(p.created_at)}`}
        actions={!p.is_sample && p.paypal_order_id && isManager(role) && <Button variant="secondary" loading={sync.isPending} onClick={() => sync.mutate(undefined)}><RefreshCw className="h-4 w-4" /> Sync from PayPal</Button>}
      />
      {p.is_sample && <Notice tone="warning" className="mb-6">Seeded sample payment. It was never sent to PayPal and cannot be captured or refunded through PayPal.</Notice>}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Details" />
          <CardBody>
            <KeyValue items={[["Amount", money(p.amount, p.currency)], ["Refunded", money(p.refunded_amount, p.currency)], ["Refundable", money(p.refundable_amount, p.currency)], ["Order", <Link className="text-brand-600 hover:underline" to={`/manager/orders/${p.order_id}`}>#{p.order_number}</Link>], ["PayPal order", p.paypal_order_id], ["Capture ID", p.paypal_capture_id], ["Payer", p.payer_email], ["Captured", dateTime(p.captured_at)]]} />
            {p.failure_reason && <Notice tone="danger" className="mt-4">{p.failure_reason}</Notice>}
          </CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Refunds against this payment" />
          <DataTable rows={p.refunds ?? []} rowKey={(r) => r.id} empty="No refunds." columns={[
            { key: 'a', header: 'Amount', cell: (r) => money(r.amount, r.currency) },
            { key: 's', header: 'Status', cell: (r) => <StatusBadge status={r.status} /> },
            { key: 'p', header: 'PayPal refund', cell: (r) => <code className="text-xs">{r.paypal_refund_id ?? '—'}</code> },
            { key: 'd', header: 'Requested', cell: (r) => dateTime(r.created_at) },
          ]} />
        </Card>
        <Card className="lg:col-span-3">
          <CardHeader title="PayPal API log" description="Sanitised record of every call made through the APIMatic PayPal SDK (no tokens or secrets stored)" />
          <PayPalLog rows={p.paypal_transactions ?? []} />
        </Card>
      </div>
    </div>
  );
}

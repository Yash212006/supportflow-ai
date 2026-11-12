import { useApi } from '@/lib/queries';
import type { Refund } from '@/lib/types';
import { Card } from '@/components/ui/card';
import { DataTable } from '@/components/ui/table';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { EmptyState, PageHeader, Skeleton } from '@/components/ui/misc';
import { dateTime, money } from '@/lib/utils';

const EXPLAIN: Record<string, string> = {
  REQUESTED: 'Being checked against the refund policy',
  AWAITING_APPROVAL: 'Waiting for a manager to review',
  PENDING: 'Sent to PayPal; PayPal is still processing it',
  OUTCOME_UNKNOWN: "Sent to PayPal; we're confirming the result",
  COMPLETED: 'PayPal completed the refund',
  FAILED: 'The refund could not be completed',
  REJECTED: 'Not approved under the refund policy',
  CANCELLED: 'Cancelled',
};

export default function CustomerRefunds() {
  const { data, isLoading } = useApi<Refund[]>(['customer', 'refunds'], '/api/customer/refunds', { refetchInterval: 15000 });
  return (
    <div>
      <PageHeader title="Refunds" description="Live status of your refund requests. A refund is only marked completed after PayPal confirms it." />
      <Card>
        {isLoading ? <Skeleton className="m-5 h-40" /> : !data?.length ? <EmptyState title="No refund requests" description="Ask the AI assistant or open an order to request a refund." /> : (
          <DataTable rows={data} rowKey={(r) => r.id} columns={[
            { key: 'o', header: 'Order', cell: (r) => <span className="font-medium">#{r.order_number} <SampleBadge show={r.is_sample} /></span> },
            { key: 'r', header: 'Reason', cell: (r) => <span className="line-clamp-1 text-muted">{r.reason}</span> },
            { key: 's', header: 'Status', cell: (r) => <div><StatusBadge status={r.status} /><p className="mt-1 text-xs text-muted">{EXPLAIN[r.status] ?? ''}{r.failure_reason ? ` — ${r.failure_reason}` : ''}</p></div> },
            { key: 'p', header: 'PayPal refund', cell: (r) => r.paypal_refund_id ? <code className="text-xs">{r.paypal_refund_id}</code> : <span className="text-muted">—</span> },
            { key: 'd', header: 'Requested', cell: (r) => dateTime(r.created_at) },
            { key: 'a', header: 'Amount', align: 'right', cell: (r) => money(r.amount, r.currency) },
          ]} />
        )}
      </Card>
    </div>
  );
}

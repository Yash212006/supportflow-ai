import { ListPage } from '@/components/ListPage';
import type { Payment } from '@/lib/types';
import { StatusBadge, SampleBadge, SandboxBadge } from '@/components/ui/badge';
import { dateTime, money } from '@/lib/utils';

export default function Payments() {
  return (
    <ListPage<Payment>
      title="Payments"
      description="PayPal Sandbox payments show the status PayPal reported. Seeded rows are labelled sample data."
      endpoint="/api/payments"
      searchable
      filters={[
        { param: 'status', label: 'Status', options: ['CREATED', 'APPROVED', 'CAPTURE_PENDING', 'CAPTURED', 'DECLINED', 'FAILED', 'PARTIALLY_REFUNDED', 'REFUNDED'] },
        { param: 'source', label: 'Source', options: ['PAYPAL_SANDBOX', 'SEED_SAMPLE'] },
      ]}
      rowKey={(p) => p.id}
      rowLink={(p) => `/manager/payments/${p.id}`}
      columns={[
        { key: 'o', header: 'Order', cell: (p) => <span className="font-medium">#{p.order_number}</span> },
        { key: 'c', header: 'Customer', cell: (p) => p.customer_name },
        { key: 'src', header: 'Source', cell: (p) => (p.is_sample ? <SampleBadge /> : <SandboxBadge />) },
        { key: 's', header: 'Status', cell: (p) => <StatusBadge status={p.status} /> },
        { key: 'cap', header: 'PayPal capture', cell: (p) => <code className="text-xs text-muted">{p.paypal_capture_id ?? '—'}</code> },
        { key: 'd', header: 'Created', cell: (p) => <span className="text-xs">{dateTime(p.created_at)}</span> },
        { key: 'r', header: 'Refunded', align: 'right', cell: (p) => money(p.refunded_amount, p.currency) },
        { key: 'a', header: 'Amount', align: 'right', cell: (p) => money(p.amount, p.currency) },
      ]}
    />
  );
}

import { useNavigate } from 'react-router-dom';
import { useApi } from '@/lib/queries';
import type { Payment } from '@/lib/types';
import { Card } from '@/components/ui/card';
import { DataTable } from '@/components/ui/table';
import { StatusBadge, SampleBadge, SandboxBadge } from '@/components/ui/badge';
import { PageHeader, Skeleton } from '@/components/ui/misc';
import { dateTime, money } from '@/lib/utils';

export default function CustomerPayments() {
  const nav = useNavigate();
  const { data, isLoading } = useApi<Payment[]>(['customer', 'payments'], '/api/customer/payments');
  return (
    <div>
      <PageHeader title="Payments" description="Every payment attempt and its status as reported by PayPal." />
      <Card>
        {isLoading ? <Skeleton className="m-5 h-40" /> : (
          <DataTable rows={data ?? []} rowKey={(p) => p.id} onRowClick={(p) => nav(`/customer/orders/${p.order_id}`)} columns={[
            { key: 'o', header: 'Order', cell: (p) => <span className="font-medium">#{p.order_number}</span> },
            { key: 's', header: 'Source', cell: (p) => p.is_sample ? <SampleBadge /> : <SandboxBadge /> },
            { key: 'st', header: 'Status', cell: (p) => <StatusBadge status={p.status} /> },
            { key: 'c', header: 'Capture ID', cell: (p) => <code className="text-xs text-muted">{p.paypal_capture_id ?? '—'}</code> },
            { key: 'd', header: 'Date', cell: (p) => dateTime(p.created_at) },
            { key: 'r', header: 'Refunded', align: 'right', cell: (p) => money(p.refunded_amount, p.currency) },
            { key: 'a', header: 'Amount', align: 'right', cell: (p) => money(p.amount, p.currency) },
          ]} />
        )}
      </Card>
    </div>
  );
}

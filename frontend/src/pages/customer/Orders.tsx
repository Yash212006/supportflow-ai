import { useNavigate } from 'react-router-dom';
import { useApi } from '@/lib/queries';
import type { Order } from '@/lib/types';
import { Card } from '@/components/ui/card';
import { DataTable } from '@/components/ui/table';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { PageHeader, Skeleton } from '@/components/ui/misc';
import { dateOnly, money } from '@/lib/utils';

export default function CustomerOrders() {
  const nav = useNavigate();
  const { data, isLoading } = useApi<Order[]>(['customer', 'orders'], '/api/customer/orders');
  return (
    <div>
      <PageHeader title="My orders" />
      <Card>
        {isLoading ? <Skeleton className="m-5 h-40" /> : (
          <DataTable
            rows={data ?? []}
            rowKey={(o) => o.id}
            onRowClick={(o) => nav(`/customer/orders/${o.id}`)}
            columns={[
              { key: 'n', header: 'Order', cell: (o) => <span className="font-medium">#{o.order_number} <SampleBadge show={o.is_sample} /></span> },
              { key: 'i', header: 'Items', cell: (o) => <span className="text-muted">{o.items_summary}</span> },
              { key: 'd', header: 'Placed', cell: (o) => dateOnly(o.placed_at) },
              { key: 's', header: 'Status', cell: (o) => <StatusBadge status={o.status} /> },
              { key: 'p', header: 'Payment', cell: (o) => <StatusBadge status={o.payment_status} /> },
              { key: 't', header: 'Total', align: 'right', cell: (o) => money(o.total_amount, o.currency) },
            ]}
          />
        )}
      </Card>
    </div>
  );
}

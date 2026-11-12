import { ListPage } from '@/components/ListPage';
import type { Order } from '@/lib/types';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { dateOnly, money } from '@/lib/utils';

export default function Orders() {
  return (
    <ListPage<Order>
      title="Orders"
      endpoint="/api/orders"
      searchable
      filters={[{ param: 'status', label: 'Status', options: ['PENDING_PAYMENT', 'PAID', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'PARTIALLY_REFUNDED', 'REFUNDED'] }]}
      rowKey={(o) => o.id}
      rowLink={(o) => `/manager/orders/${o.id}`}
      columns={[
        { key: 'n', header: 'Order', cell: (o) => <span className="font-medium">#{o.order_number} <SampleBadge show={o.is_sample} /></span> },
        { key: 'c', header: 'Customer', cell: (o) => o.customer_name },
        { key: 'i', header: 'Items', cell: (o) => <span className="line-clamp-1 max-w-xs text-xs text-muted">{o.items_summary}</span> },
        { key: 'd', header: 'Placed', cell: (o) => dateOnly(o.placed_at) },
        { key: 's', header: 'Status', cell: (o) => <StatusBadge status={o.status} /> },
        { key: 'p', header: 'Payment', cell: (o) => <StatusBadge status={o.payment_status} /> },
        { key: 'sh', header: 'Shipment', cell: (o) => <StatusBadge status={o.shipment_status} /> },
        { key: 't', header: 'Total', align: 'right', cell: (o) => money(o.total_amount, o.currency) },
      ]}
    />
  );
}

import { useNavigate, useParams } from 'react-router-dom';
import { useApi } from '@/lib/queries';
import type { Customer, Order, Refund, Ticket } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { DataTable } from '@/components/ui/table';
import { KeyValue, PageHeader, Skeleton } from '@/components/ui/misc';
import { dateOnly, humanize, money } from '@/lib/utils';

export default function CustomerDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: c, isLoading } = useApi<Customer & { orders: Order[]; tickets: Ticket[]; refunds: Refund[] }>(['customer', id], `/api/customers/${id}`);
  if (isLoading || !c) return <Skeleton className="h-96" />;
  return (
    <div>
      <PageHeader title={c.full_name} description={c.email} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card><CardHeader title="Profile" /><CardBody><KeyValue items={[["Phone", c.phone], ["City", c.city], ["Segment", humanize(c.segment)], ["Customer since", dateOnly(c.created_at)], ["Orders", c.orders.length], ["Refunds", c.refunds.length]]} /></CardBody></Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Orders" />
          <DataTable rows={c.orders} rowKey={(o) => o.id} onRowClick={(o) => nav(`/manager/orders/${o.id}`)} columns={[
            { key: 'n', header: 'Order', cell: (o) => <span className="font-medium">#{o.order_number} <SampleBadge show={o.is_sample} /></span> },
            { key: 'd', header: 'Placed', cell: (o) => dateOnly(o.placed_at) },
            { key: 's', header: 'Status', cell: (o) => <StatusBadge status={o.status} /> },
            { key: 't', header: 'Total', align: 'right', cell: (o) => money(o.total_amount, o.currency) },
          ]} />
        </Card>
        <Card className="lg:col-span-2 lg:col-start-2">
          <CardHeader title="Tickets" />
          <DataTable rows={c.tickets} rowKey={(t) => t.id} onRowClick={(t) => nav(`/manager/tickets/${t.id}`)} columns={[
            { key: 'n', header: '#', cell: (t) => t.ticket_number },
            { key: 's', header: 'Subject', cell: (t) => t.subject },
            { key: 'st', header: 'Status', cell: (t) => <StatusBadge status={t.status} /> },
          ]} />
        </Card>
        <Card className="lg:col-span-2 lg:col-start-2">
          <CardHeader title="Refund history" />
          <DataTable rows={c.refunds} rowKey={(r) => r.id} columns={[
            { key: 'o', header: 'Order', cell: (r) => `#${r.order_number}` },
            { key: 's', header: 'Status', cell: (r) => <StatusBadge status={r.status} /> },
            { key: 'd', header: 'Date', cell: (r) => dateOnly(r.created_at) },
            { key: 'a', header: 'Amount', align: 'right', cell: (r) => money(r.amount, r.currency) },
          ]} />
        </Card>
      </div>
    </div>
  );
}

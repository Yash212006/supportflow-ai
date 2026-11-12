import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { Order, Ticket } from '@/lib/types';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/table';
import { StatusBadge } from '@/components/ui/badge';
import { Field, Input, Select, Textarea } from '@/components/ui/input';
import { Modal, PageHeader, Skeleton } from '@/components/ui/misc';
import { ago, humanize } from '@/lib/utils';

export default function CustomerTickets() {
  const nav = useNavigate();
  const { data, isLoading } = useApi<Ticket[]>(['customer', 'tickets'], '/api/customer/tickets');
  const { data: orders } = useApi<Order[]>(['customer', 'orders'], '/api/customer/orders');
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ subject: '', description: '', order_id: '' });
  const create = useAction(() => post<Ticket>('/api/customer/tickets', { ...f, order_id: f.order_id || null }), { invalidate: [['customer']], success: 'Ticket created' });
  return (
    <div>
      <PageHeader title="Support tickets" actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New ticket</Button>} />
      <Card>
        {isLoading ? <Skeleton className="m-5 h-40" /> : (
          <DataTable rows={data ?? []} rowKey={(t) => t.id} onRowClick={(t) => nav(`/customer/tickets/${t.id}`)} columns={[
            { key: 'n', header: '#', cell: (t) => <span className="font-medium">{t.ticket_number}</span> },
            { key: 's', header: 'Subject', cell: (t) => t.subject },
            { key: 'c', header: 'Category', cell: (t) => <span className="text-muted">{humanize(t.category)}</span> },
            { key: 'st', header: 'Status', cell: (t) => <StatusBadge status={t.status} /> },
            { key: 'u', header: 'Updated', cell: (t) => ago(t.updated_at) },
          ]} />
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="New support ticket" footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={create.isPending} disabled={f.subject.length < 3 || f.description.length < 5} onClick={async () => { const t = await create.mutateAsync(undefined); setOpen(false); nav(`/customer/tickets/${t.id}`); }}>Create</Button></>}>
        <div className="space-y-4">
          <Field label="Subject"><Input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></Field>
          <Field label="Order (optional)">
            <Select value={f.order_id} onChange={(e) => setF({ ...f, order_id: e.target.value })}>
              <option value="">No specific order</option>
              {orders?.map((o) => <option key={o.id} value={o.id}>#{o.order_number} — {o.items_summary}</option>)}
            </Select>
          </Field>
          <Field label="Describe the issue"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        </div>
      </Modal>
    </div>
  );
}

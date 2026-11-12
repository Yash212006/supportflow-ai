import { ListPage } from '@/components/ListPage';
import type { Ticket } from '@/lib/types';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { ago, humanize } from '@/lib/utils';

export default function Tickets() {
  return (
    <ListPage<Ticket>
      title="Tickets"
      description="Created and triaged by the orchestrator agent; humans take over escalations."
      endpoint="/api/tickets"
      searchable
      filters={[
        { param: 'status', label: 'Status', options: ['OPEN', 'IN_PROGRESS', 'WAITING_ON_CUSTOMER', 'ESCALATED', 'RESOLVED', 'CLOSED'] },
        { param: 'priority', label: 'Priority', options: ['LOW', 'MEDIUM', 'HIGH', 'URGENT'] },
        { param: 'category', label: 'Category', options: ['REFUND_REQUEST', 'CANCELLATION', 'PAYMENT_FAILURE', 'DELAYED_SHIPMENT', 'PRODUCT_ISSUE', 'ACCOUNT_ISSUE', 'ORDER_INQUIRY', 'GENERAL_SUPPORT'] },
      ]}
      rowKey={(t) => t.id}
      rowLink={(t) => `/manager/tickets/${t.id}`}
      columns={[
        { key: 'n', header: '#', cell: (t) => <span className="font-medium">{t.ticket_number}</span> },
        { key: 's', header: 'Subject', cell: (t) => <div className="max-w-md"><p className="truncate font-medium">{t.subject} <SampleBadge show={t.is_sample} /></p><p className="text-xs text-muted">{t.customer_name}</p></div> },
        { key: 'c', header: 'Category', cell: (t) => <span className="text-xs text-muted">{humanize(t.category)}{t.ai_classification_confidence ? ` · ${(t.ai_classification_confidence * 100).toFixed(0)}%` : ''}</span> },
        { key: 'p', header: 'Priority', cell: (t) => <StatusBadge status={t.priority} /> },
        { key: 'st', header: 'Status', cell: (t) => <StatusBadge status={t.status} /> },
        { key: 'a', header: 'Assignee', cell: (t) => <span className="text-xs">{t.assigned_to ?? <span className="text-muted">Unassigned</span>}</span> },
        { key: 'u', header: 'Updated', cell: (t) => <span className="text-xs text-muted">{ago(t.updated_at)}</span> },
      ]}
    />
  );
}

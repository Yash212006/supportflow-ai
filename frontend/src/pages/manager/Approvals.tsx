import { useState } from 'react';
import { ListPage } from '@/components/ListPage';
import type { Approval } from '@/lib/types';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { Tabs } from '@/components/ui/misc';
import { ago, humanize } from '@/lib/utils';

export default function Approvals() {
  const [tab, setTab] = useState<'PENDING' | ''>('PENDING');
  return (
    <ListPage<Approval>
      key={tab}
      title="Approval center"
      description="Refunds the policy engine routed to a human. Every approval re-validates the payment before PayPal is called."
      endpoint="/api/approvals"
      filters={tab ? [] : [{ param: 'status', label: 'Status', options: ['PENDING', 'APPROVED', 'REJECTED', 'EXECUTION_FAILED', 'EXPIRED'] }]}
      header={<div className="mb-4"><Tabs value={tab} onChange={setTab} tabs={[{ value: 'PENDING', label: 'Pending' }, { value: '', label: 'All decisions' }]} /></div>}
      rowKey={(a) => a.id}
      rowLink={(a) => `/manager/approvals/${a.id}`}
      refetchInterval={20000}
      fixedParams={tab ? { status: tab } : undefined}
      columns={[
        { key: 't', header: 'Request', cell: (a) => <div><p className="font-medium">{a.title} <SampleBadge show={a.is_sample} /></p><p className="line-clamp-1 text-xs text-muted">{a.reason}</p></div> },
        { key: 'r', header: 'Risk', cell: (a) => <StatusBadge status={a.risk_level} /> },
        { key: 'p', header: 'Proposed by', cell: (a) => <span className="text-muted">{humanize(a.proposed_by.replace('agent:', 'AI '))}</span> },
        { key: 's', header: 'Status', cell: (a) => <StatusBadge status={a.status} /> },
        { key: 'c', header: 'Created', cell: (a) => ago(a.created_at) },
      ]}
    />
  );
}

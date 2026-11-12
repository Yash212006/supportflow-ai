import { useState } from 'react';
import { ListPage } from '@/components/ListPage';
import type { AuditRow } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/misc';
import { dateTime } from '@/lib/utils';

export default function AuditLogs() {
  const [row, setRow] = useState<AuditRow | null>(null);
  return (
    <>
      <ListPage<AuditRow>
        title="Audit log"
        description="Append-only record of sign-ins, policy changes, approvals, PayPal calls and financial state changes."
        endpoint="/api/audit-logs"
        pageSize={50}
        filters={[{ param: 'actor_type', label: 'Actor', options: ['user', 'agent', 'paypal', 'system'] }]}
        rowKey={(r) => r.id}
        columns={[
          { key: 'd', header: 'When', cell: (r) => <span className="whitespace-nowrap text-xs">{dateTime(r.created_at)}</span> },
          { key: 'a', header: 'Actor', cell: (r) => <Badge tone={r.actor_type === 'agent' ? 'violet' : r.actor_type === 'paypal' ? 'indigo' : 'gray'}>{r.actor_type}</Badge> },
          { key: 'ac', header: 'Action', cell: (r) => <code className="text-xs">{r.action}</code> },
          { key: 's', header: 'Summary', cell: (r) => <button className="text-left hover:text-brand-600" onClick={() => setRow(r)}>{r.summary}</button> },
          { key: 'e', header: 'Entity', cell: (r) => <span className="text-xs text-muted">{r.entity_type}</span> },
        ]}
      />
      <Modal open={!!row} onClose={() => setRow(null)} title={row?.action ?? ''} wide>
        <pre className="overflow-auto rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify(row, null, 2)}</pre>
      </Modal>
    </>
  );
}

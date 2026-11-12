import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, RotateCcw } from 'lucide-react';
import { ListPage } from '@/components/ListPage';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { Refund } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { StatusBadge, SampleBadge } from '@/components/ui/badge';
import { KeyValue, Modal, Notice, Skeleton } from '@/components/ui/misc';
import { DecisionTrace } from '@/components/DecisionTrace';
import { PayPalLog } from './PayPalLog';
import { useAuth, isManager } from '@/stores/auth';
import { dateTime, money } from '@/lib/utils';

function RefundModal({ id, onClose }: { id: string; onClose: () => void }) {
  const role = useAuth((s) => s.user?.role);
  const { data: r, isLoading } = useApi<Refund>(['refund', id], `/api/refunds/${id}`);
  const inv = [['refund', id], ['/api/refunds']];
  const reconcile = useAction(() => post(`/api/actions/${r?.execution_action_id}/reconcile`), { invalidate: inv, success: 'Reconciled with PayPal' });
  const retry = useAction(() => post(`/api/actions/${r?.execution_action_id}/retry`), { invalidate: inv, success: 'Retried' });
  const state = r?.action?.state;
  return (
    <Modal open onClose={onClose} wide title={r ? <span className="flex items-center gap-2">Refund {money(r.amount, r.currency)} · order #{r.order_number} <StatusBadge status={r.status} /></span> : 'Refund'}
      footer={r && isManager(role) && (
        <>
          {state === 'PENDING_CONFIRMATION' && <Button variant="secondary" loading={reconcile.isPending} onClick={() => reconcile.mutate(undefined)}><RefreshCw className="h-4 w-4" /> Reconcile with PayPal</Button>}
          {state === 'FAILED' && !r.is_sample && r.action?.error_code !== 'NOT_A_PAYPAL_CAPTURE' && <Button variant="secondary" loading={retry.isPending} onClick={() => retry.mutate(undefined)}><RotateCcw className="h-4 w-4" /> Retry (re-validates first)</Button>}
          <Button onClick={onClose}>Close</Button>
        </>
      )}>
      {isLoading || !r ? <Skeleton className="h-60" /> : (
        <div className="space-y-6">
          <KeyValue items={[["Customer", r.customer_name], ["Order", <Link className="text-brand-600 hover:underline" to={`/manager/orders/${r.order_id}`}>#{r.order_number}</Link>], ["Execution state", <StatusBadge status={state} />], ["PayPal refund ID", r.paypal_refund_id ?? '—'], ["PayPal status", r.paypal_status ?? '—'], ["Completed", dateTime(r.completed_at)]]} />
          {state === 'PENDING_CONFIRMATION' && <Notice tone="warning" title="Waiting for PayPal confirmation">The amount is reserved so it can't be refunded twice. Reconciling re-sends the identical request with the same PayPal-Request-Id, so PayPal returns the original refund instead of creating a new one.</Notice>}
          {r.failure_reason && <Notice tone="danger">{r.failure_reason}</Notice>}
          {r.decision && <div><p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Policy decision</p><DecisionTrace decision={r.decision} /></div>}
          <div><p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">PayPal calls</p><PayPalLog rows={r.paypal_transactions ?? []} /></div>
        </div>
      )}
    </Modal>
  );
}

export default function Refunds() {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <ListPage<Refund>
        title="Refunds"
        description="Every refund passes through the policy engine and the execution state machine. Completed means PayPal confirmed it."
        endpoint="/api/refunds"
        filters={[{ param: 'status', label: 'Status', options: ['REQUESTED', 'AWAITING_APPROVAL', 'PENDING', 'OUTCOME_UNKNOWN', 'COMPLETED', 'FAILED', 'REJECTED', 'CANCELLED'] }]}
        rowKey={(r) => r.id}
        refetchInterval={20000}
        columns={[
          { key: 'o', header: 'Order', cell: (r) => <button className="font-medium text-brand-600 hover:underline" onClick={() => setOpen(r.id)}>#{r.order_number}</button> },
          { key: 'c', header: 'Customer', cell: (r) => <span>{r.customer_name} <SampleBadge show={r.is_sample} /></span> },
          { key: 'po', header: 'Policy', cell: (r) => <StatusBadge status={r.policy_outcome} /> },
          { key: 's', header: 'Status', cell: (r) => <StatusBadge status={r.status} /> },
          { key: 'pp', header: 'PayPal refund', cell: (r) => <code className="text-xs text-muted">{r.paypal_refund_id ?? '—'}</code> },
          { key: 'd', header: 'Requested', cell: (r) => <span className="text-xs">{dateTime(r.created_at)}</span> },
          { key: 'a', header: 'Amount', align: 'right', cell: (r) => money(r.amount, r.currency) },
          { key: 'v', header: '', cell: (r) => <Button size="sm" variant="ghost" onClick={() => setOpen(r.id)}>Details</Button> },
        ]}
      />
      {open && <RefundModal id={open} onClose={() => setOpen(null)} />}
    </>
  );
}

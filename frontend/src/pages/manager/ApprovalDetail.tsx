import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CheckCircle2, ShieldCheck, XCircle } from 'lucide-react';
import { useApi, useAction } from '@/lib/queries';
import { post } from '@/lib/api';
import type { Approval } from '@/lib/types';
import { Card, CardBody, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, StatusBadge, SampleBadge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/input';
import { KeyValue, Notice, PageHeader, Skeleton } from '@/components/ui/misc';
import { DecisionTrace, FactsTable } from '@/components/DecisionTrace';
import { useAuth, isManager } from '@/stores/auth';
import { dateTime, humanize, money } from '@/lib/utils';

type Signal = { code: string; detail?: string; description?: string } | string;

export default function ApprovalDetail() {
  const { id } = useParams();
  const role = useAuth((s) => s.user?.role);
  const { data: a, isLoading } = useApi<Approval>(['approval', id], `/api/approvals/${id}`);
  const [note, setNote] = useState('');
  const inv = [['approval', id], ['/api/approvals'], ['overview']];
  const approve = useAction(() => post<Record<string, unknown>>(`/api/approvals/${id}/approve`, { note: note || null }), { invalidate: inv, success: (r) => (r.action_state === 'SUCCEEDED' ? 'Approved — PayPal completed the refund' : r.action_state === 'FAILED' ? null : 'Approved — waiting for PayPal confirmation') });
  const reject = useAction(() => post(`/api/approvals/${id}/reject`, { note }), { invalidate: inv, success: 'Request rejected' });
  if (isLoading || !a) return <Skeleton className="h-96" />;
  const pending = a.status === 'PENDING';
  const check = a.current_check;
  const p = a.action?.payload ?? {};
  const signals = (a.current_check?.risk.signals ?? a.risk_summary.signals ?? []) as Signal[];
  const result = a.final_result as { action_state?: string; refund_status?: string; paypal_refund_id?: string | null; paypal_status?: string | null; error?: string | null };
  return (
    <div>
      <PageHeader title={<span className="flex flex-wrap items-center gap-2">{a.title} <StatusBadge status={a.status} /> <SampleBadge show={a.is_sample} /></span>} description={<>Proposed by {humanize(a.proposed_by.replace('agent:', 'AI '))} · {dateTime(a.created_at)} {a.agent_execution && <Link to={`/manager/ai-operations/${a.agent_execution.id}`} className="text-brand-600 hover:underline">· view agent trace</Link>}</>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {a.decision && (
            <Card>
              <CardHeader title="Why this needs approval" description="Deterministic policy evaluation recorded at request time" />
              <CardBody><DecisionTrace decision={a.decision} /></CardBody>
            </Card>
          )}
          {a.decision && (
            <Card>
              <CardHeader title="Facts the policy saw" />
              <CardBody><FactsTable inputs={a.decision.inputs} /></CardBody>
            </Card>
          )}
          {a.action?.history && (
            <Card>
              <CardHeader title="Execution state history" />
              <CardBody>
                <ol className="space-y-2 text-sm">
                  {a.action.history.map((h, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2">
                      <span className="w-36 text-xs text-muted">{dateTime(h.at)}</span>
                      {h.from && <><StatusBadge status={h.from} /><span className="text-muted">→</span></>}
                      <StatusBadge status={h.to} />
                      <span className="text-xs text-muted">{h.actor}{h.note ? ` · ${h.note}` : ''}</span>
                    </li>
                  ))}
                </ol>
              </CardBody>
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Refund" />
            <CardBody className="space-y-4">
              <KeyValue items={[["Amount", money(p.amount, p.currency)], ["Order", a.order ? <Link className="text-brand-600 hover:underline" to={`/manager/orders/${a.order.id}`}>#{a.order.order_number}</Link> : '—'], ["Customer", a.customer?.full_name], ["Order total", money(a.order?.total_amount, a.order?.currency)]]} />
              <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">“{p.reason}”</p>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={<span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Live re-check</span>} description="Recomputed now; execution re-validates again on approval" />
            <CardBody className="space-y-3">
              {check ? <KeyValue items={[["Refundable now", money(check.refundable_amount, p.currency)], ["Payment status", <StatusBadge status={check.payment_status} />], ["Risk", <StatusBadge status={check.risk.level} />], ["Policy version", `v${a.current_policy_version ?? '—'} (decided on v${a.decision?.policy_version ?? '—'})`], ["PayPal capture", check.paypal_capture ?? '—']]} /> : <p className="text-sm text-muted">Unavailable.</p>}
              {!!signals.length && (
                <ul className="space-y-1">
                  {signals.map((s, i) => <li key={i} className="text-xs"><Badge tone="amber">{typeof s === 'string' ? s : s.code}</Badge> <span className="text-muted">{typeof s === 'string' ? '' : s.description ?? s.detail}</span></li>)}
                </ul>
              )}
              <p className="text-xs text-muted">{check?.risk.recommended_next_step}</p>
              {check?.is_sample && <Notice tone="warning" title="Sample payment">This payment is seeded sample data, not a PayPal Sandbox capture. Approving records your decision, but no PayPal refund can be issued, so the action will be marked failed.</Notice>}
            </CardBody>
          </Card>
          {pending ? (
            isManager(role) ? (
              <Card>
                <CardHeader title="Decision" />
                <CardBody className="space-y-3">
                  <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (required to reject)" />
                  <div className="flex gap-2">
                    <Button variant="success" className="flex-1" loading={approve.isPending} disabled={reject.isPending} onClick={() => approve.mutate(undefined)}><CheckCircle2 className="h-4 w-4" /> Approve & execute</Button>
                    <Button variant="danger" className="flex-1" loading={reject.isPending} disabled={!note.trim() || approve.isPending} onClick={() => reject.mutate(undefined)}><XCircle className="h-4 w-4" /> Reject</Button>
                  </div>
                </CardBody>
              </Card>
            ) : <Notice>Only managers can decide approvals.</Notice>
          ) : (
            <Card>
              <CardHeader title="Outcome" />
              <CardBody className="space-y-3">
                <KeyValue items={[["Decided by", a.decided_by], ["Decided", dateTime(a.decided_at)], ["Execution", <StatusBadge status={result.action_state} />], ["Refund", <StatusBadge status={result.refund_status} />], ["PayPal refund ID", result.paypal_refund_id ?? '—'], ["PayPal status", result.paypal_status ?? '—']]} />
                {a.manager_note && <p className="rounded-lg bg-slate-50 p-3 text-sm">“{a.manager_note}”</p>}
                {result.error && <Notice tone="danger">{result.error}</Notice>}
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

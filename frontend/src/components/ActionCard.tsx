import { Link } from 'react-router-dom';
import { CheckCircle2, Clock, ShieldAlert, XCircle, HelpCircle, ArrowUpRight } from 'lucide-react';
import type { ActionCard as Card } from '@/lib/types';
import { StatusBadge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

/**
 * Renders the result of a financial action proposed by an agent.
 * The state shown always comes from the execution engine / PayPal, never from the model's text.
 */
export function ActionResultCard({ card, liveStatus, staff }: { card: Card; liveStatus?: string | null; staff?: boolean }) {
  if (card.kind !== 'refund' && card.kind !== 'cancellation') {
    return (
      <div className="rounded-lg border border-line bg-white px-3 py-2 text-xs text-slate-700">
        {String(card.kind)}: {String(card.summary ?? card.action_state ?? '')}
      </div>
    );
  }
  const status = liveStatus ?? card.refund_status ?? card.action_state ?? null;
  // Only a confirmed status counts as success; a later live status (e.g. FAILED) always wins over the original card.
  const succeeded = status === 'COMPLETED' || status === 'SUCCEEDED';
  const waiting = ['AWAITING_APPROVAL', 'REQUIRES_APPROVAL', 'PENDING', 'PENDING_CONFIRMATION', 'OUTCOME_UNKNOWN', 'REQUESTED'].includes(String(status));
  const failed = ['FAILED', 'REJECTED', 'CANCELLED'].includes(String(status));
  const Icon = succeeded ? CheckCircle2 : waiting ? Clock : failed ? XCircle : card.decision === 'ESCALATED' ? ShieldAlert : HelpCircle;
  const tone = succeeded ? 'border-emerald-200 bg-emerald-50/60' : waiting ? 'border-amber-200 bg-amber-50/60' : failed ? 'border-rose-200 bg-rose-50/60' : 'border-line bg-white';
  const headline = succeeded
    ? 'Refund completed by PayPal'
    : status === 'OUTCOME_UNKNOWN'
      ? 'Refund sent — waiting for PayPal confirmation'
      : status === 'PENDING'
        ? 'Refund pending at PayPal'
        : card.decision === 'ESCALATED'
          ? 'Escalated for manual review'
          : waiting
            ? 'Waiting for manager approval'
            : status === 'REJECTED'
              ? 'Refund not approved'
              : failed
                ? 'Refund could not be completed'
                : 'Refund request recorded';
  return (
    <div className={cn('rounded-lg border px-3 py-2.5 text-xs', tone)}>
      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4', succeeded ? 'text-emerald-600' : waiting ? 'text-amber-600' : failed ? 'text-rose-600' : 'text-slate-500')} />
        <span className="font-medium text-ink">{headline}</span>
        <span className="ml-auto"><StatusBadge status={status} /></span>
      </div>
      <div className="mt-1.5 space-y-0.5 text-slate-600">
        {card.decision && <p>Policy decision: <span className="font-medium">{card.decision.replace(/_/g, ' ').toLowerCase()}</span></p>}
        {card.paypal_refund_id && <p>PayPal refund ID: <code className="font-mono">{card.paypal_refund_id}</code> ({card.paypal_status})</p>}
        {card.error && <p className="text-rose-700">{card.error}</p>}
        {staff && card.explanation && <p className="text-slate-500">{card.explanation}</p>}
      </div>
      <div className="mt-2 flex gap-3">
        {card.refund_id && !staff && <Link to="/customer/refunds" className="inline-flex items-center gap-1 font-medium text-brand-600 hover:underline">Track refund <ArrowUpRight className="h-3 w-3" /></Link>}
        {staff && card.approval_id && <Link to={`/manager/approvals/${card.approval_id}`} className="inline-flex items-center gap-1 font-medium text-brand-600 hover:underline">Open approval <ArrowUpRight className="h-3 w-3" /></Link>}
      </div>
    </div>
  );
}

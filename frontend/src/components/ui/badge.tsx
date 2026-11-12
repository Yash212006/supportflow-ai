import type { ReactNode } from 'react';
import { cn, humanize } from '@/lib/utils';

const tones = {
  gray: 'bg-slate-100 text-slate-700 ring-slate-200',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-800 ring-amber-200',
  red: 'bg-rose-50 text-rose-700 ring-rose-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  indigo: 'bg-brand-50 text-brand-700 ring-brand-100',
} as const;
export type Tone = keyof typeof tones;

export function Badge({ tone = 'gray', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cn('inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset', tones[tone], className)}>{children}</span>;
}

const STATUS_TONE: Record<string, Tone> = {
  // payments / orders
  CAPTURED: 'green', PAID: 'green', DELIVERED: 'green', COMPLETED: 'green', SUCCEEDED: 'green', RESOLVED: 'green', CLOSED: 'gray', APPROVED: 'green', READY: 'green', PROCESSED: 'green', AUTO_EXECUTE: 'green', LOW: 'green',
  CREATED: 'blue', PROCESSING: 'blue', SHIPPED: 'blue', IN_TRANSIT: 'blue', OPEN: 'blue', IN_PROGRESS: 'blue', EXECUTING: 'blue', VALIDATING: 'blue', REQUESTED: 'blue', RUNNING: 'blue', RECEIVED: 'blue',
  PENDING: 'amber', PENDING_PAYMENT: 'amber', CAPTURE_PENDING: 'amber', AWAITING_APPROVAL: 'amber', REQUIRES_APPROVAL: 'amber', WAITING_ON_CUSTOMER: 'amber', PENDING_CONFIRMATION: 'amber', DELAYED: 'amber', MEDIUM: 'amber', PARTIALLY_REFUNDED: 'violet', NEEDS_MORE_INFORMATION: 'amber', OUTCOME_UNKNOWN: 'amber',
  FAILED: 'red', DECLINED: 'red', REJECTED: 'red', CANCELLED: 'gray', ESCALATED: 'violet', HIGH: 'red', URGENT: 'red', EXECUTION_FAILED: 'red', VOIDED: 'gray', EXPIRED: 'gray', IGNORED: 'gray',
  REFUNDED: 'violet',
};

export function StatusBadge({ status, className }: { status: string | null | undefined; className?: string }) {
  if (!status) return <span className="text-xs text-muted">—</span>;
  return <Badge tone={STATUS_TONE[status] ?? 'gray'} className={className}>{humanize(status)}</Badge>;
}

export function SampleBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return <Badge tone="gray" className="font-normal">Sample data</Badge>;
}

export function SandboxBadge() {
  return <Badge tone="indigo">PayPal Sandbox</Badge>;
}

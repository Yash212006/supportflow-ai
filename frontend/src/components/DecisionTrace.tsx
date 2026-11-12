import { CheckCircle2, Circle, XCircle } from 'lucide-react';
import type { Decision } from '@/lib/types';
import { StatusBadge } from '@/components/ui/badge';
import { cn, humanize } from '@/lib/utils';

const fmt = (v: unknown) => (v === null || v === undefined ? '—' : Array.isArray(v) ? v.join(' – ') : typeof v === 'boolean' ? (v ? 'true' : 'false') : String(v));

export function DecisionTrace({ decision }: { decision: Decision }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <StatusBadge status={decision.outcome} />
        <span className="text-muted">Policy v{decision.policy_version ?? '—'} · matched rule</span>
        <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{decision.matched_rule_id ?? 'default'}</code>
      </div>
      <p className="text-sm text-slate-700">{decision.explanation}</p>
      <div className="space-y-2">
        {decision.evaluated_conditions.map((r) => (
          <div key={r.rule_id} className={cn('rounded-lg border px-3 py-2', r.matched ? 'border-brand-200 bg-brand-50/50' : 'border-line')}>
            <div className="flex items-center gap-2 text-xs">
              {r.matched ? <CheckCircle2 className="h-4 w-4 text-brand-600" /> : <Circle className="h-4 w-4 text-slate-300" />}
              <span className="font-medium text-ink">{r.rule_name}</span>
              <span className="text-muted">→ {humanize(r.rule_outcome)}</span>
              {r.matched && <span className="ml-auto text-[11px] font-semibold uppercase text-brand-700">Matched</span>}
            </div>
            <ul className="mt-1.5 space-y-0.5 pl-6">
              {r.conditions.map((c, i) => (
                <li key={i} className="flex items-center gap-1.5 text-xs text-slate-600">
                  {c.passed ? <CheckCircle2 className="h-3 w-3 text-emerald-500" /> : <XCircle className="h-3 w-3 text-slate-300" />}
                  <code>{c.field}</code> <span className="text-muted">{c.op.replace(/_/g, ' ')}</span> {!['is_true', 'is_false'].includes(c.op) && <code>{fmt(c.expected)}</code>}
                  <span className="text-muted">(actual {fmt(c.actual)})</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

export function FactsTable({ inputs }: { inputs: Record<string, unknown> }) {
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-3">
      {Object.entries(inputs).map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2 border-b border-dashed border-line py-1">
          <span className="text-muted">{k}</span>
          <span className="font-medium tabular-nums">{fmt(v)}</span>
        </div>
      ))}
    </div>
  );
}
